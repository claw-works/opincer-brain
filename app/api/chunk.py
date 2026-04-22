"""文本分块 API — 将长文本按语义切分为多个片段"""

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.chunker import split_text

router = APIRouter()


class ChunkRequest(BaseModel):
    text: str
    chunk_size: int = 1000
    chunk_overlap: int = 200


class ChunkItem(BaseModel):
    index: int
    content: str
    char_count: int


class ChunkResult(BaseModel):
    chunks: List[ChunkItem]
    total_chunks: int


@router.post("", response_model=ChunkResult)
async def chunk_text(req: ChunkRequest):
    """将长文本切分为多个片段"""
    pieces = split_text(req.text, req.chunk_size, req.chunk_overlap)
    items = [
        ChunkItem(index=i, content=c, char_count=len(c))
        for i, c in enumerate(pieces)
    ]
    return ChunkResult(chunks=items, total_chunks=len(items))
