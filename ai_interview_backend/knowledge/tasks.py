from celery import shared_task
from django.conf import settings

from .importers import parse_knowledge_file
from .models import KnowledgeDocument, KnowledgeImportBatch, KnowledgeImportFile
from .services import index_document


def refresh_import_batch_stats(batch: KnowledgeImportBatch):
    import_files = list(batch.import_files.all())
    errors = [
        {'file': item.original_name, 'error': item.error_message}
        for item in import_files
        if item.status == KnowledgeImportFile.Status.FAILED
    ]
    success_count = sum(1 for item in import_files if item.status == KnowledgeImportFile.Status.IMPORTED)
    batch.success_count = success_count
    batch.failed_count = len(errors)
    batch.error_log = errors
    if success_count and errors:
        batch.status = KnowledgeImportBatch.Status.PARTIAL_FAILED
    elif success_count:
        batch.status = KnowledgeImportBatch.Status.COMPLETED
    elif errors:
        batch.status = KnowledgeImportBatch.Status.FAILED
    else:
        batch.status = KnowledgeImportBatch.Status.PROCESSING
    batch.save(update_fields=['success_count', 'failed_count', 'error_log', 'status', 'updated_at'])


def process_import_file(import_file_id: str):
    import_file = KnowledgeImportFile.objects.select_related('batch', 'batch__uploaded_by').get(id=import_file_id)
    batch = import_file.batch
    options = batch.options or {}
    import_file.status = KnowledgeImportFile.Status.PROCESSING
    import_file.error_message = ''
    import_file.save(update_fields=['status', 'error_message', 'updated_at'])
    try:
        import_file.source_file.open('rb')
        parsed = parse_knowledge_file(
            import_file.source_file,
            enable_ocr=getattr(settings, 'DOCLING_ENABLE_OCR', True),
            ocr_lang=getattr(settings, 'PADDLEOCR_LANG', 'ch'),
        )
        document = KnowledgeDocument.objects.create(
            import_batch=batch,
            title=options.get('title') or parsed.title,
            content=parsed.content,
            source_type=options.get('source_type') or parsed.source_type,
            source_file=import_file.source_file.name,
            file_type=parsed.file_type,
            parse_status=KnowledgeDocument.ParseStatus.PARSED,
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
            parser_fallback_reason=parsed.parser_fallback_reason,
            parsed_content=parsed.parsed_content,
            ocr_enabled=parsed.ocr_enabled,
            visibility=options.get('visibility') or KnowledgeDocument.Visibility.PRIVATE,
            job_positions=options.get('job_positions') or parsed.job_positions,
            ability_tags=options.get('ability_tags') or parsed.ability_tags,
            difficulty=options.get('difficulty') or parsed.difficulty,
            status=KnowledgeDocument.Status.DRAFT,
            approval_status=KnowledgeDocument.ApprovalStatus.DRAFT,
            created_by=batch.uploaded_by,
        )
        import_file.document = document
        import_file.status = KnowledgeImportFile.Status.IMPORTED
        import_file.save(update_fields=['document', 'status', 'updated_at'])
        return document
    except Exception as exc:
        import_file.status = KnowledgeImportFile.Status.FAILED
        import_file.error_message = str(exc)[:2000]
        import_file.save(update_fields=['status', 'error_message', 'updated_at'])
        raise
    finally:
        try:
            import_file.source_file.close()
        except Exception:
            pass
        refresh_import_batch_stats(batch)


@shared_task
def process_knowledge_import_file(import_file_id: str):
    document = process_import_file(import_file_id)
    return {'import_file_id': import_file_id, 'document_id': str(document.id)}


@shared_task
def reparse_knowledge_document(document_id: str):
    document = KnowledgeDocument.objects.get(id=document_id)
    if not document.source_file:
        return {'document_id': str(document.id), 'status': document.parse_status, 'skipped': True}
    document.parse_status = KnowledgeDocument.ParseStatus.PARSING
    document.parser_fallback_reason = ''
    document.save(update_fields=['parse_status', 'parser_fallback_reason', 'updated_at'])
    try:
        document.source_file.open('rb')
        parsed = parse_knowledge_file(
            document.source_file,
            enable_ocr=getattr(settings, 'DOCLING_ENABLE_OCR', True),
            ocr_lang=getattr(settings, 'PADDLEOCR_LANG', 'ch'),
        )
        document.content = parsed.content
        document.source_type = parsed.source_type
        document.file_type = parsed.file_type
        document.parse_status = KnowledgeDocument.ParseStatus.PARSED
        document.parser_name = parsed.parser_name
        document.parser_version = parsed.parser_version
        document.parser_fallback_reason = parsed.parser_fallback_reason
        document.parsed_content = parsed.parsed_content
        document.ocr_enabled = parsed.ocr_enabled
        document.status = KnowledgeDocument.Status.DRAFT
        document.approval_status = KnowledgeDocument.ApprovalStatus.DRAFT
        document.chunk_count = 0
        document.chunks.all().delete()
        document.save(update_fields=[
            'content', 'source_type', 'file_type', 'parse_status', 'parser_name',
            'parser_version', 'parser_fallback_reason', 'parsed_content', 'ocr_enabled',
            'status', 'approval_status', 'chunk_count', 'updated_at',
        ])
    except Exception as exc:
        document.parse_status = KnowledgeDocument.ParseStatus.FAILED
        document.parser_fallback_reason = str(exc)[:2000]
        document.save(update_fields=['parse_status', 'parser_fallback_reason', 'updated_at'])
        raise
    finally:
        try:
            document.source_file.close()
        except Exception:
            pass
    return {'document_id': str(document.id), 'status': document.parse_status}


@shared_task
def reindex_knowledge_document(document_id: str):
    document = KnowledgeDocument.objects.get(id=document_id)
    index_document(document)
    return {
        'document_id': str(document.id),
        'status': document.status,
        'chunk_count': document.chunk_count,
    }
