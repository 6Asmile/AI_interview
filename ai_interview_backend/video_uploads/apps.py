from django.apps import AppConfig


class VideoUploadsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'video_uploads'
    verbose_name = '视频上传管理'

    def ready(self):
        from . import operation_handlers  # noqa: F401
