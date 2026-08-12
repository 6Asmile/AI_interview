from django.apps import AppConfig


class ResumesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'resumes'

    def ready(self):
        from . import operation_handlers  # noqa: F401
