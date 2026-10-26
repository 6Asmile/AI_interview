"""One queue/worker contract for Windows development and Linux deployment."""
from django.conf import settings


# Long work never shares a consumer with interactive or recovery work.
ROLE_QUEUES = {
    'publisher': ('CELERY_PUBLISHER_QUEUE',),
    'agent': ('CELERY_AGENT_QUEUE',),
    'career': ('CELERY_CAREER_QUEUE',),
    'document': ('CELERY_DOCUMENT_QUEUE',),
    'resume-render': ('CELERY_RESUME_RENDER_QUEUE',),
    'resume-ai': ('CELERY_RESUME_AI_QUEUE',),
    'media': ('CELERY_MEDIA_QUEUE',),
    'moderation': ('CELERY_COMMUNITY_MODERATION_QUEUE',),
    'events': ('CELERY_EVENT_QUEUE',),
    'auxiliary': ('CELERY_DEFAULT_QUEUE', 'CELERY_NOTIFICATION_QUEUE', 'CELERY_SEARCH_QUEUE'),
}


def worker_queues(role):
    return tuple(getattr(settings, name) for name in ROLE_QUEUES[role])


def worker_arguments(role, *, pool='prefork', concurrency=1, hostname=None):
    if pool == 'solo' and concurrency != 1:
        raise ValueError('solo workers execute sequentially; use one process per role')
    arguments = [
        'worker', '-l', 'info', '--pool', pool,
        '--hostname', hostname or f'{role}@%h',
        '--queues', ','.join(worker_queues(role)),
        '--concurrency', str(concurrency), '--prefetch-multiplier', '1',
    ]
    if pool == 'prefork':
        arguments.extend(['--max-tasks-per-child', '100', '--max-memory-per-child', '1048576'])
    return arguments


def queue_for_scope(scope):
    """Admission is scoped to commands, never to unrelated domain events."""
    if scope in {'resume.preview', 'resume.export', 'resume.share_export'}:
        return settings.CELERY_RESUME_RENDER_QUEUE
    if scope in {'resume.quality', 'resume.quality_review', 'resume.suggestion'}:
        return settings.CELERY_RESUME_AI_QUEUE
    if scope.startswith('resume.import') or scope.startswith('knowledge'):
        return settings.CELERY_DOCUMENT_QUEUE
    if scope in {'video-process', 'media'} or scope.startswith('media.'):
        return settings.CELERY_MEDIA_QUEUE
    if scope.startswith('career') or scope in {'job-match', 'ability-snapshot', 'weekly-report'}:
        return settings.CELERY_CAREER_QUEUE
    if scope.startswith('community'):
        return settings.CELERY_COMMUNITY_MODERATION_QUEUE
    if scope.startswith('interview'):
        return settings.CELERY_AGENT_QUEUE
    return settings.CELERY_DEFAULT_QUEUE
