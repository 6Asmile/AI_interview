from urllib.parse import urlparse

from allauth.socialaccount.models import SocialApp
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Synchronize django.contrib.sites with PUBLIC_BACKEND_URL.'

    def handle(self, *args, **options):
        public_url = str(getattr(settings, 'PUBLIC_BACKEND_URL', '') or '').strip()
        parsed = urlparse(public_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise CommandError('PUBLIC_BACKEND_URL 必须是完整的 http(s) URL。')
        with transaction.atomic():
            site = Site.objects.select_for_update().filter(pk=settings.SITE_ID).first()
            domain_site = (
                Site.objects.select_for_update()
                .filter(domain=parsed.netloc)
                .exclude(pk=settings.SITE_ID)
                .first()
            )

            linked_app_ids = set()
            if site is not None:
                linked_app_ids.update(site.socialapp_set.values_list('id', flat=True))
            if domain_site is not None:
                linked_app_ids.update(domain_site.socialapp_set.values_list('id', flat=True))

            if site is None:
                # The fixture may have preserved the public Site under another PK.
                # Create the configured SITE_ID first, then merge its M2M links.
                site = Site.objects.create(
                    pk=settings.SITE_ID,
                    domain=f'pending-site-{settings.SITE_ID}.invalid',
                    name='iFaceoff',
                )
            if domain_site is not None:
                domain_site.delete()

            site.domain = parsed.netloc
            site.name = 'iFaceoff'
            site.save(update_fields=['domain', 'name'])

            apps = SocialApp.objects.filter(provider='github')
            linked_app_ids.update(apps.values_list('id', flat=True))
            for app in SocialApp.objects.filter(id__in=linked_app_ids):
                app.sites.add(site)
        self.stdout.write(self.style.SUCCESS(
            f'站点已同步为 {site.domain}，关联 GitHub SocialApp {apps.count()} 个。'
        ))
