"""Durable media Operations for chunk merging and optional transcoding."""

from __future__ import annotations

import os
import threading

from celery.exceptions import Retry
from django.conf import settings

from core.operation_registry import OperationHandlerResult, register_operation_handler
from core.operations import (
    RetryableOperationError,
    TerminalOperationError,
    create_operation_with_dispatch,
)

from .models import FileUploadTask, VideoTranscodeTask
from .tasks import merge_chunks_task, transcode_video_task


VIDEO_PROCESS_OPERATION = 'media.video_process'


def create_video_operation(*, user, upload_task, transcode_task=None):
    return create_operation_with_dispatch(
        user=user,
        operation_type=VIDEO_PROCESS_OPERATION,
        source_app='video_uploads',
        source_model='FileUploadTask',
        source_id=str(upload_task.pk),
        input_type='video_uploads.FileUploadTask',
        input_id=str(upload_task.pk),
        input_version=str(upload_task.file_identifier),
        input_hash=str(upload_task.file_identifier)[:64],
        title=f'处理面试视频：{upload_task.file_name}',
        metadata={
            'transcode_task_id': str(transcode_task.pk) if transcode_task else '',
            'transcode_enabled': bool(transcode_task),
        },
        max_attempts=5,
        queue=settings.CELERY_MEDIA_QUEUE,
        routing_key='media',
    )


class _HeartbeatGuard:
    """Renew the PostgreSQL lease while FFmpeg performs a blocking call."""

    def __init__(self, context, interval=45):
        self.context = context
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self.stop_event.wait(self.interval):
            if not self.context.heartbeat():
                return

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.stop_event.set()
        self.thread.join(timeout=2)


def _retry_or_raise(exc: Exception):
    if isinstance(exc, FileNotFoundError):
        raise TerminalOperationError('media_input_missing', str(exc)) from exc
    if isinstance(exc, (Retry, ConnectionError, TimeoutError, OSError)):
        raise RetryableOperationError(
            'media_processing_temporarily_unavailable',
            str(exc),
            retry_after_seconds=30,
        ) from exc
    raise TerminalOperationError('media_processing_failed', str(exc)) from exc


@register_operation_handler(VIDEO_PROCESS_OPERATION)
def process_video(context):
    operation = context.get_operation()
    try:
        upload_task = FileUploadTask.objects.get(pk=operation.input_id)
    except FileUploadTask.DoesNotExist as exc:
        raise TerminalOperationError('media_upload_not_found') from exc
    if upload_task.user_id != operation.user_id:
        raise TerminalOperationError('media_input_forbidden')
    context.raise_if_canceled()

    if (
        upload_task.status == FileUploadTask.Status.MERGED
        and upload_task.merged_file_path
        and os.path.exists(upload_task.merged_file_path)
    ):
        merge_result = {'success': True, 'merged_file': upload_task.merged_file_path}
    else:
        try:
            merge_result = merge_chunks_task.run(str(upload_task.pk))
        except Exception as exc:
            _retry_or_raise(exc)
    if not merge_result.get('success'):
        raise TerminalOperationError(
            'media_merge_rejected',
            str(merge_result.get('error') or 'media_merge_failed'),
        )
    context.heartbeat()
    context.raise_if_canceled()

    transcode_task_id = str((operation.metadata or {}).get('transcode_task_id') or '')
    if not transcode_task_id:
        return OperationHandlerResult(
            result_type='video_uploads.FileUploadTask',
            result_id=str(upload_task.pk),
            result={'transcoded': False},
        )

    try:
        transcode_task = VideoTranscodeTask.objects.get(pk=transcode_task_id, user=operation.user)
    except VideoTranscodeTask.DoesNotExist as exc:
        raise TerminalOperationError('media_transcode_task_not_found') from exc
    if transcode_task.status == VideoTranscodeTask.Status.COMPLETED and transcode_task.transcoded_file:
        transcode_result = {'success': True}
    else:
        transcode_task.original_file = merge_result['merged_file']
        transcode_task.save(update_fields=['original_file'])
        try:
            with _HeartbeatGuard(context):
                transcode_result = transcode_video_task.run(str(transcode_task.pk))
        except Exception as exc:
            _retry_or_raise(exc)
    if not transcode_result.get('success'):
        raise TerminalOperationError(
            'media_transcode_rejected',
            str(transcode_result.get('error') or 'media_transcode_failed'),
        )
    context.raise_if_canceled()
    return OperationHandlerResult(
        result_type='video_uploads.VideoTranscodeTask',
        result_id=str(transcode_task.pk),
        result={'upload_task_id': str(upload_task.pk), 'transcoded': True},
    )
