"""文档解析 API — 从各种文件格式中提取纯文本"""

import os
import tempfile
from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.parser import registry

router = APIRouter()

# 下载/上传文件大小上限：50MB
MAX_FILE_SIZE = 50 * 1024 * 1024


class ParseByURLRequest(BaseModel):
    file_url: str
    file_name: str


class ParseResult(BaseModel):
    text: str
    pages: int = 0
    metadata: dict = {}


@router.post("", response_model=ParseResult)
async def parse_by_url(req: ParseByURLRequest):
    """通过文件 URL 解析文档，提取纯文本"""
    ext = _get_ext(req.file_name)
    parser = registry.get_parser(ext)
    if parser is None:
        raise HTTPException(400, f"不支持的文件格式: {ext}")

    data = await _download(req.file_url)
    result = parser.parse(data, req.file_name)
    return ParseResult(**result)


@router.post("/upload", response_model=ParseResult)
async def parse_by_upload(
    file: UploadFile = File(...),
    file_name: Optional[str] = Form(None),
):
    """通过文件上传解析文档，提取纯文本"""
    name = file_name or file.filename or "unknown"
    ext = _get_ext(name)
    parser = registry.get_parser(ext)
    if parser is None:
        raise HTTPException(400, f"不支持的文件格式: {ext}")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, f"文件过大，上限 {MAX_FILE_SIZE // (1024*1024)}MB")
    result = parser.parse(data, name)
    return ParseResult(**result)


def _get_ext(filename: str) -> str:
    _, ext = os.path.splitext(filename)
    return ext.lower()


async def _download(url: str) -> bytes:
    """下载文件内容，限制最大 50MB"""
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise HTTPException(502, f"下载文件失败: HTTP {resp.status_code}")

            # 检查 Content-Length（如果服务端提供）
            content_length = resp.headers.get("content-length")
            if content_length and int(content_length) > MAX_FILE_SIZE:
                raise HTTPException(413, f"文件过大 ({int(content_length) // (1024*1024)}MB)，上限 {MAX_FILE_SIZE // (1024*1024)}MB")

            # 流式读取，边读边检查大小
            chunks = []
            total = 0
            async for chunk in resp.aiter_bytes(chunk_size=1024 * 64):
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    raise HTTPException(413, f"文件过大，上限 {MAX_FILE_SIZE // (1024*1024)}MB")
                chunks.append(chunk)

            return b"".join(chunks)
