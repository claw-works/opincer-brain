"""PDF 文档解析器 — PyMuPDF4LLM 输出 Markdown，fallback PaddleOCR 处理扫描件"""

import io
import logging
from typing import Any, Dict

import pymupdf4llm
import pymupdf

from app.services.parser.base import BaseParser
from app.services.parser.ocr_fallback import ocr_pdf_pages

logger = logging.getLogger(__name__)

# 提取的文本字符数低于此阈值时，认为"提取为空"，触发 OCR fallback
MIN_TEXT_THRESHOLD = 50


class PDFParser(BaseParser):
    """
    PDF 解析策略：
    1. 用 PyMuPDF4LLM 提取 Markdown（快，保留标题/表格/列表/粗体结构）
    2. 如果提取的文本过少（< 50 字符），fallback 到 PaddleOCR（适合扫描件）

    输出格式：GitHub 风格 Markdown（而非纯文本），LLM 理解力更好。
    """

    def parse(self, data: bytes, filename: str) -> Dict[str, Any]:
        # 用 pymupdf 打开 PDF（从 bytes）
        doc = pymupdf.open(stream=data, filetype="pdf")
        num_pages = len(doc)

        # 提取元数据
        metadata: Dict[str, Any] = {}
        pdf_metadata = doc.metadata
        if pdf_metadata:
            if pdf_metadata.get("title"):
                metadata["title"] = pdf_metadata["title"]
            if pdf_metadata.get("author"):
                metadata["author"] = pdf_metadata["author"]

        # 用 pymupdf4llm 提取 Markdown
        try:
            md_text = pymupdf4llm.to_markdown(doc)
        except Exception as e:
            logger.warning(f"pymupdf4llm extraction failed: {e}, falling back to plain text")
            # Fallback: 用 pymupdf 基础文本提取
            md_text = ""
            for page in doc:
                text = page.get_text()
                if text:
                    md_text += text.strip() + "\n\n"

        doc.close()

        # 判断是否需要 OCR fallback
        # 去掉 markdown 标记后计算实际文本量
        plain_check = md_text.replace("#", "").replace("*", "").replace("-", "").replace("|", "").strip()

        if len(plain_check) < MIN_TEXT_THRESHOLD:
            logger.info(
                f"PyMuPDF4LLM extracted only {len(plain_check)} chars from {filename}, "
                f"attempting OCR fallback..."
            )
            ocr_text = ocr_pdf_pages(data)
            if ocr_text and len(ocr_text.strip()) > len(plain_check):
                md_text = ocr_text
                metadata["parse_method"] = "ocr"
                metadata["output_format"] = "text"
                logger.info(f"OCR fallback succeeded: {len(md_text)} chars extracted")
            else:
                metadata["parse_method"] = "pymupdf4llm"
                metadata["output_format"] = "markdown"
                if not plain_check:
                    metadata["warning"] = "文档可能是扫描件且 OCR 未能识别内容"
        else:
            metadata["parse_method"] = "pymupdf4llm"
            metadata["output_format"] = "markdown"

        return {
            "text": md_text.strip(),
            "pages": num_pages,
            "metadata": metadata,
        }
