from django.core.management.base import BaseCommand, CommandError

from core.worker_roles import ROLE_QUEUES, worker_arguments


class Command(BaseCommand):
    help = 'Start exactly one worker role using the configured queue topology.'

    def add_arguments(self, parser):
        parser.add_argument('--role', choices=tuple(ROLE_QUEUES), required=True)
        parser.add_argument('--pool', choices=('solo', 'prefork', 'threads'), default='prefork')
        parser.add_argument('--concurrency', type=int, default=1)
        parser.add_argument('--hostname')

    def handle(self, **options):
        from ai_interview_backend.celery_app import app

        if not 1 <= options['concurrency'] <= 64:
            raise CommandError('concurrency must be between 1 and 64')
        try:
            arguments = worker_arguments(
                options['role'], pool=options['pool'],
                concurrency=options['concurrency'], hostname=options['hostname'],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        app.worker_main(arguments)
