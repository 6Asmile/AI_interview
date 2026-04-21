import os
import logging
from django.utils import timezone
from celery import shared_task
from .models import FileUploadTask, FileChunk, VideoTranscodeTask
from .services import ffmpeg_service

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def merge_chunks_task(self, task_id: str):
    """合并分片任务"""
    from django.core.files.storage import default_storage
    
    try:
        upload_task = FileUploadTask.objects.get(id=task_id)
    except FileUploadTask.DoesNotExist:
        logger.error(f"上传任务不存在: {task_id}")
        return {"success": False, "error": "上传任务不存在"}
    
    upload_task.status = FileUploadTask.Status.MERGING
    upload_task.save()
    
    chunks = FileChunk.objects.filter(upload_task=upload_task).order_by('chunk_index')
    
    if chunks.count() != upload_task.total_chunks:
        upload_task.status = FileUploadTask.Status.FAILED
        upload_task.save()
        return {"success": False, "error": "分片数量不完整"}
    
    output_dir = os.path.join('media', 'videos', 'merged', str(upload_task.id))
    output_path = os.path.join(output_dir, upload_task.file_name)
    
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        with open(output_path, 'wb') as output_file:
            for chunk in chunks:
                if os.path.exists(chunk.temp_path):
                    with open(chunk.temp_path, 'rb') as chunk_file:
                        output_file.write(chunk_file.read())
        
        upload_task.merged_file_path = output_path
        upload_task.status = FileUploadTask.Status.MERGED
        upload_task.save()
        
        for chunk in chunks:
            if os.path.exists(chunk.temp_path):
                os.remove(chunk.temp_path)
        
        logger.info(f"分片合并成功: {output_path}")
        return {"success": True, "merged_file": output_path}
        
    except Exception as e:
        logger.error(f"合并分片失败: {e}")
        upload_task.status = FileUploadTask.Status.FAILED
        upload_task.save()
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)
        
        return {"success": False, "error": str(e)}


@shared_task(bind=True, max_retries=2)
def transcode_video_task(self, transcode_task_id: str):
    """视频转码任务"""
    try:
        transcode_task = VideoTranscodeTask.objects.get(id=transcode_task_id)
    except VideoTranscodeTask.DoesNotExist:
        logger.error(f"转码任务不存在: {transcode_task_id}")
        return {"success": False, "error": "转码任务不存在"}
    
    transcode_task.status = VideoTranscodeTask.Status.PROCESSING
    transcode_task.started_at = timezone.now()
    transcode_task.save()
    
    input_path = transcode_task.original_file
    
    output_dir = os.path.join('media', 'videos', 'transcoded', str(transcode_task.id))
    os.makedirs(output_dir, exist_ok=True)
    
    name, ext = os.path.splitext(transcode_task.original_file_name)
    output_path = os.path.join(output_dir, f"{name}_transcoded.mp4")
    
    def update_progress(progress: int):
        transcode_task.progress = progress
        transcode_task.save(update_fields=['progress'])
    
    try:
        duration = ffmpeg_service.get_duration(input_path)
        if duration:
            transcode_task.original_duration = duration
            transcode_task.save(update_fields=['original_duration'])
        
        success, message = ffmpeg_service.transcode(
            input_path=input_path,
            output_path=output_path,
            crf=transcode_task.crf,
            video_denoise=transcode_task.video_denoise,
            audio_denoise=transcode_task.audio_denoise,
            video_denoise_params=transcode_task.video_denoise_params,
            audio_denoise_params=transcode_task.audio_denoise_params,
            progress_callback=update_progress
        )
        
        if success:
            transcode_task.transcoded_file = output_path
            transcode_task.transcoded_size = os.path.getsize(output_path)
            transcode_task.status = VideoTranscodeTask.Status.COMPLETED
            transcode_task.completed_at = timezone.now()
            transcode_task.save()
            
            logger.info(
                f"视频转码成功: {output_path}, "
                f"压缩率: {transcode_task.compression_ratio}%"
            )
            
            return {
                "success": True,
                "transcoded_file": output_path,
                "original_size": transcode_task.original_size,
                "transcoded_size": transcode_task.transcoded_size,
                "compression_ratio": transcode_task.compression_ratio
            }
        else:
            raise Exception(message)
            
    except Exception as e:
        logger.error(f"视频转码失败: {e}")
        transcode_task.status = VideoTranscodeTask.Status.FAILED
        transcode_task.error_message = str(e)[:1000]
        transcode_task.save()
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=120)
        
        return {"success": False, "error": str(e)}


@shared_task
def cleanup_temp_files():
    """清理临时文件任务"""
    from django.utils import timezone
    from datetime import timedelta
    
    threshold = timezone.now() - timedelta(days=1)
    
    old_tasks = FileUploadTask.objects.filter(
        status__in=[FileUploadTask.Status.COMPLETED, FileUploadTask.Status.FAILED],
        updated_at__lt=threshold
    )
    
    for task in old_tasks:
        chunks = FileChunk.objects.filter(upload_task=task)
        for chunk in chunks:
            if os.path.exists(chunk.temp_path):
                try:
                    os.remove(chunk.temp_path)
                except Exception as e:
                    logger.warning(f"删除临时文件失败: {chunk.temp_path}, {e}")
    
    logger.info(f"清理了 {old_tasks.count()} 个过期上传任务的临时文件")
    return {"cleaned": old_tasks.count()}
