"""PaddleOCR fallback — 当 pypdf 提取不到文本时，用 OCR 识别扫描件"""

import io
import logging
import tempfile
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

# 延迟加载 PaddleOCR（首次调用时初始化，避免启动慢）
_ocr_instance = None


def _get_ocr():
    """延迟初始化 PaddleOCR 实例（单例）"""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from paddleocr import PaddleOCR
            _ocr_instance = PaddleOCR(
                use_angle_cls=True,  # 文字方向检测
                lang="ch",           # 中英文混合
                use_gpu=False,       # CPU 模式
                show_log=False,      # 不打印 paddle 内部日志
            )
            logger.info("PaddleOCR initialized (CPU mode)")
        except ImportError:
            logger.warning("PaddleOCR not installed, OCR fallback disabled")
            return None
    return _ocr_instance


def ocr_pdf_pages(data: bytes) -> Optional[str]:
    """
    用 PaddleOCR 对 PDF 的每一页做 OCR 识别。

    流程：PDF → 逐页渲染为图片 → OCR 提取文字 → 拼接返回。
    需要 pdf2image（依赖 poppler）将 PDF 页面转图片。

    Returns:
        提取到的全部文本，如果 OCR 不可用或失败返回 None。
    """
    ocr = _get_ocr()
    if ocr is None:
        return None

    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        logger.warning("pdf2image not installed, OCR fallback disabled")
        return None

    try:
        # 将 PDF 转为图片（150 DPI 平衡速度与清晰度）
        images = convert_from_bytes(data, dpi=150, fmt="jpeg")
    except Exception as e:
        logger.error(f"PDF to image conversion failed: {e}")
        return None

    all_text: List[str] = []

    for i, img in enumerate(images):
        # PaddleOCR 接受 numpy array 或文件路径
        # 保存到临时文件避免内存格式问题
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            img.save(tmp, format="JPEG", quality=85)
            tmp_path = tmp.name

        try:
            result = ocr.ocr(tmp_path, cls=True)
            if result and result[0]:
                page_lines = []
                for line in result[0]:
                    # line = [bbox, (text, confidence)]
                    if line and len(line) >= 2:
                        text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                        if text.strip():
                            page_lines.append(text.strip())
                if page_lines:
                    all_text.append("\n".join(page_lines))
        except Exception as e:
            logger.warning(f"OCR failed on page {i+1}: {e}")
        finally:
            os.unlink(tmp_path)

    if not all_text:
        return None

    return "\n\n".join(all_text)
