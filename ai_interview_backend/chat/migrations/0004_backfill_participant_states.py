from django.db import migrations


def backfill_states(apps, schema_editor):
    Conversation = apps.get_model('chat', 'Conversation')
    State = apps.get_model('chat', 'ConversationParticipantState')
    db_alias = schema_editor.connection.alias
    for conversation in Conversation.objects.using(db_alias).prefetch_related('participants').iterator(chunk_size=200):
        for user in conversation.participants.all():
            State.objects.using(db_alias).get_or_create(conversation_id=conversation.id, user_id=user.id)


class Migration(migrations.Migration):
    dependencies = [('chat', '0003_messageattachment_scan_detail_and_more')]
    operations = [migrations.RunPython(backfill_states, migrations.RunPython.noop)]
