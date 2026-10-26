import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('careers', '0003_skilltaxonomy_jobtarget_jd_snapshot_hash_and_more'),
        ('resumes', '0009_resumeoperationrequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='resumesuggestion',
            name='job_target',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='resume_suggestions',
                to='careers.jobtarget',
            ),
        ),
        migrations.AddField(
            model_name='resumesuggestion',
            name='task_key',
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
        migrations.AlterField(
            model_name='resumeartifact',
            name='format',
            field=models.CharField(
                choices=[
                    ('preview', '预览图'),
                    ('pdf', 'PDF'),
                    ('png', 'PNG 长图'),
                    ('docx', 'DOCX'),
                    ('json', 'JSON Resume'),
                    ('markdown', 'Markdown'),
                ],
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name='resumevariant',
            constraint=models.UniqueConstraint(
                fields=('resume', 'version'),
                name='uniq_resume_variant_version',
            ),
        ),
    ]
