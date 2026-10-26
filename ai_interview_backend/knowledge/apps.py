from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'knowledge'
    verbose_name = '面试知识库'

    def ready(self):
        # Importing registers allowlisted Operation handlers.  The broker never
        # receives a caller-controlled task name.
        from . import operation_handlers  # noqa: F401
