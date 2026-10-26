from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import AsyncOperation

from .models import KnowledgeChunk, KnowledgeDocument, KnowledgeImportBatch
from .services import index_document, search_knowledge_context, split_text
from .tasks import process_import_file
from .views import KnowledgeDocumentViewSet, KnowledgeImportBatchViewSet
from users.models import User


class KnowledgeServiceTests(TestCase):
    def test_split_text_keeps_short_content_as_single_chunk(self):
        self.assertEqual(split_text('RAG 检索题库'), ['RAG 检索题库'])

    @override_settings(QDRANT_URL='', EMBEDDING_API_KEY='')
    def test_sql_fallback_search_filters_by_job_and_topic(self):
        user = User.objects.create_user(username='owner', email='owner@example.com', password='pass')
        document = KnowledgeDocument.objects.create(
            title='AI 应用开发 RAG 追问',
            content='RAG 项目应重点追问文档切分、Embedding 模型选择、召回率、Rerank 和幻觉控制。',
            created_by=user,
            job_positions=['AI 应用开发实习生'],
            ability_tags=['RAG', '知识库'],
            difficulty='medium',
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
        )
        index_document(document)

        results = search_knowledge_context(
            job_position='AI 应用开发实习生',
            user=user,
            current_stage='technical_deep_dive',
            pending_topics=['RAG'],
            last_evaluation={'follow_up_target': '追问 RAG 召回率优化'},
            difficulty='medium',
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'AI 应用开发 RAG 追问')
        self.assertIn('Rerank', results[0]['content'])
        document.refresh_from_db()
        self.assertIsNotNone(document.last_retrieved_at)
        self.assertEqual(document.retrieval_count, 1)

    @override_settings(QDRANT_URL='', EMBEDDING_API_KEY='test-key')
    def test_index_document_degrades_to_keyword_index_when_embedding_fails(self):
        user = User.objects.create_user(username='embed-fallback', email='embed-fallback@example.com', password='pass')
        document = KnowledgeDocument.objects.create(
            title='Embedding 失败降级题库',
            content='RAG 检索应在 embedding 服务失败时保留关键词检索能力。',
            created_by=user,
            job_positions=['AI 应用开发'],
            ability_tags=['RAG'],
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
        )

        with patch('knowledge.services._embed_text', side_effect=RuntimeError('provider arrearage')):
            index_document(document)

        document.refresh_from_db()
        self.assertEqual(document.status, KnowledgeDocument.Status.INDEXED)
        self.assertGreater(document.chunk_count, 0)
        self.assertIn('keyword/BM25 fallback', document.error_message)

    @override_settings(QDRANT_URL='', EMBEDDING_API_KEY='')
    def test_topic_mismatch_does_not_hard_filter_relevant_job_document(self):
        user = User.objects.create_user(username='soft-tag', email='soft-tag@example.com', password='pass')
        document = KnowledgeDocument.objects.create(
            title='RAG 工程题库',
            content='RAG 项目应追问 BM25、RRF、Rerank、租户隔离和审批上线。',
            created_by=user,
            job_positions=['AI 应用开发'],
            ability_tags=['RAG'],
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
        )
        index_document(document)

        results = search_knowledge_context(
            job_position='AI 应用开发',
            user=user,
            pending_topics=['ASR/TTS经验'],
            last_evaluation={'follow_up_target': '追问 RAG 检索评估'},
        )

        self.assertTrue(results)
        self.assertEqual(results[0]['title'], 'RAG 工程题库')

    @override_settings(QDRANT_URL='', EMBEDDING_API_KEY='')
    def test_private_knowledge_is_isolated_by_user(self):
        user_a = User.objects.create_user(username='a', email='a@example.com', password='pass')
        user_b = User.objects.create_user(username='b', email='b@example.com', password='pass')
        private_doc = KnowledgeDocument.objects.create(
            title='用户B私有题库',
            content='只属于用户B的 Redis 缓存雪崩追问。',
            created_by=user_b,
            job_positions=['后端开发'],
            ability_tags=['Redis'],
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
        )
        public_doc = KnowledgeDocument.objects.create(
            title='公共后端题库',
            content='公共知识库中的 MySQL 索引优化追问。',
            created_by=user_b,
            visibility=KnowledgeDocument.Visibility.PUBLIC,
            job_positions=['后端开发'],
            ability_tags=['MySQL'],
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
        )
        index_document(private_doc)
        index_document(public_doc)

        results = search_knowledge_context(
            job_position='后端开发',
            user=user_a,
            pending_topics=['Redis', 'MySQL'],
            last_evaluation={'follow_up_target': '追问数据库和缓存'},
        )

        titles = {item['title'] for item in results}
        self.assertIn('公共后端题库', titles)
        self.assertNotIn('用户B私有题库', titles)
        self.assertTrue(all(item['visibility'] == KnowledgeDocument.Visibility.PUBLIC for item in results))

    @override_settings(QDRANT_URL='', EMBEDDING_API_KEY='')
    def test_unapproved_knowledge_is_not_retrieved(self):
        user = User.objects.create_user(username='review', email='review@example.com', password='pass')
        document = KnowledgeDocument.objects.create(
            title='待审核题库',
            content='RAG 召回率追问。',
            created_by=user,
            job_positions=['AI 应用开发'],
            ability_tags=['RAG'],
            status=KnowledgeDocument.Status.INDEXED,
            approval_status=KnowledgeDocument.ApprovalStatus.PENDING_REVIEW,
        )
        KnowledgeChunk.objects.create(document=document, chunk_index=0, content=document.content)

        results = search_knowledge_context(
            job_position='AI 应用开发',
            user=user,
            pending_topics=['RAG'],
        )

        self.assertEqual(results, [])

    @patch.dict('os.environ', {'DASHSCOPE_API_KEY': '', 'EMBEDDING_API_KEY': ''})
    @override_settings(QDRANT_URL='', EMBEDDING_API_KEY='', HYBRID_SEARCH_PARALLELISM=3)
    def test_hybrid_search_trace_records_multi_query_vector_path(self):
        user = User.objects.create_user(username='trace-owner', email='trace@example.com', password='pass')
        document = KnowledgeDocument.objects.create(
            title='RAG 评估题库',
            content='企业级 RAG 面试应追问 query rewrite、BM25、向量召回、RRF、Rerank 和离线评估。',
            created_by=user,
            job_positions=['AI 应用开发'],
            ability_tags=['RAG', '评估'],
            difficulty='medium',
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
        )
        index_document(document)

        result = search_knowledge_context(
            job_position='AI 应用开发',
            user=user,
            current_stage='technical_deep_dive',
            pending_topics=['RAG'],
            last_evaluation={'follow_up_target': '追问 RRF 和 Rerank'},
            difficulty='medium',
            return_trace=True,
        )

        trace = result['retrieval_trace']
        explanation = result['retrieval_explanation']
        self.assertGreaterEqual(len(trace['queries']), 3)
        self.assertEqual(len(trace['vector_query_traces']), len(trace['queries']))
        self.assertTrue(all(item['status'] == 'qdrant_unavailable' for item in trace['vector_query_traces']))
        self.assertGreaterEqual(trace['keyword_query_count'], 1)
        self.assertGreaterEqual(trace['rrf_count'], 1)
        self.assertEqual(explanation['candidate_summary']['final_count'], 1)
        self.assertGreaterEqual(len(explanation['steps']), 6)
        self.assertIn('multi_query', {step['name'] for step in explanation['steps']})
        self.assertEqual(result['contexts'][0]['title'], 'RAG 评估题库')

    @override_settings(QDRANT_URL='', EMBEDDING_API_KEY='')
    def test_sql_fallback_trace_records_match_evidence(self):
        user = User.objects.create_user(username='fallback-owner', email='fallback@example.com', password='pass')
        document = KnowledgeDocument.objects.create(
            title='Agent 工具调用题库',
            content='Agent 面试应追问工具调用失败恢复、长期记忆、环境感知和任务并发控制。',
            created_by=user,
            job_positions=['AI 应用开发'],
            ability_tags=['Agent', '工具调用'],
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
        )
        index_document(document)

        with patch('knowledge.services.keyword_search_rankings', return_value=[]):
            result = search_knowledge_context(
                job_position='AI 应用开发',
                user=user,
                current_stage='technical_deep_dive',
                pending_topics=['Agent'],
                last_evaluation={'follow_up_target': '追问工具调用失败恢复'},
                return_trace=True,
            )

        trace = result['retrieval_trace']
        explanation = result['retrieval_explanation']
        self.assertEqual(trace['fallback_path'], 'sql_keyword_fallback')
        self.assertEqual(trace['sql_fallback']['status'], 'ok')
        self.assertGreaterEqual(trace['sql_fallback']['scanned_count'], 1)
        self.assertEqual(trace['sql_fallback']['returned_count'], 1)
        self.assertEqual(explanation['candidate_summary']['sql_fallback_returned_count'], 1)
        self.assertIn('sql_fallback', {step['name'] for step in explanation['steps']})
        self.assertEqual(result['contexts'][0]['title'], 'Agent 工具调用题库')
        self.assertIn('sql_fallback_score_detail', result['contexts'][0])
        self.assertGreaterEqual(result['contexts'][0]['sql_fallback_score_detail']['topic_overlap'], 1)

    @override_settings(QDRANT_URL='http://qdrant.test', EMBEDDING_API_KEY='test-key', HYBRID_SEARCH_PARALLELISM=1)
    def test_retrieval_explanation_records_policy_filter_for_stale_vector_candidate(self):
        user = User.objects.create_user(username='vector-owner', email='vector@example.com', password='pass')
        approved = KnowledgeDocument.objects.create(
            title='已审批 RAG 题库',
            content='RRF 融合和 Rerank 重排需要解释召回链路。',
            created_by=user,
            status=KnowledgeDocument.Status.INDEXED,
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
            job_positions=['AI 应用开发'],
            ability_tags=['RAG'],
        )
        stale = KnowledgeDocument.objects.create(
            title='未审批旧向量',
            content='这段内容不应进入检索结果。',
            created_by=user,
            status=KnowledgeDocument.Status.INDEXED,
            approval_status=KnowledgeDocument.ApprovalStatus.REJECTED,
            job_positions=['AI 应用开发'],
            ability_tags=['RAG'],
        )
        approved_chunk = KnowledgeChunk.objects.create(
            document=approved,
            chunk_index=1,
            chunk_level=2,
            content='RRF 融合和 Rerank 重排需要解释召回链路。',
        )
        stale_chunk = KnowledgeChunk.objects.create(
            document=stale,
            chunk_index=1,
            chunk_level=2,
            content='未审批旧向量候选。',
        )

        with patch('knowledge.services._vector_search_ranking') as vector_search, \
                patch('knowledge.services.keyword_search_rankings', return_value=[]):
            vector_search.return_value = (
                [(str(approved_chunk.id), 1, 0.91), (str(stale_chunk.id), 2, 0.88)],
                {'query': 'AI 应用开发 RAG', 'status': 'ok', 'candidate_count': 2},
            )
            result = search_knowledge_context(
                job_position='AI 应用开发',
                user=user,
                pending_topics=['RAG'],
                return_trace=True,
            )

        self.assertEqual([item['title'] for item in result['contexts']], ['已审批 RAG 题库'])
        self.assertEqual(result['retrieval_trace']['filter_counts']['approval_not_approved'], 1)
        self.assertEqual(result['retrieval_explanation']['filters']['approval_not_approved'], 1)


class KnowledgeDocumentViewSetTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username='u', email='u@example.com', password='pass')
        self.other = User.objects.create_user(username='o', email='o@example.com', password='pass')
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='pass',
            is_staff=True,
        )
        self.hr = User.objects.create_user(
            username='hr',
            email='hr@example.com',
            password='pass',
            role=User.Role.HR,
        )

    def test_user_lists_own_private_and_public_only(self):
        own = KnowledgeDocument.objects.create(title='自己的私有库', content='own', created_by=self.user)
        KnowledgeDocument.objects.create(title='别人的私有库', content='other', created_by=self.other)
        public = KnowledgeDocument.objects.create(
            title='公共库',
            content='public',
            created_by=self.admin,
            visibility=KnowledgeDocument.Visibility.PUBLIC,
        )
        view = KnowledgeDocumentViewSet.as_view({'get': 'list'})
        request = self.factory.get('/knowledge/documents/')
        force_authenticate(request, user=self.user)

        response = view(request)

        ids = {item['id'] for item in response.data['results']} if isinstance(response.data, dict) and 'results' in response.data else {item['id'] for item in response.data}
        self.assertIn(str(own.id), ids)
        self.assertIn(str(public.id), ids)
        self.assertEqual(len(ids), 2)

    def test_normal_user_cannot_create_public_document(self):
        view = KnowledgeDocumentViewSet.as_view({'post': 'create'})
        request = self.factory.post('/knowledge/documents/', {
            'title': '公共库',
            'content': 'content',
            'visibility': KnowledgeDocument.Visibility.PUBLIC,
        }, format='json')
        force_authenticate(request, user=self.user)

        response = view(request)

        self.assertEqual(response.status_code, 400)

    def test_normal_user_cannot_reindex_public_document(self):
        public = KnowledgeDocument.objects.create(
            title='公共库',
            content='public',
            created_by=self.admin,
            visibility=KnowledgeDocument.Visibility.PUBLIC,
        )
        view = KnowledgeDocumentViewSet.as_view({'post': 'reindex'})
        request = self.factory.post(f'/knowledge/documents/{public.id}/reindex/')
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(public.id))

        self.assertEqual(response.status_code, 403)

    def test_preview_chunks_does_not_create_document_or_chunks(self):
        view = KnowledgeDocumentViewSet.as_view({'post': 'preview_chunks'})
        request = self.factory.post('/knowledge/documents/preview-chunks/', {
            'content': '这是一段用于预览切分的知识库内容。' * 80,
            'chunk_size': 220,
            'overlap': 20,
        }, format='json')
        force_authenticate(request, user=self.user)

        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data['chunk_count'], 1)
        self.assertEqual(response.data['strategy'], 'hierarchical_recursive_semantic')
        self.assertGreater(response.data['parent_count'], 0)
        self.assertTrue(response.data['parents'])
        self.assertEqual(KnowledgeDocument.objects.count(), 0)
        self.assertEqual(KnowledgeChunk.objects.count(), 0)

    def test_preview_chunks_preserves_markdown_heading_hierarchy(self):
        view = KnowledgeDocumentViewSet.as_view({'post': 'preview_chunks'})
        request = self.factory.post('/knowledge/documents/preview-chunks/', {
            'title': 'AI 面试题库',
            'content': '# RAG\n\nRRF 融合、向量召回和关键词召回应作为一组能力点追问。\n\n# Agent\n\n工具调用、记忆系统和环境感知需要分开验证。',
            'chunk_size': 300,
            'overlap': 40,
        }, format='json')
        force_authenticate(request, user=self.user)

        response = view(request)

        self.assertEqual(response.status_code, 200)
        heading_paths = {
            tuple(parent['heading_path'])
            for parent in response.data['parents']
            if parent['block_type'] != 'heading'
        }
        self.assertIn(('RAG',), heading_paths)
        self.assertIn(('Agent',), heading_paths)
        self.assertEqual(response.data['strategy'], 'hierarchical_recursive_semantic')
        self.assertEqual(KnowledgeDocument.objects.count(), 0)
        self.assertEqual(KnowledgeChunk.objects.count(), 0)

    def test_existing_document_structured_preview_uses_same_strategy(self):
        document = KnowledgeDocument.objects.create(
            title='结构化题库',
            content='RAG 内容\n\nAgent 内容',
            created_by=self.user,
            parsed_content={
                'parser_name': 'test',
                'blocks': [
                    {'block_type': 'heading', 'text': 'RAG', 'heading_path': ['RAG']},
                    {'block_type': 'paragraph', 'text': 'RRF 融合和 Rerank 重排。', 'heading_path': ['RAG']},
                    {'block_type': 'heading', 'text': 'Agent', 'heading_path': ['Agent']},
                    {'block_type': 'paragraph', 'text': '工具调用、长期记忆和环境感知。', 'heading_path': ['Agent']},
                ],
            },
        )
        view = KnowledgeDocumentViewSet.as_view({'post': 'preview_structured_chunks'})
        request = self.factory.post(f'/knowledge/documents/{document.id}/preview-structured-chunks/', {
            'chunk_size': 300,
            'overlap': 40,
        }, format='json')
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(document.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['strategy'], 'hierarchical_recursive_semantic')
        self.assertEqual(response.data['chunk_count'], 2)
        self.assertEqual({tuple(item['heading_path']) for item in response.data['chunks']}, {('RAG',), ('Agent',)})

    def test_reindex_sets_indexing_status_and_dispatches_task(self):
        document = KnowledgeDocument.objects.create(
            title='私有库',
            content='content',
            created_by=self.user,
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
        )
        view = KnowledgeDocumentViewSet.as_view({'post': 'reindex'})
        request = self.factory.post(f'/knowledge/documents/{document.id}/reindex/')
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(document.id))

        self.assertEqual(response.status_code, 202)
        operation = AsyncOperation.objects.get(pk=response.data['operation_id'])
        self.assertEqual(operation.input_id, str(document.id))
        self.assertEqual(operation.dispatches.get().payload, {'operation_id': str(operation.pk)})
        document.refresh_from_db()
        self.assertEqual(document.status, KnowledgeDocument.Status.INDEXING)

    def test_create_with_auto_index_still_requires_review(self):
        view = KnowledgeDocumentViewSet.as_view({'post': 'create'})
        request = self.factory.post('/knowledge/documents/', {
            'title': '自动索引库',
            'content': 'content',
            'auto_index': True,
        }, format='json')
        force_authenticate(request, user=self.user)

        response = view(request)

        self.assertEqual(response.status_code, 201)
        document = KnowledgeDocument.objects.get(id=response.data['id'])
        self.assertEqual(document.status, KnowledgeDocument.Status.DRAFT)
        self.assertEqual(document.approval_status, KnowledgeDocument.ApprovalStatus.DRAFT)
        self.assertFalse(AsyncOperation.objects.filter(source_id=str(document.pk)).exists())

    def test_submit_review_and_hr_approve_dispatches_index(self):
        document = KnowledgeDocument.objects.create(title='待审核库', content='content', created_by=self.user)
        submit_view = KnowledgeDocumentViewSet.as_view({'post': 'submit_review'})
        submit_request = self.factory.post(f'/knowledge/documents/{document.id}/submit-review/')
        force_authenticate(submit_request, user=self.user)

        submit_response = submit_view(submit_request, pk=str(document.id))
        self.assertEqual(submit_response.status_code, 200)
        document.refresh_from_db()
        self.assertEqual(document.approval_status, KnowledgeDocument.ApprovalStatus.PENDING_REVIEW)

        approve_view = KnowledgeDocumentViewSet.as_view({'post': 'approve'})
        approve_request = self.factory.post(f'/knowledge/documents/{document.id}/approve/')
        force_authenticate(approve_request, user=self.hr)

        approve_response = approve_view(approve_request, pk=str(document.id))

        self.assertEqual(approve_response.status_code, 200)
        document.refresh_from_db()
        self.assertEqual(document.approval_status, KnowledgeDocument.ApprovalStatus.APPROVED)
        self.assertEqual(document.status, KnowledgeDocument.Status.INDEXING)
        operation = AsyncOperation.objects.get(pk=approve_response.data['operation']['operation_id'])
        self.assertEqual(operation.dispatches.get().payload, {'operation_id': str(operation.pk)})

    def test_candidate_cannot_approve_document(self):
        document = KnowledgeDocument.objects.create(
            title='待审核库',
            content='content',
            created_by=self.user,
            approval_status=KnowledgeDocument.ApprovalStatus.PENDING_REVIEW,
        )
        view = KnowledgeDocumentViewSet.as_view({'post': 'approve'})
        request = self.factory.post(f'/knowledge/documents/{document.id}/approve/')
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(document.id))

        self.assertEqual(response.status_code, 403)

    def test_import_markdown_batch_creates_draft_document(self):
        view = KnowledgeImportBatchViewSet.as_view({'post': 'create'})
        upload = SimpleUploadedFile('rag.md', b'# RAG\n\nquestion: how to improve retrieval?', content_type='text/markdown')
        request = self.factory.post('/knowledge/import-batches/', {
            'files': [upload],
            'job_positions': 'AI 应用开发',
            'ability_tags': 'RAG,检索',
        }, format='multipart')
        force_authenticate(request, user=self.user)

        response = view(request)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(response.data['operations']), 1)
        self.assertEqual(KnowledgeImportBatch.objects.count(), 1)
        batch = KnowledgeImportBatch.objects.get()
        import_file = batch.import_files.get()
        process_import_file(str(import_file.id))
        document = KnowledgeDocument.objects.get()
        self.assertEqual(document.approval_status, KnowledgeDocument.ApprovalStatus.DRAFT)
        self.assertEqual(document.status, KnowledgeDocument.Status.DRAFT)
        self.assertEqual(document.parse_status, KnowledgeDocument.ParseStatus.PARSED)
        self.assertTrue(document.parsed_content.get('blocks'))
        self.assertIn('RAG', document.ability_tags)

    def test_import_invalid_file_records_error_without_document(self):
        view = KnowledgeImportBatchViewSet.as_view({'post': 'create'})
        upload = SimpleUploadedFile('image.png', b'not supported', content_type='image/png')
        request = self.factory.post('/knowledge/import-batches/', {'files': [upload]}, format='multipart')
        force_authenticate(request, user=self.user)

        response = view(request)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['operations'], [])
        batch = KnowledgeImportBatch.objects.get()
        import_file = batch.import_files.get()
        with self.assertRaises(Exception):
            process_import_file(str(import_file.id))
        batch.refresh_from_db()
        self.assertEqual(batch.failed_count, 1)
        self.assertEqual(KnowledgeDocument.objects.count(), 0)
