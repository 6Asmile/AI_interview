from django.apps import AppConfig


class CareersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'careers'
    verbose_name = '求职工作台'

    def ready(self):
        from . import events  # noqa: F401
