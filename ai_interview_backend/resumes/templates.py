from __future__ import annotations

from copy import deepcopy

from rest_framework.exceptions import ValidationError

from .runtime import resume_runtime_config
from .schema import sha256_json


TEMPLATE_VERSION = '1.0.0'
ALLOWED_PAGE_SIZES = {'A4', 'Letter'}
ALLOWED_LANGUAGES = {'zh-CN', 'en-US'}
ALLOWED_FONTS = {'Noto Sans CJK SC', 'Noto Serif CJK SC', 'Source Sans 3', 'Inter'}
ALLOWED_DENSITIES = {'compact', 'balanced', 'comfortable'}
ALLOWED_DATE_FORMATS = {'YYYY-MM', 'YYYY.MM', 'MMM YYYY', 'YYYY'}
SECTION_KEYS = [
    'basics', 'summary', 'work', 'projects', 'education', 'skills',
    'certificates', 'awards', 'publications', 'languages', 'volunteer', 'interests',
    'references',
]

RESUME_TEMPLATES = {
    'ats-classic': {
        'name': {'zh-CN': 'ATS 经典', 'en-US': 'ATS Classic'},
        'description': '高兼容、单栏、无图形化技能条。',
        'default_font': 'Noto Sans CJK SC',
        'default_color': '#1F2937',
        'default_density': 'balanced',
        'use_tags': ['通用求职', 'ATS 优先'],
        'industry_tags': ['互联网', '制造', '服务业'],
        'role_tags': ['产品', '运营', '职能'],
    },
    'modern-professional': {
        'name': {'zh-CN': '现代专业', 'en-US': 'Modern Professional'},
        'description': '清晰层级与克制的强调色。',
        'default_font': 'Source Sans 3',
        'default_color': '#155E75',
        'default_density': 'balanced',
        'use_tags': ['社招', '专业岗位'],
        'industry_tags': ['互联网', '金融', '专业服务'],
        'role_tags': ['产品', '设计', '市场'],
    },
    'engineering': {
        'name': {'zh-CN': '技术工程', 'en-US': 'Engineering'},
        'description': '突出项目、技术栈和可验证成果。',
        'default_font': 'Inter',
        'default_color': '#334155',
        'default_density': 'compact',
        'use_tags': ['技术岗位', '项目优先'],
        'industry_tags': ['互联网', '软件', '智能制造'],
        'role_tags': ['后端', '前端', '算法', '测试'],
    },
    'graduate': {
        'name': {'zh-CN': '校招成长', 'en-US': 'Graduate'},
        'description': '优先教育、项目和成长证据。',
        'default_font': 'Noto Sans CJK SC',
        'default_color': '#4338CA',
        'default_density': 'balanced',
        'use_tags': ['校招', '实习'],
        'industry_tags': ['通用'],
        'role_tags': ['应届生', '实习生'],
    },
    'management-consulting': {
        'name': {'zh-CN': '管理咨询', 'en-US': 'Management Consulting'},
        'description': '强调业务影响、结构化表达与领导力。',
        'default_font': 'Noto Serif CJK SC',
        'default_color': '#78350F',
        'default_density': 'compact',
        'use_tags': ['商业分析', '管理岗'],
        'industry_tags': ['咨询', '金融', '企业服务'],
        'role_tags': ['咨询顾问', '战略', '管理'],
    },
    'academic-research': {
        'name': {'zh-CN': '学术研究', 'en-US': 'Academic Research'},
        'description': '突出研究、发表、教育和学术成果。',
        'default_font': 'Noto Serif CJK SC',
        'default_color': '#374151',
        'default_density': 'comfortable',
        'use_tags': ['学术申请', '研究岗位'],
        'industry_tags': ['高校', '研究院', '医药'],
        'role_tags': ['研究员', '博士后', '教师'],
    },
}


def default_design(template_key: str = 'ats-classic', language: str = 'zh-CN') -> dict:
    template = RESUME_TEMPLATES.get(template_key, RESUME_TEMPLATES['ats-classic'])
    return {
        'template_key': template_key if template_key in RESUME_TEMPLATES else 'ats-classic',
        'template_version': TEMPLATE_VERSION,
        'page_size': 'A4',
        'language': language if language in ALLOWED_LANGUAGES else 'zh-CN',
        'font': template['default_font'],
        'color': template['default_color'],
        'density': template['default_density'],
        'date_format': 'YYYY-MM',
        'show_avatar': False,
        'section_order': list(SECTION_KEYS),
        'hidden_sections': [],
    }


def validate_design(payload: dict | None) -> dict:
    source = deepcopy(payload) if isinstance(payload, dict) else {}
    template_key = source.get('template_key', 'ats-classic')
    if template_key not in RESUME_TEMPLATES:
        raise ValidationError({'design_json': {'template_key': '未知母版。'}})
    design = default_design(template_key, source.get('language', 'zh-CN'))
    design.update(source)
    if design['page_size'] not in ALLOWED_PAGE_SIZES:
        raise ValidationError({'design_json': {'page_size': '仅支持 A4 或 Letter。'}})
    if design['language'] not in ALLOWED_LANGUAGES:
        raise ValidationError({'design_json': {'language': '仅支持 zh-CN 或 en-US。'}})
    if design['font'] not in ALLOWED_FONTS:
        raise ValidationError({'design_json': {'font': '字体不在允许列表中。'}})
    if design['density'] not in ALLOWED_DENSITIES:
        raise ValidationError({'design_json': {'density': '紧凑度不在允许列表中。'}})
    if design['date_format'] not in ALLOWED_DATE_FORMATS:
        raise ValidationError({'design_json': {'date_format': '日期格式不在允许列表中。'}})
    color = str(design.get('color', ''))
    if len(color) != 7 or not color.startswith('#'):
        raise ValidationError({'design_json': {'color': '颜色必须是 #RRGGBB。'}})
    try:
        int(color[1:], 16)
    except ValueError as exc:
        raise ValidationError({'design_json': {'color': '颜色必须是 #RRGGBB。'}}) from exc
    order = design.get('section_order')
    if not isinstance(order, list) or len(order) != len(set(order)) or any(item not in SECTION_KEYS for item in order):
        raise ValidationError({'design_json': {'section_order': '栏目顺序包含重复或未知栏目。'}})
    # Older drafts did not know newly-added sections. Append them deterministically
    # so an old user can keep editing without a manual migration.
    design['section_order'] = [*order, *(item for item in SECTION_KEYS if item not in order)]
    hidden = design.get('hidden_sections') or []
    if not isinstance(hidden, list) or len(hidden) != len(set(hidden)) or any(item not in SECTION_KEYS for item in hidden):
        raise ValidationError({'design_json': {'hidden_sections': '隐藏栏目包含重复或未知栏目。'}})
    design['hidden_sections'] = hidden
    design['show_avatar'] = bool(design.get('show_avatar', False))
    return design


def template_catalog(*, enabled_only: bool = True) -> list[dict]:
    enabled = set(resume_runtime_config().get('enabled_templates') or RESUME_TEMPLATES)
    return [
        {
            'key': key,
            'version': TEMPLATE_VERSION,
            **value,
            'thumbnail': f'/resume-templates/{key}.svg',
            'capabilities': {
                'page_sizes': sorted(ALLOWED_PAGE_SIZES),
                'languages': sorted(ALLOWED_LANGUAGES),
                'fonts': sorted(ALLOWED_FONTS),
                'densities': sorted(ALLOWED_DENSITIES),
                'date_formats': sorted(ALLOWED_DATE_FORMATS),
                'avatar': True,
                'single_column': True,
            },
        }
        for key, value in RESUME_TEMPLATES.items()
        if not enabled_only or key in enabled
    ]


def design_hash(payload: dict) -> str:
    return sha256_json(validate_design(payload))
