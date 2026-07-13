from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any


JSON_RESUME_SCHEMA_VERSION = '1.0.0'
ARRAY_SECTIONS = ('work', 'volunteer', 'education', 'awards', 'certificates', 'publications', 'skills', 'languages', 'interests', 'references', 'projects')


def _date(value: date | str | None) -> str:
    if not value:
        return ''
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def normalize_json_resume(payload: dict | None) -> dict:
    data = deepcopy(payload) if isinstance(payload, dict) else {}
    data['basics'] = data.get('basics') if isinstance(data.get('basics'), dict) else {}
    for section in ARRAY_SECTIONS:
        data[section] = data.get(section) if isinstance(data.get(section), list) else []
    data['meta'] = data.get('meta') if isinstance(data.get('meta'), dict) else {}
    data['meta']['schemaVersion'] = JSON_RESUME_SCHEMA_VERSION
    extension = data.get('x-ifaceoff')
    data['x-ifaceoff'] = extension if isinstance(extension, dict) else {}
    return data


def _legacy_modules(content_json: Any) -> list[dict]:
    if isinstance(content_json, list):
        return [item for item in content_json if isinstance(item, dict)]
    if isinstance(content_json, dict):
        modules = []
        for zone in ('sidebar', 'main'):
            value = content_json.get(zone)
            if isinstance(value, list):
                modules.extend(item for item in value if isinstance(item, dict))
        return modules
    return []


def legacy_resume_to_json_resume(resume, content_json: dict | list | None = None) -> dict:
    data = normalize_json_resume({})
    data['basics'] = {
        'name': resume.full_name or '',
        'label': resume.job_title or '',
        'email': resume.email or '',
        'phone': resume.phone or '',
        'summary': resume.summary or '',
        'location': {'city': resume.city or ''},
        'profiles': [],
    }
    data['education'] = [
        {
            'institution': item.school,
            'area': item.major,
            'studyType': item.degree,
            'startDate': _date(item.start_date),
            'endDate': _date(item.end_date),
            'score': '',
            'courses': [],
        }
        for item in resume.educations.all()
    ]
    data['work'] = [
        {
            'name': item.company,
            'position': item.position,
            'startDate': _date(item.start_date),
            'endDate': _date(item.end_date),
            'summary': item.description,
            'highlights': [],
        }
        for item in resume.work_experiences.all()
    ]
    data['projects'] = [
        {
            'name': item.project_name,
            'description': item.description,
            'startDate': _date(item.start_date),
            'endDate': _date(item.end_date),
            'roles': [item.role] if item.role else [],
            'keywords': [],
            'highlights': [],
        }
        for item in resume.project_experiences.all()
    ]
    data['skills'] = [
        {'name': item.skill_name, 'level': item.proficiency, 'keywords': []}
        for item in resume.skills.all()
    ]

    custom_sections = []
    for module in _legacy_modules(content_json if content_json is not None else resume.content_json):
        module_type = module.get('moduleType') or ''
        props = module.get('props') if isinstance(module.get('props'), dict) else {}
        if module_type == 'BaseInfo':
            data['basics']['name'] = props.get('name') or data['basics']['name']
            for item in props.get('items') or []:
                label = str(item.get('label') or '').lower()
                value = str(item.get('value') or '')
                if '邮箱' in label or 'email' in label:
                    data['basics']['email'] = value
                elif '电话' in label or 'phone' in label:
                    data['basics']['phone'] = value
        elif module_type == 'Summary':
            data['basics']['summary'] = props.get('summary') or data['basics']['summary']
        elif module_type == 'Education' and not data['education']:
            for item in props.get('educations') or []:
                dates = item.get('dateRange') or []
                data['education'].append({
                    'institution': item.get('school', ''), 'area': item.get('major', ''),
                    'studyType': item.get('degree', ''), 'startDate': dates[0] if dates else '',
                    'endDate': dates[1] if len(dates) > 1 and dates[1] else '',
                    'score': '', 'courses': [], 'summary': item.get('description', ''),
                })
        elif module_type == 'WorkExp' and not data['work']:
            for item in props.get('experiences') or []:
                dates = item.get('dateRange') or []
                data['work'].append({
                    'name': item.get('company', ''), 'position': item.get('position', ''),
                    'startDate': dates[0] if dates else '',
                    'endDate': dates[1] if len(dates) > 1 and dates[1] else '',
                    'summary': item.get('description', ''), 'highlights': [],
                })
        elif module_type == 'Project' and not data['projects']:
            for item in props.get('projects') or []:
                dates = item.get('dateRange') or []
                keywords = [part.strip() for part in str(item.get('techStack') or '').split(',') if part.strip()]
                data['projects'].append({
                    'name': item.get('name', ''), 'description': item.get('description', ''),
                    'startDate': dates[0] if dates else '',
                    'endDate': dates[1] if len(dates) > 1 and dates[1] else '',
                    'roles': [item.get('role')] if item.get('role') else [],
                    'keywords': keywords, 'highlights': [],
                })
        elif module_type == 'Skills' and not data['skills']:
            data['skills'] = [
                {'name': item.get('name', ''), 'level': item.get('proficiency', ''), 'keywords': []}
                for item in props.get('skills') or []
                if isinstance(item, dict)
            ]
        elif module_type not in {'BaseInfo', 'Summary', 'Education', 'WorkExp', 'Project', 'Skills'}:
            custom_sections.append({
                'type': module_type or 'Custom',
                'title': props.get('title') or module.get('title') or '自定义内容',
                'content': props.get('content') or props.get('items') or props,
            })

    data['x-ifaceoff'] = {
        'legacyResumeId': resume.pk,
        'template': resume.template_name,
        'customSections': custom_sections,
    }
    return normalize_json_resume(data)


def imported_text_to_json_resume(resume, text: str, parsed_content: dict | None = None) -> dict:
    data = legacy_resume_to_json_resume(resume)
    data['x-ifaceoff']['import'] = {
        'reviewRequired': True,
        'rawText': text,
        'structuredBlocks': (parsed_content or {}).get('blocks', []),
    }
    return data


def json_resume_plain_text(payload: dict) -> str:
    data = normalize_json_resume(payload)
    parts = []
    basics = data['basics']
    parts.extend(str(basics.get(key) or '') for key in ('name', 'label', 'summary', 'email', 'phone'))
    for section in ('work', 'education', 'projects', 'skills', 'certificates', 'awards'):
        for item in data.get(section, []):
            if isinstance(item, dict):
                parts.extend(str(value) for value in item.values() if isinstance(value, (str, int, float)))
                for value in item.values():
                    if isinstance(value, list):
                        parts.extend(str(entry) for entry in value if isinstance(entry, (str, int, float)))
    return '\n'.join(part.strip() for part in parts if part and part.strip())

