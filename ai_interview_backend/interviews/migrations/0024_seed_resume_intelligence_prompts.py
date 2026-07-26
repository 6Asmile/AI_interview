import hashlib
import json

from django.db import migrations
from django.db.models import Max
from django.utils import timezone


PROMPTS = {
    'resume.from_career_facts': {
        'system': '你是简历事实整理器。只能使用已确认 CareerFact，不得增加不存在的经历、技能、数字或因果关系。只返回 JSON。',
        'user': '{{ context_json }}\n返回 {"resume_json": {}, "evidence_links": [], "questions": []}；证据不足必须提问，不得猜测。',
        'required': ['resume_json', 'evidence_links', 'questions'],
        'temperature': 0.1,
        'tokens': 3000,
    },
    'resume.rewrite_section': {
        'system': '你是证据约束的简历编辑器。只生成 JSON Patch 建议，不直接写入简历，不得添加无证据的数字、技能或经历。',
        'user': '{{ context_json }}\n返回 {"patch": [], "evidence_links": [], "questions": [], "rationale": ""}。',
        'required': ['patch', 'evidence_links', 'questions', 'rationale'],
        'temperature': 0.2,
        'tokens': 1600,
    },
    'resume.achievement_coach': {
        'system': '你是成果挖掘教练。提出可回答的问题，不替候选人创造指标；所有数字必须来自已确认事实。',
        'user': '{{ context_json }}\n返回 {"questions": [], "candidate_patch": [], "missing_evidence": []}；确认前 patch 必须为空。',
        'required': ['questions', 'candidate_patch', 'missing_evidence'],
        'temperature': 0.2,
        'tokens': 1000,
    },
    'resume.quality_review': {
        'system': '你是简历质量复核器。确定性 Schema、ATS 和证据检查优先，只补充三类招聘视角，不得把推测写成事实。',
        'user': '{{ context_json }}\n返回 {"recruiter": [], "hiring_manager": [], "domain_reviewer": [], "consensus": []}。',
        'required': ['recruiter', 'hiring_manager', 'domain_reviewer', 'consensus'],
        'temperature': 0.1,
        'tokens': 1800,
    },
    'resume.jd_tailor': {
        'system': '你是岗位定制简历编辑器。只调整排序和措辞，不改变职业事实；只返回 JSON Patch。',
        'user': '{{ context_json }}\n返回 {"patch": [], "evidence_links": [], "unmatched_requirements": [], "questions": []}。',
        'required': ['patch', 'evidence_links', 'unmatched_requirements', 'questions'],
        'temperature': 0.1,
        'tokens': 1800,
    },
}


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def seed_resume_prompts(apps, schema_editor):
    AgentConfigProfile = apps.get_model('interviews', 'AgentConfigProfile')
    AgentConfigRevision = apps.get_model('interviews', 'AgentConfigRevision')
    AgentPromptTemplate = apps.get_model('interviews', 'AgentPromptTemplate')
    AgentConfigKnowledgeBinding = apps.get_model('interviews', 'AgentConfigKnowledgeBinding')
    ModelAlias = apps.get_model('system', 'ModelAlias')
    db = schema_editor.connection.alias
    now = timezone.now()
    profile = AgentConfigProfile.objects.using(db).filter(
        scope='platform',
        active_revision_id__isnull=False,
    ).first()
    if not profile:
        return
    active = AgentConfigRevision.objects.using(db).get(pk=profile.active_revision_id)
    existing = set(AgentPromptTemplate.objects.using(db).filter(
        revision_id=active.pk,
    ).values_list('task_key', flat=True))
    if set(PROMPTS).issubset(existing):
        return
    next_version = (
        AgentConfigRevision.objects.using(db).filter(profile_id=profile.pk).aggregate(value=Max('version'))['value'] or 0
    ) + 1
    revision = AgentConfigRevision.objects.using(db).create(
        profile_id=profile.pk,
        base_revision_id=active.pk,
        version=next_version,
        status='published',
        context_mode=active.context_mode,
        context_policy=active.context_policy,
        knowledge_mode=active.knowledge_mode,
        validation_report={'valid': True, 'source': 'resume_intelligence_migration'},
        evaluation_summary={
            'status': 'succeeded',
            'source': 'resume_baseline_compatibility',
            'finished_at': now.isoformat(),
        },
        change_summary='注册 Resume Intelligence 五类证据约束 Prompt',
        published_at=now,
    )
    prompt_hashes = {}
    for prompt in AgentPromptTemplate.objects.using(db).filter(revision_id=active.pk):
        prompt.pk = None
        prompt.revision_id = revision.pk
        prompt.save(using=db)
        prompt_hashes[prompt.task_key] = prompt.content_hash
    alias = ModelAlias.objects.using(db).filter(slug='interview.evaluate.fast').first()
    for task_key, spec in PROMPTS.items():
        variable_schema = {
            'type': 'object',
            'properties': {'context_json': {'type': 'string'}},
            'required': ['context_json'],
        }
        contract = {'type': 'object', 'required': spec['required']}
        content_hash = digest({
            'system_template': spec['system'],
            'user_template': spec['user'],
            'variable_schema': variable_schema,
            'output_contract': contract,
            'model_alias_id': alias.pk if alias else None,
            'temperature': str(spec['temperature']),
            'max_output_tokens': spec['tokens'],
        })
        AgentPromptTemplate.objects.using(db).create(
            revision_id=revision.pk,
            task_key=task_key,
            system_template=spec['system'],
            user_template=spec['user'],
            variable_schema=variable_schema,
            output_contract=contract,
            model_alias_id=alias.pk if alias else None,
            temperature=spec['temperature'],
            max_output_tokens=spec['tokens'],
            content_hash=content_hash,
        )
        prompt_hashes[task_key] = content_hash
    binding_ids = []
    for binding in AgentConfigKnowledgeBinding.objects.using(db).filter(revision_id=active.pk):
        binding.pk = None
        binding.revision_id = revision.pk
        binding.save(using=db)
        binding_ids.append({
            'knowledge_base_revision_id': str(binding.knowledge_base_revision_id),
            'retrieval_profile_revision_id': str(binding.retrieval_profile_revision_id or ''),
        })
    config_hash = digest({
        'context_policy': revision.context_policy,
        'prompt_hashes': prompt_hashes,
        'knowledge_bindings': binding_ids,
    })
    AgentConfigRevision.objects.using(db).filter(pk=revision.pk).update(config_hash=config_hash)
    AgentConfigRevision.objects.using(db).filter(pk=active.pk, status='published').update(status='superseded')
    AgentConfigProfile.objects.using(db).filter(pk=profile.pk).update(active_revision_id=revision.pk)


class Migration(migrations.Migration):
    dependencies = [('interviews', '0023_seed_agent_config_baseline')]
    operations = [migrations.RunPython(seed_resume_prompts, migrations.RunPython.noop)]
