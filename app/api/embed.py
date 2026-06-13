"""向量化 API — 调用百炼 text-embedding-v4 生成 dense + sparse 向量"""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.embedder import DEFAULT_DIMENSION, EmbedError, embed_texts

router = APIRouter()


class EmbedRequest(BaseModel):
    texts: List[str]
    text_type: str = "document"  # "document"（入库）| "query"（检索）
    dimension: int = DEFAULT_DIMENSION


class SparseItem(BaseModel):
    i: int  # token 词表索引
    v: float  # 权重


class EmbeddingItem(BaseModel):
    index: int
    dense: List[float]
    sparse: List[SparseItem]


class EmbedResult(BaseModel):
    embeddings: List[EmbeddingItem]
    total_tokens: int


@router.post("", response_model=EmbedResult)
async def embed(req: EmbedRequest):
    """将文本列表向量化为稠密 + 稀疏向量"""
    try:
        result = embed_texts(req.texts, req.text_type, req.dimension)
    except EmbedError as e:
        # 向量化失败统一返回 5xx，由 opincer-service 侧按
        # 「临时不可用」或「失败重试」处理，不静默跳过片段
        raise HTTPException(502, str(e))
    return result
