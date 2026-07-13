import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from .services import extract_text_from_file


class ResumeParsingServiceTests(TestCase):
    def _temp_file(self, suffix: str, content: bytes) -> str:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            handle.write(content)
            return handle.name
        finally:
            handle.close()

    def test_extract_text_prefers_structured_document_parser(self):
        path = self._temp_file('.pdf', b'%PDF fake content')
        try:
            with patch('knowledge.importers.DocumentParsingService.parse', return_value=SimpleNamespace(content='结构化解析的简历内容')) as parse:
                text = extract_text_from_file(path)

            self.assertEqual(text, '结构化解析的简历内容')
            parse.assert_called_once()
        finally:
            os.remove(path)

    def test_extract_text_falls_back_to_text_reader_when_parser_fails(self):
        path = self._temp_file('.txt', '候选人有 RAG 和 Agent 项目经验。'.encode('utf-8'))
        try:
            with patch('knowledge.importers.DocumentParsingService.parse', side_effect=RuntimeError('docling unavailable')):
                text = extract_text_from_file(path)

            self.assertIn('RAG 和 Agent 项目经验', text)
        finally:
            os.remove(path)
