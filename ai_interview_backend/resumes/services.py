# resumes/services.py
import os
from django.conf import settings
from docx import Document
from pypdf import PdfReader

def extract_text_from_file(file_path: str) -> str:
    """
    根据文件扩展名，从 PDF 或 DOCX 文件中提取纯文本。

    :param file_path: 文件在服务器上的完整物理路径。
    :return: 提取出的纯文本内容。
    """
    # 从文件名中获取扩展名
    _, extension = os.path.splitext(file_path)
    extension = extension.lower()

    try:
        if extension == '.pdf':
            return extract_text_from_pdf(file_path)
        elif extension == '.docx':
            return extract_text_from_docx(file_path)
        else:
            print(f"不支持的文件类型: {extension}")
            return ""
    except Exception as e:
        print(f"从文件 {file_path} 提取文本时出错: {e}")
        return ""

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