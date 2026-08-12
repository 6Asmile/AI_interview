from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.events import register_event_handler

from .models import GrowthEvent, ReputationLedger, StreakState


EFFECTIVE_EVENTS = {
    'job.match.completed',
    'interview.completed',
    'learning.task.completed',
    'application.status.changed',
    'community.content.published',
}


@register_event_handler('*', 'community.growth-projector')
def project_effective_growth(envelope):
    event_type = envelope.get('event_type')
    actor_id = envelope.get('actor_id')
    if event_type not in EFFECTIVE_EVENTS or not actor_id:
        return {'ignored': True}
    payload = envelope.get('payload') or {}
    source_id = payload.get('analysis_id') or payload.get('learning_task_id') or payload.get('application_id') or payload.get('content_id') or envelope['aggregate_id']
    effective_date = timezone.localdate()
    dedup_key = f'{event_type}:{envelope["aggregate_type"]}:{source_id}'
    with transaction.atomic():
        growth, created = GrowthEvent.objects.get_or_create(
            dedup_key=dedup_key,
            defaults={
                'user_id': actor_id,
                'event_type': event_type,
                'source_type': envelope['aggregate_type'],
                'source_id': str(source_id),
                'effective_date': effective_date,
            },
        )
        if not created:
            return {'duplicate': True}
        state, _ = StreakState.objects.select_for_update().get_or_create(user_id=actor_id)
        if state.last_effective_date == effective_date:
            pass
        elif state.last_effective_date == effective_date - timedelta(days=1):
            state.current_days += 1
        else:
            state.current_days = 1
        state.longest_days = max(state.longest_days, state.current_days)
        state.last_effective_date = effective_date
        state.save()
    return {'growth_event_id': str(growth.pk), 'current_streak': state.current_days}


@register_event_handler('community.content.published', 'community.search-projector')
def project_community_search(envelope):
    from .tasks import index_community_content
    content_id = (envelope.get('payload') or {}).get('content_id')
    if content_id:
        # Search is a reconstructible projection. Running it inside the leased
        # Inbox consumer makes the event, not an untracked Celery task ID, the
        # retry and deduplication authority.
        result = index_community_content.run(str(content_id))
        return {'content_id': content_id, **result}
    return {'content_id': content_id, 'indexed': False}


@register_event_handler('community.content.published', 'community.reputation-projector')
def project_content_reputation(envelope):
    actor_id = envelope.get('actor_id')
    content_id = (envelope.get('payload') or {}).get('content_id')
    if not actor_id or not content_id:
        return {'ignored': True}
    entry, created = ReputationLedger.objects.get_or_create(
        dedup_key=f'content.published:{content_id}',
        defaults={
            'user_id': actor_id,
            'event_type': 'content.published',
            'points': 5,
            'source_type': 'CommunityContent',
            'source_id': str(content_id),
        },
    )
    return {'reputation_entry_id': str(entry.pk), 'created': created}
