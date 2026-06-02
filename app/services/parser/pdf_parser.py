"""PDF 文档解析器 — pypdf 优先提取文本层，提取为空时 fallback 到 PaddleOCR"""

import io
import logging
from typing import Any, Dict

from pypdf import PdfReader

from app.services.parser.base import BaseParser
from app.services.parser.ocr_fallback import ocr_pdf_pages

logger = logging.getLogger(__name__)

# pypdf 提取的文本字符数低于此阈值时，认为"提取为空"，触发 OCR fallback
MIN_TEXT_THRESHOLD = 50


class PDFParser(BaseParser):
    """
    PDF 解析策略：
    1. 用 pypdf 提取文本层（快，适合 Word/LaTeX 导出的 PDF）
    2. 如果提取的文本过少（< 50 字符），fallback 到 PaddleOCR（适合扫描件）
    """

    def parse(self, data: bytes, filename: str) -> Dict[str, Any]:
        reader = PdfReader(io.BytesIO(data))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())

        full_text = "\n\n".join(pages_text)
        num_pages = len(reader.pages)

        # 提取元数据
        metadata: Dict[str, Any] = {}
        if reader.metadata:
            if reader.metadata.title:
                metadata["title"] = reader.metadata.title
            if reader.metadata.author:
                metadata["author"] = reader.metadata.author

        # 判断是否需要 OCR fallback
        if len(full_text.strip()) < MIN_TEXT_THRESHOLD:
            logger.info(
                f"pypdf extracted only {len(full_text.strip())} chars from {filename}, "
                f"attempting OCR fallback..."
            )
            ocr_text = ocr_pdf_pages(data)
            if ocr_text and len(ocr_text.strip()) > len(full_text.strip()):
                full_text = ocr_text
                metadata["parse_method"] = "ocr"
                logger.info(f"OCR fallback succeeded: {len(full_text)} chars extracted")
            else:
                metadata["parse_method"] = "pypdf"
                if not full_text.strip():
                    metadata["warning"] = "文档可能是扫描件且 OCR 未能识别内容"
        else:
            metadata["parse_method"] = "pypdf"

        return {
            "text": full_text,
            "pages": num_pages,
            "metadata": metadata,
        }
