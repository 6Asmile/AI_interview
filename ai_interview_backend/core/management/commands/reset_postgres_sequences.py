from django.apps import apps
from django.core.management import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction


class Command(BaseCommand):
    help = 'Reset all PostgreSQL identity sequences after fixture import.'

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError(f'Expected PostgreSQL, connected to {connection.vendor}')
        models = [
            model
            for model in apps.get_models()
            if model._meta.managed and not model._meta.proxy
        ]
        statements = connection.ops.sequence_reset_sql(no_style(), models)
        with transaction.atomic(), connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        self.stdout.write(self.style.SUCCESS(f'Reset {len(statements)} PostgreSQL sequences.'))
