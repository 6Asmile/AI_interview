import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .importers import DocumentParsingService, ParsedKnowledgeDocument
from .services import (
    _ensure_qdrant_collection,
    _expand_adjacent_contexts,
    _expand_parent_contexts,
    _plan_registered_queries,
    _switch_qdrant_alias,
    _wait_for_meili_task,
    rrf_fuse,
)


class QdrantCollectionSafetyTests(SimpleTestCase):
    def test_transport_failure_never_calls_create_or_recreate(self):
        client = Mock()
        client.get_aliases.return_value = SimpleNamespace(aliases=[])
        client.collection_exists.side_effect = TimeoutError('network timeout')

        with self.assertRaises(TimeoutError):
            _ensure_qdrant_collection(client, 1536)

        client.create_collection.assert_not_called()
        self.assertFalse(hasattr(client, 'recreate_collection') and client.recreate_collection.called)

    def test_missing_collection_creates_versioned_physical_collection(self):
        client = Mock()
        client.get_aliases.return_value = SimpleNamespace(aliases=[])
        client.collection_exists.return_value = False

        qdrant_module = ModuleType('qdrant_client')
        models_module = ModuleType('qdrant_client.models')
        models_module.Distance = SimpleNamespace(COSINE='cosine')
        models_module.VectorParams = lambda **kwargs: kwargs
        qdrant_module.models = models_module
        with patch.dict(sys.modules, {
            'qdrant_client': qdrant_module,
            'qdrant_client.models': models_module,
        }):
            target, pending = _ensure_qdrant_collection(client, 1536)

        self.assertTrue(target.startswith('interview_knowledge_d1536_'))
        self.assertTrue(pending)
        client.create_collection.assert_called_once()

    def test_alias_switch_uses_atomic_operation_list(self):
        client = Mock()
        client.get_aliases.return_value = SimpleNamespace(aliases=[
            SimpleNamespace(alias_name='interview_knowledge', collection_name='old'),
        ])
        models_module = ModuleType('qdrant_client.models')
        models_module.CreateAlias = lambda **kwargs: ('create', kwargs)
        models_module.CreateAliasOperation = lambda **kwargs: ('create_op', kwargs)
        models_module.DeleteAlias = lambda **kwargs: ('delete', kwargs)
        models_module.DeleteAliasOperation = lambda **kwargs: ('delete_op', kwargs)

        with patch.dict(sys.modules, {'qdrant_client.models': models_module}):
            _switch_qdrant_alias(client, 'interview_knowledge_d1536_v2')

        operations = client.update_collection_aliases.call_args.kwargs['change_aliases_operations']
        self.assertIsInstance(operations, list)
        self.assertEqual([item[0] for item in operations], ['delete_op', 'create_op'])


class MeilisearchTaskTests(SimpleTestCase):
    @patch('knowledge.services.requests.get')
    def test_waits_for_async_mutation_before_publishing_index_state(self, get):
        response = Mock()
        response.json.return_value = {'taskUid': 12}
        get.return_value.json.return_value = {'status': 'succeeded'}

        _wait_for_meili_task(response)

        response.raise_for_status.assert_called_once()
        get.return_value.raise_for_status.assert_called_once()


class QueryPlannerTests(SimpleTestCase):
    @patch('knowledge.services.ModelGateway')
    def test_registered_query_planner_uses_versioned_prompt(self, gateway):
        gateway.return_value.chat_json.return_value = {
            'queries': ['RRF 召回评估', '租户过滤'],
            'retrieval_intent': True,
        }
        snapshot = {
            'prompts': {
                'rag.query_planner': {
                    'system_template': '只返回 JSON',
                    'user_template': '{{ context_json }} {{ query_count }}',
                    'variable_schema': {'required': ['context_json', 'query_count']},
                    'output_contract': {
                        'type': 'object',
                        'required': ['queries', 'retrieval_intent'],
                    },
                    'model_alias': 'interview.evaluate.fast',
                    'max_output_tokens': 200,
                    'temperature': 0.1,
                    'content_hash': 'planner-hash',
                },
            },
        }

        queries, trace = _plan_registered_queries(
            fallback_queries=['fallback'],
            query_count=2,
            agent_config_snapshot=snapshot,
            job_position='AI 应用开发',
        )

        self.assertEqual(queries, ['RRF 召回评估', '租户过滤'])
        self.assertEqual(trace['status'], 'model')
        self.assertEqual(trace['prompt_hash'], 'planner-hash')


class ParentExpansionTests(SimpleTestCase):
    def test_child_rerank_expands_full_parent_and_deduplicates(self):
        contexts = [
            {
                'chunk_id': 'child-1',
                'parent_chunk_id': 'parent-1',
                'semantic_group_id': 'group-1',
                'content': '精确命中的 child',
                'token_count': 10,
                '_parent_content': '完整 parent 上下文',
                '_parent_token_count': 20,
            },
            {
                'chunk_id': 'child-2',
                'parent_chunk_id': 'parent-1',
                'semantic_group_id': 'group-1',
                'content': '同一父块另一个 child',
                'token_count': 10,
                '_parent_content': '完整 parent 上下文',
                '_parent_token_count': 20,
            },
        ]
        result = _expand_parent_contexts(contexts, enabled=True, token_limit=100, limit=4)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['chunk_id'], 'parent-1')
        self.assertEqual(result[0]['matched_child_chunk_id'], 'child-1')
        self.assertEqual(result[0]['content'], '完整 parent 上下文')
        self.assertTrue(result[0]['parent_expanded'])

    @patch('knowledge.services.KnowledgeChunk.objects')
    def test_adjacent_expansion_uses_profile_count_when_parent_is_disabled(self, objects):
        queryset = objects.filter.return_value
        queryset.filter.return_value = queryset
        queryset.order_by.return_value.values.return_value = [
            {'id': 'child-1', 'chunk_index': 1, 'content': '前文'},
            {'id': 'child-2', 'chunk_index': 2, 'content': '命中内容'},
            {'id': 'child-3', 'chunk_index': 3, 'content': '后文'},
        ]
        result = _expand_adjacent_contexts([{
            'document_id': 'doc-1',
            'document_revision_id': 'revision-1',
            'chunk_id': 'child-2',
            'parent_chunk_id': 'parent-1',
            'chunk_index': 2,
            'content': '命中内容',
            '_retrieval_config': {'parent_expansion': False, 'adjacent_chunks': 1},
        }])

        self.assertEqual(result[0]['adjacent_chunk_ids'], ['child-1', 'child-3'])
        self.assertEqual(result[0]['content'], '前文\n命中内容\n后文')
        self.assertTrue(result[0]['adjacent_expanded'])

    def test_rrf_respects_vector_and_keyword_weights(self):
        fused = rrf_fuse(
            vector_rankings=[[('vector', 1, 0.9)]],
            keyword_rankings=[[('keyword', 1, 0.9)]],
            rrf_k=10,
            vector_weights=[2.0],
            keyword_weights=[0.5],
        )

        self.assertGreater(fused['vector']['rrf_score'], fused['keyword']['rrf_score'])


class PdfFallbackOrderTests(SimpleTestCase):
    def test_pdf_uses_fixed_docling_ocr_paddle_pypdf_chain(self):
        service = DocumentParsingService(enable_ocr=True, ocr_lang='ch')
        uploaded = SimpleNamespace(name='scan.pdf')
        expected = ParsedKnowledgeDocument(
            title='scan',
            content='fallback',
            file_type='pdf',
            parser_name='pypdf',
        )
        calls = []

        def docling(*args, use_ocr=False, **kwargs):
            calls.append('docling_ocr' if use_ocr else 'docling')
            raise RuntimeError('failed')

        with patch.object(service, '_parse_with_docling', side_effect=docling), patch.object(
            service,
            '_parse_pdf_with_paddleocr',
            side_effect=lambda *args, **kwargs: calls.append('paddleocr') or (_ for _ in ()).throw(RuntimeError('failed')),
        ), patch.object(
            service,
            '_parse_pdf_fallback',
            side_effect=lambda *args, **kwargs: calls.append('pypdf') or expected,
        ):
            result = service.parse(uploaded)

        self.assertIs(result, expected)
        self.assertEqual(calls, ['docling', 'docling_ocr', 'paddleocr', 'pypdf'])
