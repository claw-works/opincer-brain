"""PDF 文档解析器"""

import io
from typing import Any, Dict

from pypdf import PdfReader

from app.services.parser.base import BaseParser


class PDFParser(BaseParser):
    """使用 pypdf 提取 PDF 文本"""

    def parse(self, data: bytes, filename: str) -> Dict[str, Any]:
        reader = PdfReader(io.BytesIO(data))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())

        metadata = {}
        if reader.metadata:
            if reader.metadata.title:
                metadata["title"] = reader.metadata.title
            if reader.metadata.author:
                metadata["author"] = reader.metadata.author

        return {
            "text": "\n\n".join(pages_text),
            "pages": len(reader.pages),
            "metadata": metadata,
        }
