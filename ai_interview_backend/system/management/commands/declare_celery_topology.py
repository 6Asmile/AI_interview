"""Declare or passively verify the versioned Celery queue topology."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ai_interview_backend.celery_app import app


class Command(BaseCommand):
    help = (
        'Declare all configured Celery queues and per-domain dead-letter queues. '
        'Queue names are versioned so this command never mutates legacy queues.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Passively verify queues instead of declaring them.',
        )
        parser.add_argument(
            '--max-retries',
            type=int,
            default=3,
            help='Maximum broker connection retries (default: 3).',
        )

    def handle(self, *args, **options):
        queues = tuple(settings.CELERY_TASK_QUEUES)
        check_only = bool(options['check'])
        connection = app.connection_for_write()
        channel = None
        try:
            connection.ensure_connection(max_retries=max(0, options['max_retries']))
            channel = connection.channel()
            for queue in queues:
                bound_queue = queue(channel)
                if check_only:
                    bound_queue.exchange.declare(passive=True)
                    bound_queue.queue_declare(passive=True)
                else:
                    bound_queue.declare()
        except Exception as exc:
            mode = 'verify' if check_only else 'declare'
            raise CommandError(
                f'Unable to {mode} Celery topology: {type(exc).__name__}'
            ) from exc
        finally:
            if channel is not None:
                channel.close()
            connection.release()

        mode = 'verified' if check_only else 'declared'
        self.stdout.write(self.style.SUCCESS(
            f'Celery topology {mode}: version={settings.CELERY_TOPOLOGY_VERSION}, '
            f'main={len(settings.CELERY_MAIN_QUEUE_NAMES)}, '
            f'dlq={len(settings.CELERY_DLQ_NAMES)}'
        ))
