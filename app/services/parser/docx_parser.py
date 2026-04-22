"""DOCX 文档解析器"""

import io
from typing import Any, Dict

from docx import Document

from app.services.parser.base import BaseParser


class DOCXParser(BaseParser):
    """使用 python-docx 提取 DOCX 文本"""

    def parse(self, data: bytes, filename: str) -> Dict[str, Any]:
        doc = Document(io.BytesIO(data))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

        # 也提取表格内容
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    paragraphs.append(" | ".join(cells))

        metadata = {}
        if doc.core_properties.title:
            metadata["title"] = doc.core_properties.title
        if doc.core_properties.author:
            metadata["author"] = doc.core_properties.author

        return {
            "text": "\n\n".join(paragraphs),
            "pages": 0,
            "metadata": metadata,
        }
