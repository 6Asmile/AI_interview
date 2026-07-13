from rest_framework import serializers
from .models import FileUploadTask, FileChunk, VideoTranscodeTask


class FileUploadTaskSerializer(serializers.ModelSerializer):
    """文件上传任务序列化器"""
    progress_percent = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    
    class Meta:
        model = FileUploadTask
        fields = [
            'id', 'file_identifier', 'file_name', 'file_size',
            'total_chunks', 'uploaded_chunks', 'status',
            'progress_percent', 'is_completed', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'uploaded_chunks', 'status', 'created_at', 'updated_at']


class InitUploadSerializer(serializers.Serializer):
    """初始化上传任务序列化器"""
    file_identifier = serializers.CharField(
        max_length=64,
        help_text='文件MD5哈希值'
    )
    file_name = serializers.CharField(max_length=255)
    file_size = serializers.IntegerField(min_value=1)
    total_chunks = serializers.IntegerField(min_value=1)
    chunk_size = serializers.IntegerField(
        default=5 * 1024 * 1024,
        help_text='分片大小，默认5MB'
    )


class ChunkUploadSerializer(serializers.Serializer):
    """分片上传序列化器"""
    task_id = serializers.UUIDField()
    chunk_index = serializers.IntegerField(min_value=0)
    chunk_hash = serializers.CharField(max_length=64, required=False, default='')
    chunk = serializers.FileField()


class MergeChunksSerializer(serializers.Serializer):
    """合并分片序列化器"""
    task_id = serializers.UUIDField()
    enable_transcode = serializers.BooleanField(
        default=True,
        help_text='是否启用视频转码'
    )
    video_denoise = serializers.BooleanField(default=True)
    audio_denoise = serializers.BooleanField(default=True)
    crf = serializers.IntegerField(min_value=0, max_value=51, default=28)


class UploadProgressSerializer(serializers.Serializer):
    """上传进度查询序列化器"""
    file_identifier = serializers.CharField(max_length=64)


class FileChunkSerializer(serializers.ModelSerializer):
    """文件分片序列化器"""
    
    class Meta:
        model = FileChunk
        fields = ['chunk_index', 'chunk_size', 'chunk_hash', 'created_at']


class VideoTranscodeTaskSerializer(serializers.ModelSerializer):
    """视频转码任务序列化器"""
    compression_ratio = serializers.ReadOnlyField()
    
    class Meta:
        model = VideoTranscodeTask
        fields = [
            'id', 'original_file_name', 'original_size', 'original_duration',
            'transcoded_size', 'status', 'progress', 'error_message',
            'video_denoise', 'audio_denoise', 'crf',
            'compression_ratio', 'created_at', 'started_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'user', 'original_file', 'transcoded_file', 'original_duration',
            'transcoded_size', 'status', 'progress', 'error_message',
            'created_at', 'started_at', 'completed_at'
        ]


class TranscodeConfigSerializer(serializers.Serializer):
    """转码配置序列化器"""
    video_denoise = serializers.BooleanField(default=True)
    audio_denoise = serializers.BooleanField(default=True)
    crf = serializers.IntegerField(min_value=18, max_value=40, default=28)
    video_denoise_params = serializers.DictField(
        required=False,
        default={
            'luma_spatial': 4.0,
            'chroma_spatial': 3.0,
            'luma_tmp': 6.0,
            'chroma_tmp': 4.5
        }
    )
    audio_denoise_params = serializers.DictField(
        required=False,
        default={
            's': 10.0,
            'p': 0.007,
            'r': 0.015
        }
    )
