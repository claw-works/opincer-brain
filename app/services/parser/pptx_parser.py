"""PPTX 演示文稿解析器"""

import io
from typing import Any, Dict

from pptx import Presentation

from app.services.parser.base import BaseParser


class PPTXParser(BaseParser):
    """使用 python-pptx 提取 PPTX 文本"""

    def parse(self, data: bytes, filename: str) -> Dict[str, Any]:
        prs = Presentation(io.BytesIO(data))
        slides_text = []

        for i, slide in enumerate(prs.slides, 1):
            texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if text:
                            texts.append(text)
                if shape.has_table:
                    for row in shape.table.rows:
                        cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if cells:
                            texts.append(" | ".join(cells))
            if texts:
                slides_text.append(f"## 第 {i} 页\n\n" + "\n".join(texts))

        return {
            "text": "\n\n".join(slides_text),
            "pages": len(prs.slides),
            "metadata": {},
        }
