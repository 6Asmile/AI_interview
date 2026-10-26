import os
import subprocess
import json
import logging
import queue
import threading
import time
import signal
from pathlib import Path
from typing import Optional, Dict, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class FFmpegService:
    """FFmpeg 视频处理服务"""
    
    DEFAULT_VIDEO_DENOISE_PARAMS = {
        'luma_spatial': 4.0,
        'chroma_spatial': 3.0,
        'luma_tmp': 6.0,
        'chroma_tmp': 4.5
    }
    
    DEFAULT_AUDIO_DENOISE_PARAMS = {
        's': 10.0,
        'p': 0.007,
        'r': 0.015
    }
    
    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
        self.ffprobe_path = self._find_ffprobe()
    
    def _find_ffmpeg(self) -> str:
        return getattr(settings, 'FFMPEG_PATH', 'ffmpeg')
    
    def _find_ffprobe(self) -> str:
        return getattr(settings, 'FFPROBE_PATH', 'ffprobe')
    
    def get_video_info(self, input_path: str) -> Optional[Dict]:
        """获取视频文件信息"""
        if not os.path.exists(input_path):
            logger.error(f"文件不存在: {input_path}")
            return None
        
        cmd = [
            self.ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            input_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                logger.error(f"ffprobe 执行失败: {result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            logger.error("ffprobe 执行超时")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"解析 ffprobe 输出失败: {e}")
            return None
        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            return None
    
    def get_duration(self, input_path: str) -> Optional[float]:
        """获取视频时长(秒)"""
        info = self.get_video_info(input_path)
        if info and 'format' in info:
            return float(info['format'].get('duration', 0))
        return None
    
    def build_denoise_filter(
        self,
        video_denoise: bool = True,
        audio_denoise: bool = True,
        video_params: Optional[Dict] = None,
        audio_params: Optional[Dict] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """构建降噪滤镜"""
        video_filter = None
        audio_filter = None
        
        if video_denoise:
            params = {**self.DEFAULT_VIDEO_DENOISE_PARAMS, **(video_params or {})}
            video_filter = (
                f"hqdn3d={params['luma_spatial']}:"
                f"{params['chroma_spatial']}:"
                f"{params['luma_tmp']}:"
                f"{params['chroma_tmp']}"
            )
        
        if audio_denoise:
            params = {**self.DEFAULT_AUDIO_DENOISE_PARAMS, **(audio_params or {})}
            audio_filter = f"anlmdn=s={params['s']}:p={params['p']}:r={params['r']}"
        
        return video_filter, audio_filter
    
    def build_transcode_command(
        self,
        input_path: str,
        output_path: str,
        crf: int = 28,
        video_denoise: bool = True,
        audio_denoise: bool = True,
        video_denoise_params: Optional[Dict] = None,
        audio_denoise_params: Optional[Dict] = None,
        preset: str = 'medium'
    ) -> list:
        """构建转码命令"""
        cmd = [
            self.ffmpeg_path,
            '-i', input_path,
            '-y',
        ]
        
        video_filter, audio_filter = self.build_denoise_filter(
            video_denoise=video_denoise,
            audio_denoise=audio_denoise,
            video_params=video_denoise_params,
            audio_params=audio_denoise_params
        )
        
        if video_filter:
            cmd.extend(['-vf', video_filter])
        
        if audio_filter:
            cmd.extend(['-af', audio_filter])
        
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', str(crf),
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            output_path
        ])
        
        return cmd
    
    def transcode(
        self,
        input_path: str,
        output_path: str,
        crf: int = 28,
        video_denoise: bool = True,
        audio_denoise: bool = True,
        video_denoise_params: Optional[Dict] = None,
        audio_denoise_params: Optional[Dict] = None,
        progress_callback=None,
        timeout_seconds=None,
        stall_timeout_seconds=None,
        cancellation_check=None,
    ) -> Tuple[bool, str]:
        """
        执行视频转码
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            crf: 视频质量 (0-51, 值越大压缩率越高)
            video_denoise: 是否启用视频降噪
            audio_denoise: 是否启用音频降噪
            progress_callback: 进度回调函数 callback(progress: int)
        
        Returns:
            (success: bool, message: str)
        """
        if not os.path.exists(input_path):
            return False, f"输入文件不存在: {input_path}"
        
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        duration = self.get_duration(input_path)
        
        cmd = self.build_transcode_command(
            input_path=input_path,
            output_path=output_path,
            crf=crf,
            video_denoise=video_denoise,
            audio_denoise=audio_denoise,
            video_denoise_params=video_denoise_params,
            audio_denoise_params=audio_denoise_params
        )
        
        deadline = float(timeout_seconds or getattr(settings, 'MEDIA_TRANSCODE_TIMEOUT_SECONDS', 600))
        stall_deadline = float(stall_timeout_seconds or getattr(settings, 'MEDIA_TRANSCODE_STALL_SECONDS', 120))
        if not 0 < deadline <= 3600 or not 0 < stall_deadline <= 3600:
            raise ValueError('视频转码超时必须在 0 到 3600 秒之间')
        cmd[1:1] = ['-nostdin', '-progress', 'pipe:2', '-nostats']
        process = None
        reader = None
        lines = queue.Queue(maxsize=128)
        stopped = threading.Event()
        finished = threading.Event()
        started = last_progress = time.monotonic()
        last_position = -1.0
        stderr_tail = []

        def read_stderr():
            try:
                for line in process.stderr:
                    while not stopped.is_set():
                        try:
                            lines.put(line, timeout=0.1)
                            break
                        except queue.Full:
                            continue
                    if stopped.is_set():
                        break
            finally:
                finished.set()

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                start_new_session=os.name != 'nt',
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            )
            reader = threading.Thread(target=read_stderr, daemon=True)
            reader.start()
            import re
            time_pattern = re.compile(r'(?:time=|out_time=)(\d+):(\d+):(\d+\.?\d*)')
            checked_at = 0.0
            while True:
                now = time.monotonic()
                if cancellation_check and now - checked_at >= 1:
                    cancellation_check()
                    checked_at = now
                if now - started >= deadline:
                    return False, '转码超时'
                if now - last_progress >= stall_deadline:
                    return False, '转码进度停滞'
                try:
                    line = lines.get(timeout=0.1)
                except queue.Empty:
                    if process.poll() is not None and finished.is_set():
                        break
                    continue
                stderr_tail = (stderr_tail + [line.strip()])[-20:]
                match = time_pattern.search(line)
                if match:
                    position = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
                    if position > last_position:
                        last_position = position
                        last_progress = now
                        if duration and progress_callback:
                            progress_callback(min(int(position / duration * 100), 99))
            process.wait(timeout=max(0.1, deadline - (time.monotonic() - started)))
            
            if process.returncode == 0:
                if progress_callback:
                    progress_callback(100)
                return True, "转码成功"
            else:
                stderr = "\n".join(stderr_tail)
                logger.error(f"FFmpeg 转码失败: {stderr}")
                return False, f"转码失败: {stderr[:500]}"
                
        except subprocess.TimeoutExpired:
            return False, "转码超时"
        except Exception as e:
            from core.operations import OperationCanceled, OperationLeaseLost
            if isinstance(e, (OperationCanceled, OperationLeaseLost)):
                raise
            logger.error(f"转码异常: {e}")
            return False, f"转码异常: {str(e)}"
        finally:
            stopped.set()
            if process is not None:
                self._terminate_process(process)
            if reader:
                reader.join(timeout=2)
            if process is not None and process.stderr and (not reader or not reader.is_alive()):
                process.stderr.close()

    @staticmethod
    def _terminate_process(process):
        """只终止本次任务创建的进程组，不能杀死其他视频任务。"""
        if process.poll() is not None:
            return
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            else:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            if os.name != 'nt':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait(timeout=3)
    
    def get_file_size(self, file_path: str) -> int:
        """获取文件大小"""
        if os.path.exists(file_path):
            return os.path.getsize(file_path)
        return 0


ffmpeg_service = FFmpegService()
