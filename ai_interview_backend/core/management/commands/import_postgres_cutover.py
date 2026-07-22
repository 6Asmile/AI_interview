from pathlib import Path

from django.contrib.sites.models import Site
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection


class Command(BaseCommand):
    help = 'Reset the PostgreSQL business database and import a cutover fixture.'

    def add_arguments(self, parser):
        parser.add_argument('--fixture', required=True)
        parser.add_argument('--manifest')
        parser.add_argument('--confirm', action='store_true')

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError(f'Expected PostgreSQL, connected to {connection.vendor}')
        if not options['confirm']:
            raise CommandError('Pass --confirm to reset and import the PostgreSQL business database')

        fixture = Path(options['fixture']).resolve()
        if not fixture.exists():
            raise CommandError(f'Fixture does not exist: {fixture}')

        call_command('flush', interactive=False, verbosity=0)
        # post_migrate creates example.com; the source Site is restored by natural key.
        Site.objects.all().delete()
        call_command('loaddata', str(fixture), verbosity=1)
        call_command('reset_postgres_sequences')
        connection.check_constraints()
        if options.get('manifest'):
            call_command('verify_postgres_cutover', manifest=options['manifest'])
        self.stdout.write(self.style.SUCCESS('PostgreSQL business data import completed.'))
