import hashlib
import re

from django.db import migrations


def redact_legacy(text):
    value = text or ''
    for pattern, replacement in (
        (r'(?<!\d)1[3-9]\d{9}(?!\d)', '[PHONE_REDACTED]'),
        (r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', '[EMAIL_REDACTED]'),
        (r'(?<!\d)\d{17}[\dXx](?!\d)', '[NATIONAL_ID_REDACTED]'),
        (r'[\u4e00-\u9fff]{2,}(?:路|街|巷|弄)\d{1,5}号', '[PRECISE_ADDRESS_REDACTED]'),
    ):
        value = re.sub(pattern, replacement, value, flags=re.I)
    return value


def forwards(apps, schema_editor):
    Post = apps.get_model('blog', 'Post')
    Comment = apps.get_model('blog', 'Comment')
    DailyPostStats = apps.get_model('blog', 'DailyPostStats')
    LegacyLike = apps.get_model('interactions', 'Like')
    LegacyBookmark = apps.get_model('interactions', 'Bookmark')
    LegacyFollow = apps.get_model('interactions', 'Follow')
    CommunityContent = apps.get_model('community', 'CommunityContent')
    ContentRevision = apps.get_model('community', 'ContentRevision')
    CommunityComment = apps.get_model('community', 'CommunityComment')
    Reaction = apps.get_model('community', 'Reaction')
    Bookmark = apps.get_model('community', 'Bookmark')
    UserFollow = apps.get_model('community', 'UserFollow')
    ContentDailyMetric = apps.get_model('community', 'ContentDailyMetric')

    status_map = {
        'draft': 'draft',
        'pending': 'pending',
        'published': 'published',
        'private': 'hidden',
    }
    for post in Post.objects.all().iterator(chunk_size=500):
        content, _ = CommunityContent.objects.get_or_create(
            legacy_source='blog.Post',
            legacy_id=str(post.pk),
            defaults={
                'author_id': post.author_id,
                'content_type': 'article',
                'title': post.title,
                'excerpt': post.excerpt,
                'status': status_map.get(post.status, 'draft'),
                'quality_score': 10 if post.is_featured else 0,
                'risk_level': 'low',
                'published_at': post.published_at,
            },
        )
        revision, _ = ContentRevision.objects.get_or_create(
            content_id=content.pk,
            version=1,
            defaults={
                'title': post.title,
                'body': post.content,
                'redacted_body': redact_legacy(post.content),
                'body_hash': hashlib.sha256(f'{post.title}\0{post.content}'.encode('utf-8')).hexdigest(),
                'created_by_id': post.author_id,
            },
        )
        if content.current_revision_id != revision.pk:
            CommunityContent.objects.filter(pk=content.pk).update(current_revision_id=revision.pk)

    for comment in Comment.objects.filter(parent__isnull=True).iterator(chunk_size=500):
        content = CommunityContent.objects.get(legacy_source='blog.Post', legacy_id=str(comment.post_id))
        CommunityComment.objects.get_or_create(
            legacy_source='blog.Comment',
            legacy_id=str(comment.pk),
            defaults={
                'content_id': content.pk,
                'author_id': comment.author_id,
                'body': comment.content,
                'status': 'published',
            },
        )
    for comment in Comment.objects.filter(parent__isnull=False).iterator(chunk_size=500):
        content = CommunityContent.objects.get(legacy_source='blog.Post', legacy_id=str(comment.post_id))
        parent = CommunityComment.objects.filter(
            legacy_source='blog.Comment', legacy_id=str(comment.parent_id),
        ).first()
        CommunityComment.objects.get_or_create(
            legacy_source='blog.Comment',
            legacy_id=str(comment.pk),
            defaults={
                'content_id': content.pk,
                'author_id': comment.author_id,
                'parent_id': parent.pk if parent else None,
                'body': comment.content,
                'status': 'published',
            },
        )

    for item in LegacyLike.objects.all().iterator(chunk_size=1000):
        content = CommunityContent.objects.filter(legacy_source='blog.Post', legacy_id=str(item.post_id)).first()
        if content:
            Reaction.objects.get_or_create(user_id=item.user_id, content_id=content.pk, kind='like')
    for item in LegacyBookmark.objects.all().iterator(chunk_size=1000):
        content = CommunityContent.objects.filter(legacy_source='blog.Post', legacy_id=str(item.post_id)).first()
        if content:
            Bookmark.objects.get_or_create(user_id=item.user_id, content_id=content.pk)
    for item in LegacyFollow.objects.all().iterator(chunk_size=1000):
        UserFollow.objects.get_or_create(follower_id=item.follower_id, followed_id=item.followed_id)
    for item in DailyPostStats.objects.all().iterator(chunk_size=1000):
        content = CommunityContent.objects.filter(legacy_source='blog.Post', legacy_id=str(item.post_id)).first()
        if content:
            ContentDailyMetric.objects.update_or_create(
                content_id=content.pk,
                date=item.date,
                defaults={'views': item.views, 'reactions': item.likes},
            )


class Migration(migrations.Migration):
    dependencies = [
        ('blog', '0005_backfill_counts'),
        ('interactions', '0001_initial'),
        ('community', '0003_contentdailymetric'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
