"""文档预览转换 API — Office 文档转 PDF，供 Web 端在线预览。

把 doc/docx/xls/xlsx/ppt/pptx 等转成 PDF 字节返回，调用方（opincer-service）
拿到 PDF 后可缓存到 OSS 再交给前端用已有的 PDF 预览渲染。

与 /parse 解耦：/parse 提取纯文本用于检索/理解，/preview 产出 PDF 用于视觉预览。
"""

import os

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.services.office_converter import ConvertError, convert_to_pdf, is_supported

router = APIRouter()

# 预览转换的文件大小上限：100MB（Office 文档通常远小于此）。
MAX_FILE_SIZE = 100 * 1024 * 1024


class PreviewByURLRequest(BaseModel):
    file_url: str
    file_name: str


def _get_ext(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def _pdf_response(pdf: bytes) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.post("")
async def preview_by_url(req: PreviewByURLRequest):
    """按文件 URL 把 Office 文档转成 PDF 返回（application/pdf 字节流）。"""
    ext = _get_ext(req.file_name)
    if not is_supported(ext):
        raise HTTPException(400, f"不支持转换为 PDF 预览的格式: {ext}")

    data = await _download(req.file_url)
    try:
        pdf = convert_to_pdf(data, req.file_name)
    except ConvertError as e:
        # 转换失败：返回 502，调用方据此降级为下载，不外泄底层细节。
        raise HTTPException(502, str(e))
    return _pdf_response(pdf)


@router.post("/upload")
async def preview_by_upload(
    file: UploadFile = File(...),
    file_name: str = Form(None),
):
    """按上传的 Office 文档转成 PDF 返回。"""
    name = file_name or file.filename or "unknown"
    ext = _get_ext(name)
    if not is_supported(ext):
        raise HTTPException(400, f"不支持转换为 PDF 预览的格式: {ext}")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, f"文件过大，上限 {MAX_FILE_SIZE // (1024*1024)}MB")
    try:
        pdf = convert_to_pdf(data, name)
    except ConvertError as e:
        raise HTTPException(502, str(e))
    return _pdf_response(pdf)


async def _download(url: str) -> bytes:
    """下载文件内容，限制最大 MAX_FILE_SIZE。"""
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise HTTPException(502, f"下载文件失败: HTTP {resp.status_code}")
            content_length = resp.headers.get("content-length")
            if content_length and int(content_length) > MAX_FILE_SIZE:
                raise HTTPException(413, f"文件过大，上限 {MAX_FILE_SIZE // (1024*1024)}MB")
            chunks = []
            total = 0
            async for chunk in resp.aiter_bytes(chunk_size=1024 * 64):
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    raise HTTPException(413, f"文件过大，上限 {MAX_FILE_SIZE // (1024*1024)}MB")
                chunks.append(chunk)
            return b"".join(chunks)
