"""Opt-in real renderer matrix with synthetic data; no AI or network calls."""
import io
import math
import time

from django.test import SimpleTestCase
from pypdf import PdfReader

from .rendering import _render_with_rendercv
from .templates import RESUME_TEMPLATES, default_design


class RealRenderMatrixEvaluation(SimpleTestCase):
    def test_six_templates_two_languages_two_page_sizes(self):
        rows = []
        self.measurements = []
        for template in RESUME_TEMPLATES:
            for language in ('zh-CN', 'en-US'):
                for size in ('A4', 'Letter'):
                    with self.subTest(template=template, language=language, page_size=size):
                        marker = 'SYNTHETIC-CONTENT-LAST'
                        data = {'basics': {'name': '合成候选人' if language == 'zh-CN' else 'Synthetic Candidate',
                                           'summary': '合成测试简历' if language == 'zh-CN' else 'Synthetic test resume'},
                                'work': [{'name': f'Synthetic Company {index}', 'position': 'Engineer',
                                          'startDate': '2020-01', 'endDate': '2021-01',
                                          'highlights': [f'Synthetic reproducible engineering experience {index}',
                                                         marker if index == 11 else f'CONTENT-{index}']}
                                         for index in range(12)]}
                        design = default_design(template_key=template, language=language)
                        design['page_size'] = size
                        started = time.perf_counter()
                        content, _mime, _pages = _render_with_rendercv(data, design, 'pdf')
                        duration = (time.perf_counter() - started) * 1000
                        reader = PdfReader(io.BytesIO(content))
                        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
                        self.assertIn(marker, text)
                        self.assertIn('Synthetic Company 0', text)
                        self.assertIn('Synthetic Company 11', text)
                        self.assertIn(''.join(data['basics']['name'].split()), ''.join(text.split()))
                        expected_size = (595.28, 841.89) if size == 'A4' else (612, 792)
                        for page in reader.pages:
                            self.assertAlmostEqual(float(page.mediabox.width), expected_size[0], delta=2)
                            self.assertAlmostEqual(float(page.mediabox.height), expected_size[1], delta=2)
                        rows.append({'template': template, 'language': language, 'page_size': size,
                                     'page_count': len(reader.pages), 'bytes': len(content),
                                     'render_ms': round(duration, 3), 'final_content_preserved': True})
        values = sorted(row['render_ms'] for row in rows)
        self.measurements = [{'name': '真实六模板渲染矩阵', 'sample_count': len(rows),
            **{key: values[math.ceil(len(values) * q) - 1] for key, q in
               (('p50_ms', .5), ('p95_ms', .95), ('p99_ms', .99))},
            'evidence_level': 'real_local_rendercv_pdf_synthetic_matrix', 'cases': rows,
            'limitations': ['检查文本末尾与纸张尺寸；未验证像素黄金图、字体嵌入或边界溢出。',
                            '生成实际页数，不声称覆盖精确 1/2/3 页全部组合；不证明 Worker 吞吐。']}]
