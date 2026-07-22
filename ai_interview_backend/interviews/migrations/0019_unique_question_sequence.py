from django.db import migrations, models
from django.db.models import Count


def resequence_legacy_duplicate_questions(apps, schema_editor):
    question = apps.get_model('interviews', 'InterviewQuestion')
    session_ids = list(
        question.objects.values('session_id', 'sequence')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .values_list('session_id', flat=True)
        .distinct()
    )
    for session_id in session_ids:
        rows = question.objects.filter(session_id=session_id).order_by('created_at', 'id')
        for sequence, row in enumerate(rows, start=1):
            if row.sequence != sequence:
                question.objects.filter(id=row.id).update(sequence=sequence)


class Migration(migrations.Migration):
    dependencies = [('interviews', '0018_durable_agent_execution')]

    operations = [
        migrations.RunPython(resequence_legacy_duplicate_questions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='interviewquestion',
            constraint=models.UniqueConstraint(
                fields=('session', 'sequence'),
                name='uniq_interview_question_sequence',
            ),
        ),
    ]
