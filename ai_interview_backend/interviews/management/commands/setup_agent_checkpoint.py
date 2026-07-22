from django.core.management.base import BaseCommand

from interviews.agent_v4.checkpoint import setup_checkpoint_schema


class Command(BaseCommand):
    help = 'Create or upgrade LangGraph checkpoint tables in AGENT_DATABASE_URL.'

    def handle(self, *args, **options):
        setup_checkpoint_schema()
        self.stdout.write(self.style.SUCCESS('LangGraph PostgreSQL checkpoint schema is ready.'))
