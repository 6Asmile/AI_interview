import os
import logging
from django.db import transaction
from django.utils import timezone
from celery import shared_task
from .models import FileUploadTask, FileChunk, VideoTranscodeTask
from .services import ffmpeg_service

logger = logging.getLogger(__name__)


def _mark_transcode_failed(transcode_task: VideoTranscodeTask, message: str):
    transcode_task.status = VideoTranscodeTask.Status.FAILED
    transcode_task.error_message = message[:1000]
    transcode_task.save(update_fields=['status', 'error_message'])


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


@shared_task
def start_transcode_after_merge(merge_result: dict, transcode_task_id: str):
    """合并完成后补齐原始文件路径并启动转码。"""
    try:
        transcode_task = VideoTranscodeTask.objects.select_related('upload_task').get(id=transcode_task_id)
    except VideoTranscodeTask.DoesNotExist:
        logger.error(f"转码任务不存在: {transcode_task_id}")
        return {"success": False, "error": "转码任务不存在"}

    if not merge_result.get('success'):
        error = merge_result.get('error') or '分片合并失败，无法开始转码'
        _mark_transcode_failed(transcode_task, error)
        return {"success": False, "error": error}

    merged_file = merge_result.get('merged_file') or getattr(transcode_task.upload_task, 'merged_file_path', '')
    if not merged_file:
        error = '合并文件路径为空，无法开始转码'
        _mark_transcode_failed(transcode_task, error)
        return {"success": False, "error": error}

    with transaction.atomic():
        transcode_task = VideoTranscodeTask.objects.select_for_update().select_related('upload_task').get(
            id=transcode_task.id,
        )
        transcode_task.original_file = merged_file
        transcode_task.save(update_fields=['original_file'])
        from core.models import AsyncOperation
        from .operation_handlers import create_video_operation

        operation = AsyncOperation.objects.filter(
            user=transcode_task.user,
            operation_type='media.video_process',
            source_app='video_uploads',
            source_model='FileUploadTask',
            source_id=str(transcode_task.upload_task_id),
        ).exclude(status=AsyncOperation.Status.CANCELED).order_by('-created_at').first()
        if operation is None:
            operation = create_video_operation(
                user=transcode_task.user,
                upload_task=transcode_task.upload_task,
                transcode_task=transcode_task,
            )
    return {
        "success": True,
        "transcode_task_id": str(transcode_task.id),
        "operation_id": str(operation.id),
    }


@shared_task(bind=True, max_retries=2)
def transcode_video_task(self, transcode_task_id: str):
    """视频转码任务"""
    try:
        transcode_task = VideoTranscodeTask.objects.get(id=transcode_task_id)
    except VideoTranscodeTask.DoesNotExist:
        logger.error(f"转码任务不存在: {transcode_task_id}")
        return {"success": False, "error": "转码任务不存在"}
    
    input_path = transcode_task.original_file
    if not input_path and transcode_task.upload_task and transcode_task.upload_task.merged_file_path:
        input_path = transcode_task.upload_task.merged_file_path
        transcode_task.original_file = input_path

    if not input_path:
        error = "转码原始文件路径为空，请确认合并任务是否完成"
        _mark_transcode_failed(transcode_task, error)
        return {"success": False, "error": error}

    transcode_task.status = VideoTranscodeTask.Status.PROCESSING
    transcode_task.started_at = timezone.now()
    transcode_task.error_message = ''
    transcode_task.save()
    
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
