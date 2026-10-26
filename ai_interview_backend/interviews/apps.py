from django.apps import AppConfig


class InterviewsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'interviews'

    def ready(self):
        # Register allowlisted Operation handlers when Django loads the app.
        from . import operation_handlers  # noqa: F401
