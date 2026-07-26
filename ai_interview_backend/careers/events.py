from core.events import register_event_handler

from .models import AbilitySnapshot, JobMatchAnalysis
from .services import stable_hash


@register_event_handler('job.match.completed', 'careers.ability-projector')
def project_job_match_ability(envelope):
    analysis_id = (envelope.get('payload') or {}).get('analysis_id')
    analysis = JobMatchAnalysis.objects.filter(pk=analysis_id).first()
    if not analysis:
        return {'ignored': True}
    snapshot, created = AbilitySnapshot.objects.get_or_create(
        user=analysis.user,
        trigger=f'job_match:{analysis.pk}',
        defaults={
            'dimensions': {
                'job_match_score': float(analysis.score),
                **(analysis.dimensions or {}),
            },
            'source_refs': [{'type': 'JobMatchAnalysis', 'id': str(analysis.pk)}],
            'config_hash': analysis.config_hash,
        },
    )
    return {'ability_snapshot_id': str(snapshot.pk), 'created': created}


@register_event_handler('interview.completed', 'careers.interview-ability-projector')
def project_interview_ability(envelope):
    from interviews.models import InterviewSession
    session_id = (envelope.get('payload') or {}).get('interview_session_id')
    session = InterviewSession.objects.filter(pk=session_id).first()
    if not session:
        return {'ignored': True}
    report = session.report or {}
    dimensions = report.get('ability_scores') or {'overall_score': report.get('overall_score') or 0}
    snapshot, created = AbilitySnapshot.objects.get_or_create(
        user=session.user,
        trigger=f'interview:{session.pk}',
        defaults={
            'dimensions': dimensions,
            'source_refs': [{'type': 'InterviewSession', 'id': str(session.pk)}],
            'config_hash': stable_hash(session.agent_config_snapshot or session.template_snapshot or {}),
        },
    )
    return {'ability_snapshot_id': str(snapshot.pk), 'created': created}
