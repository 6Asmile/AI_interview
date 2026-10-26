import os
import logging
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.utils import timezone
from django.conf import settings
from django.db import transaction

from core.admission import admit_expensive_operation
from core.idempotency import run_idempotent

from .models import FileUploadTask, FileChunk, VideoTranscodeTask
from .serializers import (
    FileUploadTaskSerializer,
    InitUploadSerializer,
    ChunkUploadSerializer,
    MergeChunksSerializer,
    UploadProgressSerializer,
    VideoTranscodeTaskSerializer,
)
from .operation_handlers import create_video_operation

logger = logging.getLogger(__name__)


class InitUploadView(APIView):
    """初始化分片上传"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = InitUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file_identifier = serializer.validated_data['file_identifier']
        file_name = serializer.validated_data['file_name']
        file_size = serializer.validated_data['file_size']
        total_chunks = serializer.validated_data['total_chunks']
        chunk_size = serializer.validated_data.get('chunk_size', 5 * 1024 * 1024)
        
        existing_task = FileUploadTask.objects.filter(
            file_identifier=file_identifier
        ).first()
        
        if existing_task:
            if existing_task.status == FileUploadTask.Status.MERGED:
                return Response({
                    'exists': True,
                    'message': '文件已存在',
                    'task': FileUploadTaskSerializer(existing_task).data
                }, status=status.HTTP_200_OK)
            
            uploaded_chunk_indexes = list(
                existing_task.chunks.values_list('chunk_index', flat=True)
            )
            
            return Response({
                'exists': True,
                'message': '断点续传',
                'task_id': str(existing_task.id),
                'uploaded_chunks': uploaded_chunk_indexes,
                'task': FileUploadTaskSerializer(existing_task).data
            }, status=status.HTTP_200_OK)
        
        task = FileUploadTask.objects.create(
            user=request.user,
            file_identifier=file_identifier,
            file_name=file_name,
            file_size=file_size,
            total_chunks=total_chunks,
            chunk_size=chunk_size,
            status=FileUploadTask.Status.UPLOADING
        )
        
        return Response({
            'exists': False,
            'message': '新上传任务已创建',
            'task_id': str(task.id),
            'task': FileUploadTaskSerializer(task).data
        }, status=status.HTTP_201_CREATED)


class ChunkUploadView(APIView):
    """上传分片"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        serializer = ChunkUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        task_id = serializer.validated_data['task_id']
        chunk_index = serializer.validated_data['chunk_index']
        chunk_hash = serializer.validated_data.get('chunk_hash', '')
        chunk_file = serializer.validated_data['chunk']
        
        try:
            task = FileUploadTask.objects.get(id=task_id, user=request.user)
        except FileUploadTask.DoesNotExist:
            return Response({'error': '上传任务不存在'}, status=status.HTTP_404_NOT_FOUND)
        
        if task.status != FileUploadTask.Status.UPLOADING:
            return Response({'error': '上传任务状态异常'}, status=status.HTTP_400_BAD_REQUEST)
        
        if FileChunk.objects.filter(upload_task=task, chunk_index=chunk_index).exists():
            return Response({
                'message': '分片已存在',
                'chunk_index': chunk_index
            }, status=status.HTTP_200_OK)
        
        chunk_dir = os.path.join(
            settings.MEDIA_ROOT,
            'chunks',
            str(task.id)
        )
        os.makedirs(chunk_dir, exist_ok=True)
        
        chunk_path = os.path.join(chunk_dir, f'chunk_{chunk_index}')
        
        with open(chunk_path, 'wb') as f:
            for chunk in chunk_file.chunks():
                f.write(chunk)
        
        FileChunk.objects.create(
            upload_task=task,
            chunk_index=chunk_index,
            chunk_size=os.path.getsize(chunk_path),
            chunk_hash=chunk_hash,
            temp_path=chunk_path
        )
        
        task.uploaded_chunks = task.chunks.count()
        task.save()
        
        return Response({
            'message': '分片上传成功',
            'chunk_index': chunk_index,
            'progress': task.progress_percent
        }, status=status.HTTP_201_CREATED)


class MergeChunksView(APIView):
    """合并分片"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = MergeChunksSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        task_id = serializer.validated_data['task_id']
        enable_transcode = serializer.validated_data.get('enable_transcode', True)
        video_denoise = serializer.validated_data.get('video_denoise', True)
        audio_denoise = serializer.validated_data.get('audio_denoise', True)
        crf = serializer.validated_data.get('crf', 28)
        
        try:
            task = FileUploadTask.objects.get(id=task_id, user=request.user)
        except FileUploadTask.DoesNotExist:
            return Response({'error': '上传任务不存在'}, status=status.HTTP_404_NOT_FOUND)
        
        if not task.is_completed:
            return Response({
                'error': '分片未上传完成',
                'uploaded': task.uploaded_chunks,
                'total': task.total_chunks
            }, status=status.HTTP_400_BAD_REQUEST)
        
        def create():
            # Validate/claim Idempotency-Key before consuming scarce media
            # capacity. Invalid requests must not spend an admission token.
            admit_expensive_operation(request, scope='video-process')
            with transaction.atomic():
                locked_task = FileUploadTask.objects.select_for_update().get(
                    pk=task.pk,
                    user=request.user,
                )
                locked_task.status = FileUploadTask.Status.MERGING
                locked_task.save(update_fields=['status', 'updated_at'])
                transcode_task = None
                if enable_transcode:
                    transcode_task, _created = VideoTranscodeTask.objects.get_or_create(
                        user=request.user,
                        upload_task=locked_task,
                        defaults={
                            'original_file': '',
                            'original_file_name': locked_task.file_name,
                            'original_size': locked_task.file_size,
                            'video_denoise': video_denoise,
                            'audio_denoise': audio_denoise,
                            'crf': crf,
                            'status': VideoTranscodeTask.Status.PENDING,
                        },
                    )
                operation = create_video_operation(
                    user=request.user,
                    upload_task=locked_task,
                    transcode_task=transcode_task,
                )
            return Response({
                'operation_id': str(operation.pk),
                'status': 'accepted',
                'events_url': f'/api/v2/operations/{operation.pk}/events/',
                'result_url': f'/api/v2/operations/{operation.pk}/',
                # v1 aliases remain for two release cycles; they intentionally
                # expose the same authoritative Operation UUID.
                'task_id': str(locked_task.pk),
                'merge_task_id': str(operation.pk),
                'transcode_enabled': enable_transcode,
                'transcode_task_id': str(transcode_task.pk) if transcode_task else None,
            }, status=status.HTTP_202_ACCEPTED)

        return run_idempotent(
            request,
            f'video.merge:{task.pk}:{int(enable_transcode)}',
            create,
            required=True,
        )


class UploadProgressView(APIView):
    """查询上传进度"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        serializer = UploadProgressSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        file_identifier = serializer.validated_data['file_identifier']
        
        try:
            task = FileUploadTask.objects.get(
                file_identifier=file_identifier,
                user=request.user
            )
        except FileUploadTask.DoesNotExist:
            return Response({'error': '上传任务不存在'}, status=status.HTTP_404_NOT_FOUND)
        
        uploaded_chunk_indexes = list(
            task.chunks.values_list('chunk_index', flat=True)
        )
        
        return Response({
            'task': FileUploadTaskSerializer(task).data,
            'uploaded_chunks': uploaded_chunk_indexes
        }, status=status.HTTP_200_OK)


class FileUploadTaskViewSet(viewsets.ReadOnlyModelViewSet):
    """文件上传任务查询"""
    serializer_class = FileUploadTaskSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return FileUploadTask.objects.filter(user=self.request.user)


class VideoTranscodeTaskViewSet(viewsets.ReadOnlyModelViewSet):
    """视频转码任务查询"""
    serializer_class = VideoTranscodeTaskSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return VideoTranscodeTask.objects.filter(user=self.request.user)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        if instance.transcoded_file and os.path.exists(instance.transcoded_file):
            data['transcoded_url'] = request.build_absolute_uri(
                instance.transcoded_file.replace('\\', '/').replace('media/', '/media/')
            )
        
        return Response(data)
