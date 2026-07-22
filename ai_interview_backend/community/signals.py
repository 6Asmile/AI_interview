from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from blog.models import Post
from knowledge.models import KnowledgeDocument

from .models import CommunityTopicLink


def queue_public_search_rebuild():
    def enqueue():
        if not cache.add('community:search-rebuild-pending', '1', timeout=15):
            return
        try:
            from .tasks import rebuild_public_search_indexes
            rebuild_public_search_indexes.apply_async(countdown=3)
        except Exception:
            cache.delete('community:search-rebuild-pending')

    transaction.on_commit(enqueue)


@receiver([post_save, post_delete], sender=Post)
@receiver([post_save, post_delete], sender=KnowledgeDocument)
@receiver([post_save, post_delete], sender=CommunityTopicLink)
def public_content_changed(sender, instance, **kwargs):
    if kwargs.get('raw'):
        return
    queue_public_search_rebuild()
