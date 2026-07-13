from django.db import migrations


ALIASES = {
    'chat': [
        ('chat.default', '默认对话模型'),
        ('interview.evaluate.fast', '面试快速评估'),
        ('interview.generate.quality', '面试高质量出题'),
        ('resume.extract', '简历信息提取'),
        ('resume.rewrite', '简历证据化改写'),
    ],
    'embedding': [('embedding.default', '默认向量模型')],
    'rerank': [('rerank.default', '默认重排模型')],
    'asr': [('speech.asr', '语音识别')],
    'tts': [('speech.tts', '语音合成')],
}


def seed_gateway(apps, schema_editor):
    from system.credentials import encrypt_secret, secret_hint

    AIModel = apps.get_model('system', 'AIModel')
    AISetting = apps.get_model('system', 'AISetting')
    ProviderCredential = apps.get_model('system', 'ProviderCredential')
    ModelDeployment = apps.get_model('system', 'ModelDeployment')
    ModelAlias = apps.get_model('system', 'ModelAlias')
    RoutePolicy = apps.get_model('system', 'RoutePolicy')
    RoutePolicyTarget = apps.get_model('system', 'RoutePolicyTarget')
    db_alias = schema_editor.connection.alias

    for setting in AISetting.objects.using(db_alias).exclude(api_keys={}).iterator():
        remaining_keys = dict(setting.api_keys or {})
        for raw_model_id, raw_key in list(remaining_keys.items()):
            key = str(raw_key or '').strip()
            if not key:
                remaining_keys.pop(raw_model_id, None)
                continue
            model = None
            model_ref = str(raw_model_id).strip()
            if model_ref.isdigit():
                model = AIModel.objects.using(db_alias).filter(id=int(model_ref)).first()
            if not model:
                model = AIModel.objects.using(db_alias).filter(model_slug__iexact=model_ref).first()
            if not model:
                model = AIModel.objects.using(db_alias).filter(name__iexact=model_ref).first()
            if not model:
                continue
            ProviderCredential.objects.using(db_alias).get_or_create(
                user_id=setting.user_id,
                legacy_model_id=model.id,
                provider=model.provider,
                scope='byok',
                defaults={
                    'name': f'{model.name} BYOK'[:120],
                    'encrypted_secret': encrypt_secret(key),
                    'secret_hint': secret_hint(key),
                    'is_active': True,
                },
            )
            remaining_keys.pop(raw_model_id, None)
        AISetting.objects.using(db_alias).filter(pk=setting.pk).update(api_keys=remaining_keys)

    deployments_by_type = {}
    for index, model in enumerate(AIModel.objects.using(db_alias).filter(is_active=True).order_by('id')):
        deployment, _ = ModelDeployment.objects.using(db_alias).get_or_create(
            name=f'legacy-{model.id}-{model.model_slug}'[:120],
            defaults={
                'provider': model.provider,
                'remote_model': model.model_slug,
                'model_type': model.model_type,
                'base_url': model.base_url,
                'capabilities': {'json_mode': bool(model.supports_json_mode), 'dimension': model.dimension},
                'priority': 100 + index,
                'timeout_seconds': 30,
                'is_active': True,
            },
        )
        deployments_by_type.setdefault(model.model_type, []).append(deployment)

    for model_type, alias_specs in ALIASES.items():
        for slug, name in alias_specs:
            alias, _ = ModelAlias.objects.using(db_alias).get_or_create(
                slug=slug,
                defaults={'name': name, 'model_type': model_type, 'is_active': True},
            )
            policy, _ = RoutePolicy.objects.using(db_alias).get_or_create(
                alias_id=alias.id,
                defaults={'strategy': 'priority', 'total_timeout_seconds': 45, 'max_attempts': 2, 'is_active': True},
            )
            for order, deployment in enumerate(deployments_by_type.get(model_type, [])):
                RoutePolicyTarget.objects.using(db_alias).get_or_create(
                    policy_id=policy.id,
                    deployment_id=deployment.id,
                    defaults={'order': order, 'weight': 100, 'retry_count': 0, 'is_active': True},
                )


class Migration(migrations.Migration):
    dependencies = [('system', '0007_modelalias_providercredential_modeldeployment_and_more')]

    operations = [migrations.RunPython(seed_gateway, migrations.RunPython.noop)]
