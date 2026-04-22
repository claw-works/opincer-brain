"""文档解析 API — 从各种文件格式中提取纯文本"""

import os
import tempfile
from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.parser import registry

router = APIRouter()


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
    result = parser.parse(data, name)
    return ParseResult(**result)


def _get_ext(filename: str) -> str:
    _, ext = os.path.splitext(filename)
    return ext.lower()


async def _download(url: str) -> bytes:
    """下载文件内容"""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(502, f"下载文件失败: HTTP {resp.status_code}")
        return resp.content
