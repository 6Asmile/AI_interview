from django.db import models
from django.conf import settings
import uuid
import os


def get_chunk_upload_path(instance, filename):
    return f'chunks/{instance.upload_task.file_identifier}/{instance.chunk_index}'


def get_video_upload_path(instance, filename):
    return f'videos/original/{instance.id}/{filename}'


class FileUploadTask(models.Model):
    """大文件分片上传任务"""
    
    class Status(models.TextChoices):
        UPLOADING = 'uploading', '上传中'
        COMPLETED = 'completed', '上传完成'
        MERGING = 'merging', '合并中'
        MERGED = 'merged', '已合并'
        FAILED = 'failed', '失败'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='upload_tasks',
        verbose_name='所属用户'
    )
    
    file_identifier = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name='文件唯一标识',
        help_text='文件MD5哈希值，用于断点续传'
    )
    file_name = models.CharField(max_length=255, verbose_name='原始文件名')
    file_size = models.BigIntegerField(verbose_name='文件总大小(字节)')
    total_chunks = models.IntegerField(verbose_name='总分片数')
    chunk_size = models.IntegerField(verbose_name='分片大小(字节)', default=5 * 1024 * 1024)
    
    uploaded_chunks = models.IntegerField(default=0, verbose_name='已上传分片数')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADING,
        verbose_name='状态'
    )
    
    merged_file_path = models.CharField(max_length=512, blank=True, verbose_name='合并后文件路径')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '文件上传任务'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
    
    def __str__(self):
        return f'{self.file_name} ({self.get_status_display()})'
    
    @property
    def progress_percent(self):
        if self.total_chunks == 0:
            return 0
        return round((self.uploaded_chunks / self.total_chunks) * 100, 2)
    
    @property
    def is_completed(self):
        return self.uploaded_chunks >= self.total_chunks


class FileChunk(models.Model):
    """文件分片记录"""
    
    upload_task = models.ForeignKey(
        FileUploadTask,
        on_delete=models.CASCADE,
        related_name='chunks',
        verbose_name='所属上传任务'
    )
    chunk_index = models.IntegerField(verbose_name='分片序号', help_text='从0开始')
    chunk_size = models.IntegerField(verbose_name='分片大小(字节)')
    chunk_hash = models.CharField(max_length=64, blank=True, verbose_name='分片MD5')
    
    temp_path = models.CharField(max_length=512, verbose_name='临时存储路径')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='上传时间')
    
    class Meta:
        verbose_name = '文件分片'
        verbose_name_plural = verbose_name
        unique_together = ['upload_task', 'chunk_index']
        ordering = ['upload_task', 'chunk_index']
    
    def __str__(self):
        return f'分片 {self.chunk_index} - {self.upload_task.file_name}'


class VideoTranscodeTask(models.Model):
    """视频转码任务"""
    
    class Status(models.TextChoices):
        PENDING = 'pending', '等待中'
        PROCESSING = 'processing', '处理中'
        COMPLETED = 'completed', '已完成'
        FAILED = 'failed', '失败'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='transcode_tasks',
        verbose_name='所属用户'
    )
    upload_task = models.OneToOneField(
        FileUploadTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transcode_task',
        verbose_name='关联上传任务'
    )
    
    original_file = models.CharField(max_length=512, verbose_name='原始文件路径')
    original_file_name = models.CharField(max_length=255, verbose_name='原始文件名')
    original_size = models.BigIntegerField(verbose_name='原始文件大小(字节)')
    original_duration = models.FloatField(null=True, blank=True, verbose_name='原始视频时长(秒)')
    
    transcoded_file = models.CharField(max_length=512, blank=True, verbose_name='转码后文件路径')
    transcoded_size = models.BigIntegerField(null=True, blank=True, verbose_name='转码后文件大小(字节)')
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='状态'
    )
    progress = models.IntegerField(default=0, verbose_name='转码进度(0-100)')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    
    video_denoise = models.BooleanField(default=True, verbose_name='视频降噪')
    audio_denoise = models.BooleanField(default=True, verbose_name='音频降噪')
    
    video_denoise_params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='视频降噪参数',
        help_text='hqdn3d滤镜参数: luma_spatial, chroma_spatial, luma_tmp, chroma_tmp'
    )
    audio_denoise_params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='音频降噪参数',
        help_text='anlmdn滤镜参数: s, p, r'
    )
    
    crf = models.IntegerField(default=28, verbose_name='视频质量CRF值', help_text='范围0-51, 值越大压缩率越高')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始处理时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    
    class Meta:
        verbose_name = '视频转码任务'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
    
    def __str__(self):
        return f'{self.original_file_name} ({self.get_status_display()})'
    
    @property
    def compression_ratio(self):
        if self.original_size and self.transcoded_size and self.transcoded_size > 0:
            return round((1 - self.transcoded_size / self.original_size) * 100, 2)
        return None
