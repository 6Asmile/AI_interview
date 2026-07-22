from __future__ import annotations

import json
from pathlib import Path

from django.apps import apps
from django.core.management import BaseCommand, CommandError
from django.db import connection

from .cutover_profile import model_digest


class Command(BaseCommand):
    help = 'Verify PostgreSQL data against an export_postgres_cutover manifest.'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', required=True)
        parser.add_argument('--allow-non-postgresql', action='store_true')

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql' and not options['allow_non_postgresql']:
            raise CommandError(f'Expected PostgreSQL, connected to {connection.vendor}')

        manifest = json.loads(Path(options['manifest']).resolve().read_text(encoding='utf-8'))
        failures = []
        for label, expected in manifest['included_models'].items():
            model = apps.get_model(label)
            actual_count, actual_digest = model_digest(model)
            if actual_count != expected['count']:
                failures.append(f'{label}: count {actual_count} != {expected["count"]}')
            elif actual_digest != expected['sha256']:
                failures.append(f'{label}: content hash mismatch')

        connection.check_constraints()
        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(failure))
            raise CommandError(f'Cutover verification failed for {len(failures)} models')
        self.stdout.write(self.style.SUCCESS(
            f'PostgreSQL cutover verified for {len(manifest["included_models"])} models.'
        ))
