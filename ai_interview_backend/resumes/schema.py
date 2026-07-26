from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from jsonschema import Draft7Validator, FormatChecker

from .runtime import resume_runtime_config


JSON_RESUME_SCHEMA_VERSION = '1.3.1'
SCHEMA_PATH = Path(__file__).resolve().parent / 'schema' / 'jsonresume-1.3.1.json'
ARRAY_SECTIONS = (
    'work', 'volunteer', 'education', 'awards', 'certificates', 'publications',
    'skills', 'languages', 'interests', 'references', 'projects',
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))


def schema_snapshot_hash() -> str:
    return hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()


def _ensure_item_ids(data: dict) -> None:
    for section in ARRAY_SECTIONS:
        for item in data.get(section, []):
            if not isinstance(item, dict):
                continue
            extension = item.get('x-ifaceoff')
            if not isinstance(extension, dict):
                extension = {}
                item['x-ifaceoff'] = extension
            if not extension.get('id'):
                extension['id'] = str(uuid4())


def _drop_blank_formatted_fields(value: Any) -> None:
    """Clean legacy optional fields that are invalid when serialized as an empty string."""
    if isinstance(value, dict):
        for key in list(value):
            child = value[key]
            if key in {'email', 'url'} and isinstance(child, str) and not child.strip():
                value.pop(key)
                continue
            _drop_blank_formatted_fields(child)
    elif isinstance(value, list):
        for child in value:
            _drop_blank_formatted_fields(child)


def normalize_resume(payload: dict | None, *, with_internal_ids: bool = True) -> dict:
    data = deepcopy(payload) if isinstance(payload, dict) else {}
    _drop_blank_formatted_fields(data)
    data['basics'] = data.get('basics') if isinstance(data.get('basics'), dict) else {}
    data['basics']['location'] = (
        data['basics'].get('location') if isinstance(data['basics'].get('location'), dict) else {}
    )
    data['basics']['profiles'] = (
        data['basics'].get('profiles') if isinstance(data['basics'].get('profiles'), list) else []
    )
    for section in ARRAY_SECTIONS:
        data[section] = data.get(section) if isinstance(data.get(section), list) else []
    data['meta'] = data.get('meta') if isinstance(data.get('meta'), dict) else {}
    data['meta']['schemaVersion'] = JSON_RESUME_SCHEMA_VERSION
    data['meta']['schemaSnapshotHash'] = schema_snapshot_hash()
    data['x-ifaceoff'] = data.get('x-ifaceoff') if isinstance(data.get('x-ifaceoff'), dict) else {}
    if with_internal_ids:
        _ensure_item_ids(data)
    return data


def validation_errors(payload: dict) -> list[dict]:
    validator = Draft7Validator(load_schema(), format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        pointer = '/' + '/'.join(str(part).replace('~', '~0').replace('/', '~1') for part in error.path)
        errors.append({'pointer': pointer, 'message': error.message, 'validator': error.validator})
    return errors


def validate_resume(payload: dict) -> dict:
    data = normalize_resume(payload)
    errors = validation_errors(data)
    if errors:
        from rest_framework.exceptions import ValidationError
        raise ValidationError({'resume_json': errors})
    max_input_bytes = int(resume_runtime_config().get('max_input_bytes', 2_000_000))
    if len(canonical_json(data).encode('utf-8')) > max_input_bytes:
        from rest_framework.exceptions import ValidationError
        raise ValidationError({'resume_json': f'简历内容不得超过 {max_input_bytes} 字节。'})
    return data


def strip_internal_metadata(payload: dict, *, preserve_asset_references: bool = False) -> dict:
    data = deepcopy(payload)
    data.pop('x-ifaceoff', None)
    basics = data.get('basics')
    if (
        not preserve_asset_references
        and isinstance(basics, dict)
        and str(basics.get('image') or '').startswith('asset:')
    ):
        basics.pop('image', None)
    meta = data.get('meta')
    if isinstance(meta, dict):
        meta.pop('schemaSnapshotHash', None)
        meta['version'] = JSON_RESUME_SCHEMA_VERSION
    for section in ARRAY_SECTIONS:
        for item in data.get(section, []):
            if isinstance(item, dict):
                item.pop('x-ifaceoff', None)
    return data
