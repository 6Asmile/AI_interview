# resumes/services.py
import logging
import os
from django.conf import settings
from django.core.files import File
from docx import Document
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extract_text_from_file(file_path: str) -> str:
    """
    优先使用知识库同源的 Docling/结构化解析链路提取文本，失败后回退到轻量解析。

    :param file_path: 文件在服务器上的完整物理路径。
    :return: 提取出的纯文本内容。
    """
    # 从文件名中获取扩展名
    _, extension = os.path.splitext(file_path)
    extension = extension.lower()

    try:
        parsed_text = extract_text_with_document_parser(file_path)
        if parsed_text.strip():
            return parsed_text
    except Exception as exc:
        logger.warning('结构化简历解析失败，回退到轻量解析: %s', exc)

    try:
        if extension == '.pdf':
            return extract_text_from_pdf(file_path)
        elif extension == '.docx':
            return extract_text_from_docx(file_path)
        elif extension in {'.txt', '.md'}:
            return extract_text_from_text(file_path)
        else:
            logger.warning("不支持的文件类型: %s", extension)
            return ""
    except Exception as e:
        logger.warning("从文件 %s 提取文本时出错: %s", file_path, e)
        return ""


def extract_text_with_document_parser(file_path: str) -> str:
    """
    复用知识库 DocumentParsingService，使简历解析与知识库文档解析保持一致。
    """
    from knowledge.importers import DocumentParsingService

    enable_ocr = str(getattr(settings, 'DOCLING_ENABLE_OCR', True)).lower() in {'1', 'true', 'yes', 'on'}
    ocr_lang = getattr(settings, 'PADDLEOCR_LANG', 'ch')
    parser = DocumentParsingService(enable_ocr=enable_ocr, ocr_lang=ocr_lang)
    with open(file_path, 'rb') as handle:
        django_file = File(handle, name=os.path.basename(file_path))
        parsed = parser.parse(django_file)
    return (parsed.content or '').strip()

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    使用 pypdf 从 PDF 文件中提取文本。
    """
    text = ""
    with open(pdf_path, 'rb') as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() or ""
    return text

def extract_text_from_docx(docx_path: str) -> str:
    """
    使用 python-docx 从 DOCX 文件中提取文本。
    """
    doc = Document(docx_path)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text


def extract_text_from_text(text_path: str) -> str:
    for encoding in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            with open(text_path, 'r', encoding=encoding) as handle:
                return handle.read()
        except UnicodeDecodeError:
            continue
    with open(text_path, 'r', encoding='utf-8', errors='ignore') as handle:
        return handle.read()
