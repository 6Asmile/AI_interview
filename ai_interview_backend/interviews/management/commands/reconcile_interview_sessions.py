from datetime import timedelta

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from interviews.models import InterviewSession
class Command(BaseCommand):
    help = '检查并可选关闭长期无活动的运行中面试，同时修复用户的 Redis 会话缓存。'

    def add_arguments(self, parser):
        parser.add_argument('--older-than-minutes', type=int, default=120)
        parser.add_argument('--apply', action='store_true', help='实际关闭陈旧会话；默认仅 dry-run。')

    def handle(self, *args, **options):
        threshold = timezone.now() - timedelta(minutes=max(5, options['older_than_minutes']))
        stale = InterviewSession.objects.filter(
            status=InterviewSession.Status.RUNNING,
            last_activity_at__lt=threshold,
        ).select_related('user').order_by('user_id', '-last_activity_at')
        stale_ids = list(stale.values_list('id', flat=True))
        self.stdout.write(f'发现 {len(stale_ids)} 个陈旧运行会话。')
        if options['apply'] and stale_ids:
            now = timezone.now()
            with transaction.atomic():
                updated = InterviewSession.objects.select_for_update().filter(id__in=stale_ids).update(
                    status=InterviewSession.Status.CANCELED,
                    finished_at=now,
                    last_activity_at=now,
                )
            self.stdout.write(self.style.SUCCESS(f'已关闭 {updated} 个陈旧会话。'))

        user_ids = set(InterviewSession.objects.filter(status=InterviewSession.Status.RUNNING).values_list('user_id', flat=True))
        for user_id in user_ids:
            latest = InterviewSession.objects.filter(
                user_id=user_id,
                status=InterviewSession.Status.RUNNING,
            ).order_by('-last_activity_at', '-updated_at').first()
            if latest and options['apply']:
                cache.set(f'user_{user_id}_unfinished_interview', str(latest.id), timeout=7200)
        self.stdout.write('dry-run 完成，使用 --apply 才会修改数据库和缓存。' if not options['apply'] else '缓存对账完成。')
