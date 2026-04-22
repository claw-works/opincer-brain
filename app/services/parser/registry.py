"""解析器注册表 — 根据文件扩展名选择对应的解析器"""

from typing import Optional

from app.services.parser.base import BaseParser
from app.services.parser.pdf_parser import PDFParser
from app.services.parser.docx_parser import DOCXParser
from app.services.parser.excel_parser import ExcelParser
from app.services.parser.pptx_parser import PPTXParser
from app.services.parser.text_parser import TextParser

_pdf = PDFParser()
_docx = DOCXParser()
_excel = ExcelParser()
_pptx = PPTXParser()
_text = TextParser()

_PARSERS: dict[str, BaseParser] = {
    # PDF
    ".pdf": _pdf,
    # Word
    ".docx": _docx,
    ".doc": _docx,  # .doc 尝试用 docx 解析，失败时返回错误提示
    # Excel
    ".xlsx": _excel,
    ".xls": _excel,  # openpyxl 只支持 xlsx，旧版 xls 会报错
    # PowerPoint
    ".pptx": _pptx,
    # 纯文本
    ".txt": _text,
    ".md": _text,
    ".csv": _text,
    ".json": _text,
    ".xml": _text,
    ".html": _text,
    ".htm": _text,
    ".yaml": _text,
    ".yml": _text,
    ".log": _text,
    # 电子书
    ".epub": _text,  # 简单处理，后续可用专门的 epub 解析器
}


def get_parser(ext: str) -> Optional[BaseParser]:
    """根据文件扩展名获取解析器，返回 None 表示不支持"""
    return _PARSERS.get(ext.lower())
