"""Office 文档 → PDF 转换服务（用于 Web 端在线预览）。

复用镜像内的 LibreOffice（headless）把 doc/docx/xls/xlsx/ppt/pptx 转成 PDF，
前端再用已有的 PDF 预览渲染。纯转换逻辑、无状态，不依赖也不影响 parse/chunk/embed。

设计要点：
- 用 `soffice --headless --convert-to pdf` 子进程转换；每次用独立临时目录，转完即清理。
- 设超时，避免坏文件卡死 worker。
- 失败抛 ConvertError，由路由层映射为 5xx，调用方据此降级为下载。
"""

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

# 可转换为 PDF 预览的 Office 扩展名（小写，含点）。
SUPPORTED_EXTS = frozenset(
    [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".rtf", ".csv"]
)

# 单次转换超时（秒）。LibreOffice 首次启动较慢，给足余量。
CONVERT_TIMEOUT = 120

# LibreOffice 可执行名：镜像装的是 libreoffice-nogui，提供 soffice。
_SOFFICE_BIN = os.environ.get("SOFFICE_BIN", "soffice")


class ConvertError(Exception):
    """Office → PDF 转换失败。"""


def is_supported(ext: str) -> bool:
    """判断扩展名（含点、任意大小写）是否支持转 PDF 预览。"""
    return ext.lower() in SUPPORTED_EXTS


def convert_to_pdf(data: bytes, filename: str) -> bytes:
    """把 Office 文档字节转成 PDF 字节。

    Args:
        data: 原始文档字节。
        filename: 原始文件名（取扩展名用，决定 LibreOffice 输入解析）。

    Returns:
        转换后的 PDF 字节。

    Raises:
        ConvertError: 不支持的格式、转换超时或 LibreOffice 失败时抛出。
    """
    ext = os.path.splitext(filename)[1].lower()
    if not is_supported(ext):
        raise ConvertError(f"不支持转换为 PDF 预览的格式: {ext}")

    workdir = tempfile.mkdtemp(prefix="office2pdf_")
    try:
        # 输入文件名用安全的固定名 + 原扩展名，避免文件名里的特殊字符影响子进程。
        src_path = os.path.join(workdir, f"input{ext}")
        with open(src_path, "wb") as f:
            f.write(data)

        # 每个转换用独立的 user profile，避免并发时 LibreOffice 单实例锁冲突。
        profile_dir = os.path.join(workdir, "lo_profile")
        cmd = [
            _SOFFICE_BIN,
            "--headless",
            "--norestore",
            "--nologo",
            f"-env:UserInstallation=file://{profile_dir}",
            "--convert-to",
            "pdf",
            "--outdir",
            workdir,
            src_path,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=CONVERT_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise ConvertError(f"转换超时（>{CONVERT_TIMEOUT}s）") from e
        except FileNotFoundError as e:
            # soffice 不存在（镜像未装 LibreOffice）
            raise ConvertError("LibreOffice 不可用（soffice 未安装）") from e

        if proc.returncode != 0:
            logger.error(
                "soffice 转换失败: rc=%s stderr=%s",
                proc.returncode,
                proc.stderr.decode("utf-8", "ignore")[:500],
            )
            raise ConvertError("LibreOffice 转换失败")

        out_path = os.path.join(workdir, "input.pdf")
        if not os.path.exists(out_path):
            raise ConvertError("转换未产出 PDF")

        with open(out_path, "rb") as f:
            pdf = f.read()
        if not pdf:
            raise ConvertError("转换产出的 PDF 为空")

        logger.info("office→pdf 转换完成: %s (%d bytes -> %d bytes)", ext, len(data), len(pdf))
        return pdf
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
