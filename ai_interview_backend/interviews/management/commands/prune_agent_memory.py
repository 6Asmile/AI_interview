from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from interviews.agent_v4.checkpoint import postgres_checkpointer
from interviews.models import InterviewAgentExecution, InterviewAgentMemoryEvent, InterviewSession


class Command(BaseCommand):
    help = 'Prune expired Agent memory and old LangGraph checkpoints. Dry-run by default.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument(
            '--memory-days',
            type=int,
            default=getattr(settings, 'AGENT_MEMORY_EVENT_RETENTION_DAYS', 30),
        )
        parser.add_argument(
            '--checkpoint-days',
            type=int,
            default=getattr(settings, 'AGENT_CHECKPOINT_RETENTION_DAYS', 30),
        )

    def handle(self, *args, **options):
        now = timezone.now()
        memory_cutoff = now - timedelta(days=max(options['memory_days'], 1))
        checkpoint_cutoff = now - timedelta(days=max(options['checkpoint_days'], 1))
        memory = InterviewAgentMemoryEvent.objects.filter(created_at__lt=memory_cutoff).filter(
            expires_at__isnull=False,
            expires_at__lte=now,
        )
        sessions = InterviewSession.objects.filter(
            status__in=(InterviewSession.Status.FINISHED, InterviewSession.Status.CANCELED),
            updated_at__lt=checkpoint_cutoff,
        ).values_list('id', flat=True)
        session_ids = [str(session_id) for session_id in sessions.iterator()]
        execution_keys = list(
            InterviewAgentExecution.objects.filter(session_id__in=session_ids).values_list(
                'session_id', 'run_id'
            )
        )
        checkpoint_threads = set(session_ids)
        for session_id, run_id in execution_keys:
            for phase in ('prepare', 'finalize', 'report'):
                checkpoint_threads.add(f'{session_id}.{run_id}.{phase}')

        self.stdout.write(
            f"memory_events={memory.count()} checkpoint_threads={len(checkpoint_threads)} apply={options['apply']}"
        )
        if not options['apply']:
            return

        memory.delete()
        with postgres_checkpointer() as saver:
            for thread_id in checkpoint_threads:
                saver.delete_thread(thread_id)
        self.stdout.write(self.style.SUCCESS('Agent memory and checkpoints pruned.'))
