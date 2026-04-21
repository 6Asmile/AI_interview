from django.contrib import admin
from .models import FileUploadTask, FileChunk, VideoTranscodeTask


@admin.register(FileUploadTask)
class FileUploadTaskAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'file_name', 'file_size', 'total_chunks',
        'uploaded_chunks', 'status', 'progress_percent', 'created_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['file_name', 'file_identifier', 'user__username']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    def progress_percent(self, obj):
        return f'{obj.progress_percent}%'
    progress_percent.short_description = '进度'


@admin.register(FileChunk)
class FileChunkAdmin(admin.ModelAdmin):
    list_display = ['id', 'upload_task', 'chunk_index', 'chunk_size', 'created_at']
    list_filter = ['created_at']
    search_fields = ['upload_task__file_name']


@admin.register(VideoTranscodeTask)
class VideoTranscodeTaskAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'original_file_name', 'original_size',
        'transcoded_size', 'status', 'progress', 'compression_ratio', 'created_at'
    ]
    list_filter = ['status', 'video_denoise', 'audio_denoise', 'created_at']
    search_fields = ['original_file_name', 'user__username']
    readonly_fields = ['id', 'created_at', 'started_at', 'completed_at']
    
    def compression_ratio(self, obj):
        ratio = obj.compression_ratio
        return f'{ratio}%' if ratio is not None else '-'
    compression_ratio.short_description = '压缩率'
