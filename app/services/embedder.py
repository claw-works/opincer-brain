"""向量化服务 — 封装阿里云百炼 DashScope text-embedding-v4

走 DashScope 原生 SDK（而非 OpenAI 兼容接口），因为只有原生 SDK 支持
`text_type`(query/document) 与 `output_type`(dense&sparse) 参数。

职责：
- 一次调用同时产出稠密(dense)与稀疏(sparse)向量，维度固定 1024。
- 按每批 ≤10 条切批循环调用 DashScope，并按输入顺序对齐 index。
- 单条 token 估算超过 8192 时先截断后再向量化，保证整批不因单条超长整体失败；
  截断机制本身失败则使整批失败，不静默跳过该片段。
- 凭据从环境变量 DASHSCOPE_API_KEY 读取。
"""

import logging
import os
from http import HTTPStatus
from typing import Dict, List, TypedDict

logger = logging.getLogger(__name__)

# 向量模型与约束（见需求 3.x）
MODEL = "text-embedding-v4"
DEFAULT_DIMENSION = 1024
# 单次请求最多 10 条片段
EMBED_BATCH_MAX = 10
# 单条片段最长 8192 token
MAX_TOKENS_PER_TEXT = 8192


class EmbedError(Exception):
    """向量化失败（DashScope 报错、凭据缺失或截断机制失败）。

    调用方（/embed 路由）据此返回 5xx，由 opincer-service 侧按
    「临时不可用」或「失败重试」处理，不静默跳过片段。
    """


class SparseItem(TypedDict):
    i: int  # token 词表索引
    v: float  # 权重


class EmbeddingItem(TypedDict):
    index: int  # 在输入列表中的序号
    dense: List[float]  # 稠密向量，长度 = dimension
    sparse: List[SparseItem]  # 稀疏向量


class EmbedResult(TypedDict):
    embeddings: List[EmbeddingItem]
    total_tokens: int


def _estimate_tokens(text: str) -> int:
    """估算文本 token 数（保守上界，零额外依赖）。

    text-embedding-v4 并非 tiktoken 编码，任何分词库都只是近似且会引入依赖与
    镜像体积，故在此用按字符类型区分的启发式：
      - CJK 字符（中日韩）≈ 1 token / 字；
      - 其余字符（英文 / 代码 / 标点）≈ 1 token / 4 字符。
    两类分别估算后相加，再向上取整。相比旧实现 len(text) 一刀切，避免了纯英文 /
    代码片段在实际只有两三千 token 时就被粗暴截断，提升英文与技术文档的召回完备性；
    同时对中文仍保持 1:1 的保守上界，不会超过模型 8192 token 上限。
    """
    cjk = 0
    for ch in text:
        # CJK 统一表意文字及扩展、兼容区、假名、谚文等常见东亚文字区间。
        o = ord(ch)
        if (
            0x4E00 <= o <= 0x9FFF      # CJK 统一表意文字
            or 0x3400 <= o <= 0x4DBF   # 扩展 A
            or 0xF900 <= o <= 0xFAFF   # 兼容表意文字
            or 0x3040 <= o <= 0x30FF   # 平假名 / 片假名
            or 0xAC00 <= o <= 0xD7A3   # 谚文音节
        ):
            cjk += 1
    non_cjk = len(text) - cjk
    # 非 CJK 按 4 字符/token 估算，向上取整。
    return cjk + (non_cjk + 3) // 4


def _truncate_to_token_limit(text: str) -> str:
    """将超长文本按估算 token 数截断到上限以内（保留尽可能长的前缀）。

    估算 token 数随前缀长度单调不减，故用二分查找定位「估算 token ≤ 上限」的
    最长前缀。相比按固定字符数截断，英文/代码不会被过早腰斩。截断机制本身失败
    （如非字符串入参）则抛出 EmbedError，由上层使整批失败。
    """
    try:
        if _estimate_tokens(text) <= MAX_TOKENS_PER_TEXT:
            return text
        # 二分最长合法前缀：lo 始终合法，hi 始终超限。
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _estimate_tokens(text[:mid]) <= MAX_TOKENS_PER_TEXT:
                lo = mid
            else:
                hi = mid - 1
        truncated = text[:lo]
        logger.warning(
            "片段超过 token 上限，已截断: 原长 %d 字符 -> %d 字符（估算 %d tokens）",
            len(text),
            len(truncated),
            _estimate_tokens(truncated),
        )
        return truncated
    except EmbedError:
        raise
    except Exception as e:  # noqa: BLE001 — 截断机制本身失败必须使整批失败
        raise EmbedError(f"片段截断失败: {e}") from e


def _batched(texts: List[str], size: int) -> List[List[str]]:
    """按 size 切批，保持原始顺序。"""
    return [texts[i : i + size] for i in range(0, len(texts), size)]


def _require_api_key() -> str:
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise EmbedError("缺少 DASHSCOPE_API_KEY 环境变量")
    return api_key


def _call_dashscope(batch: List[str], text_type: str, dimension: int, api_key: str):
    # 延迟导入 dashscope：纯逻辑（切批 / 截断）单测无需安装该 SDK，
    # 仅在真正发起向量化请求时才依赖它。
    import dashscope

    resp = dashscope.TextEmbedding.call(
        model=MODEL,
        input=batch,
        text_type=text_type,
        dimension=dimension,
        output_type="dense&sparse",
        api_key=api_key,
    )
    if resp.status_code != HTTPStatus.OK:
        # 错误细节仅记日志，不外泄底层报错
        logger.error(
            "DashScope 向量化失败: status=%s code=%s request_id=%s",
            resp.status_code,
            getattr(resp, "code", ""),
            getattr(resp, "request_id", ""),
        )
        raise EmbedError(f"DashScope 向量化请求失败: HTTP {resp.status_code}")
    return resp


def _parse_sparse(raw_sparse) -> List[SparseItem]:
    """将 DashScope sparse_embedding [{index,value,token}] 转为 [{i,v}]。"""
    items: List[SparseItem] = []
    for entry in raw_sparse or []:
        items.append({"i": int(entry["index"]), "v": float(entry["value"])})
    return items


def embed_texts(
    texts: List[str],
    text_type: str = "document",
    dimension: int = DEFAULT_DIMENSION,
) -> EmbedResult:
    """向量化文本列表，返回 dense + sparse 向量。

    Args:
        texts: 待向量化文本列表（1 条或多条）。
        text_type: "document"（入库片段）或 "query"（检索查询）。
        dimension: 稠密向量维度，固定 1024。

    Returns:
        EmbedResult，embeddings 按输入顺序对齐 index，并附带 total_tokens。

    Raises:
        EmbedError: DashScope 报错、凭据缺失或截断机制失败时抛出，
            不静默跳过任何片段。
    """
    if not texts:
        return {"embeddings": [], "total_tokens": 0}

    api_key = _require_api_key()

    # 超长片段先截断（截断失败会抛 EmbedError 使整批失败）
    prepared = [_truncate_to_token_limit(t) for t in texts]

    embeddings: List[EmbeddingItem] = []
    total_tokens = 0

    offset = 0
    for batch in _batched(prepared, EMBED_BATCH_MAX):
        resp = _call_dashscope(batch, text_type, dimension, api_key)

        output_embeddings = resp.output["embeddings"]
        # 按 text_index 排序对齐，确保与输入顺序一致
        output_embeddings = sorted(
            output_embeddings, key=lambda e: e["text_index"]
        )
        for item in output_embeddings:
            embeddings.append(
                {
                    "index": offset + item["text_index"],
                    "dense": list(item["embedding"]),
                    "sparse": _parse_sparse(item.get("sparse_embedding")),
                }
            )

        usage = resp.usage or {}
        total_tokens += int(usage.get("total_tokens", 0) or 0)
        offset += len(batch)

    logger.info(
        "向量化完成: %d 条片段, text_type=%s, total_tokens=%d",
        len(embeddings),
        text_type,
        total_tokens,
    )
    return {"embeddings": embeddings, "total_tokens": total_tokens}
