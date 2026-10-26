"""Read-only audit: legacy rows have no dispatch and must not be auto-executed."""
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import AsyncOperation


class Command(BaseCommand):
    help = '只读检查旧任务投影，输出计数而不重跑外部任务或公开业务正文。'

    def handle(self, **options):
        from django.db.models import Count
        rows = AsyncOperation.objects.filter(
            dispatches__isnull=True, status__in=['pending', 'claimed', 'running', 'retrying'],
        )
        for row in rows.values('operation_type', 'status').annotate(total=Count('id')).order_by('operation_type'):
            self.stdout.write(f"{row['operation_type']} {row['status']}: {row['total']}")
        expired = rows.filter(lease_expires_at__lte=timezone.now()).count()
        self.stdout.write(f'过期旧租约: {expired}；旧投影总数: {rows.count()}')
        self.stdout.write('不自动重跑：需确认领域结果、输入文件及旧队列已排空，再通过对应业务入口重试。')
