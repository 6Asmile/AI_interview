import io
import os
import zipfile

from rest_framework.exceptions import ValidationError


SIGNATURES = {
    '.pdf': (b'%PDF-',),
    '.png': (b'\x89PNG\r\n\x1a\n',),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
    '.gif': (b'GIF87a', b'GIF89a'),
    '.webp': (b'RIFF',),
    '.bmp': (b'BM',),
    '.docx': (b'PK\x03\x04',),
    '.xlsx': (b'PK\x03\x04',),
    '.json': (b'{', b'['),
}
TEXT_EXTENSIONS = {'.txt', '.md', '.csv'}


def _head(uploaded, size=32):
    position = uploaded.tell() if hasattr(uploaded, 'tell') else 0
    uploaded.seek(0)
    value = uploaded.read(size)
    uploaded.seek(position or 0)
    return value.lstrip(b'\xef\xbb\xbf\x00\x20\x09\x0d\x0a') if value else b''


def _validate_zip(uploaded, *, max_uncompressed_bytes=250 * 1024 * 1024, max_members=5000, max_ratio=100):
    uploaded.seek(0)
    raw = uploaded.read()
    uploaded.seek(0)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) > max_members:
                raise ValidationError({'file': '压缩文档包含过多文件。', 'code': 'archive_member_limit'})
            total = sum(item.file_size for item in members)
            compressed = max(1, sum(item.compress_size for item in members))
            if total > max_uncompressed_bytes or total / compressed > max_ratio:
                raise ValidationError({'file': '压缩文档解压体积或压缩比异常。', 'code': 'archive_bomb_detected'})
    except zipfile.BadZipFile:
        raise ValidationError({'file': 'Office 文件结构无效。', 'code': 'invalid_office_archive'})


def validate_uploaded_file(uploaded, *, allowed_extensions, max_bytes, max_pdf_pages=1000):
    extension = os.path.splitext(uploaded.name)[1].lower()
    if extension not in allowed_extensions:
        raise ValidationError({'file': f'不支持的文件类型：{extension or "无扩展名"}。', 'code': 'unsupported_file_type'})
    if uploaded.size <= 0:
        raise ValidationError({'file': '文件内容为空。', 'code': 'empty_file'})
    if uploaded.size > max_bytes:
        raise ValidationError({'file': f'文件不能超过 {max_bytes // 1024 // 1024}MB。', 'code': 'file_too_large'})
    head = _head(uploaded)
    if extension in SIGNATURES and not any(head.startswith(item) for item in SIGNATURES[extension]):
        raise ValidationError({'file': '文件内容与扩展名不匹配。', 'code': 'file_signature_mismatch'})
    if extension in TEXT_EXTENSIONS:
        uploaded.seek(0)
        sample = uploaded.read(min(uploaded.size, 128 * 1024))
        uploaded.seek(0)
        if b'\x00' in sample:
            raise ValidationError({'file': '文本文件包含二进制内容。', 'code': 'binary_text_rejected'})
    if extension in {'.docx', '.xlsx'}:
        _validate_zip(uploaded)
    if extension == '.pdf':
        try:
            from pypdf import PdfReader
            uploaded.seek(0)
            pages = len(PdfReader(uploaded, strict=False).pages)
            uploaded.seek(0)
            if pages > max_pdf_pages:
                raise ValidationError({'file': f'PDF 不能超过 {max_pdf_pages} 页。', 'code': 'pdf_page_limit'})
        except ValidationError:
            raise
        except Exception:
            uploaded.seek(0)
            raise ValidationError({'file': 'PDF 文件结构无效或已损坏。', 'code': 'invalid_pdf'})
    return extension
