from django.db import migrations


def backfill_versions(apps, schema_editor):
    Resume = apps.get_model('resumes', 'Resume')
    ResumeVersion = apps.get_model('resumes', 'ResumeVersion')
    db_alias = schema_editor.connection.alias
    for resume in Resume.objects.using(db_alias).all().iterator():
        if ResumeVersion.objects.using(db_alias).filter(resume_id=resume.id).exists():
            continue
        payload = {
            'basics': {
                'name': resume.full_name or '',
                'label': resume.job_title or '',
                'email': resume.email or '',
                'phone': resume.phone or '',
                'summary': resume.summary or '',
                'location': {'city': resume.city or ''},
                'profiles': [],
            },
            'work': [
                {
                    'name': item.company,
                    'position': item.position,
                    'startDate': str(item.start_date or ''),
                    'endDate': str(item.end_date or ''),
                    'summary': item.description,
                    'highlights': [],
                }
                for item in resume.work_experiences.all()
            ],
            'education': [
                {
                    'institution': item.school,
                    'area': item.major,
                    'studyType': item.degree,
                    'startDate': str(item.start_date or ''),
                    'endDate': str(item.end_date or ''),
                    'score': '',
                    'courses': [],
                }
                for item in resume.educations.all()
            ],
            'projects': [
                {
                    'name': item.project_name,
                    'description': item.description,
                    'startDate': str(item.start_date or ''),
                    'endDate': str(item.end_date or ''),
                    'roles': [item.role] if item.role else [],
                    'keywords': [],
                    'highlights': [],
                }
                for item in resume.project_experiences.all()
            ],
            'skills': [
                {'name': item.skill_name, 'level': item.proficiency, 'keywords': []}
                for item in resume.skills.all()
            ],
            'volunteer': [], 'awards': [], 'certificates': [], 'publications': [],
            'languages': [], 'interests': [], 'references': [],
            'meta': {'schemaVersion': '1.0.0'},
            'x-ifaceoff': {
                'legacyResumeId': resume.id,
                'template': resume.template_name,
                'legacyLayout': resume.content_json or {},
                'customSections': [],
            },
        }
        version = ResumeVersion.objects.using(db_alias).create(
            resume_id=resume.id,
            version_number=1,
            schema_version='1.0.0',
            resume_json=payload,
            layout_json=resume.content_json or {},
            evidence_snapshot=[],
            source='legacy_migration',
            change_summary='数据库迁移生成初始标准版本',
            created_by_id=resume.user_id,
        )
        Resume.objects.using(db_alias).filter(pk=resume.pk).update(current_version_id=version.id)


class Migration(migrations.Migration):
    dependencies = [('resumes', '0006_alter_education_options_and_more')]

    operations = [migrations.RunPython(backfill_versions, migrations.RunPython.noop)]
