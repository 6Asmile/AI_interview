from django.apps import AppConfig

class InteractionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'interactions'

    # 【核心新增】重写 ready 方法
    def ready(self):
        # 导入信号处理器，确保它们被注册
        import interactions.signals