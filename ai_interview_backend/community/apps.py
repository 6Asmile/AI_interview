from django.apps import AppConfig


class CommunityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'community'
    verbose_name = '技术社区集成'

    def ready(self):
        from . import signals  # noqa: F401
        from . import events  # noqa: F401
