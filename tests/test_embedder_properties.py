"""embedder 纯逻辑的属性测试（hypothesis）。

覆盖 tasks.md 的 Correctness Properties：
  - Property 4: 批处理切分保序且不超上限（Validates: Requirements 3.5）
  - Property 5: 超长片段截断后不超 token 上限（Validates: Requirements 3.7）

被测的 `_batched` / `_truncate_to_token_limit` / `_estimate_tokens` 是纯函数，
embedder 模块对 dashscope 采用延迟导入，故无需安装该 SDK 即可运行本测试。
每条属性至少运行 100 个样例（hypothesis 默认 max_examples=100）。

运行：
  .venv/Scripts/python -m pytest claw-works/opincer-brain/tests -q
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# 让 `import app.services.embedder` 可用（仓库根为 opincer-brain）。
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.embedder import (  # noqa: E402
    EMBED_BATCH_MAX,
    MAX_TOKENS_PER_TEXT,
    _batched,
    _estimate_tokens,
    _truncate_to_token_limit,
)

texts_strategy = st.lists(st.text(max_size=50), max_size=60)


# ── Property 4: 批处理切分保序且不超上限 ──────────────────────────────
@settings(max_examples=200)
@given(texts=texts_strategy, size=st.integers(min_value=1, max_value=20))
def test_batched_preserves_order_and_caps_size(texts, size):
    batches = _batched(texts, size)

    # 1) 每批不超过 size。
    for b in batches:
        assert len(b) <= size

    # 2) 拼接所有批 == 原始列表（保序、不丢、不重、不增）。
    flattened = [t for b in batches for t in b]
    assert flattened == texts

    # 3) 总条数守恒。
    assert sum(len(b) for b in batches) == len(texts)

    # 4) 除最后一批外，其余批都恰好为 size（紧凑切分）。
    for b in batches[:-1]:
        assert len(b) == size


@settings(max_examples=100)
@given(texts=texts_strategy)
def test_batched_with_embed_batch_max_caps_at_10(texts):
    # 用生产实际批大小 EMBED_BATCH_MAX(=10) 切分，单批绝不超过 10 条。
    batches = _batched(texts, EMBED_BATCH_MAX)
    for b in batches:
        assert len(b) <= EMBED_BATCH_MAX
    assert [t for b in batches for t in b] == texts


def test_batched_empty_yields_no_batches():
    assert _batched([], EMBED_BATCH_MAX) == []


# ── Property 5: 超长片段截断后不超 token 上限 ────────────────────────
@settings(max_examples=200)
@given(text=st.text(max_size=MAX_TOKENS_PER_TEXT * 2 + 100))
def test_truncate_never_exceeds_token_limit(text):
    out = _truncate_to_token_limit(text)

    # 1) 截断后估算 token 数不超过上限。
    assert _estimate_tokens(out) <= MAX_TOKENS_PER_TEXT

    # 2) 不超长的输入原样返回（不误伤）。
    if _estimate_tokens(text) <= MAX_TOKENS_PER_TEXT:
        assert out == text
    else:
        # 3) 超长输入截断为原文前缀（保留开头语义），且为「不超限的最长前缀」：
        #    再多取一个字符就会超限。
        assert text.startswith(out)
        assert len(out) < len(text)
        assert _estimate_tokens(text[: len(out) + 1]) > MAX_TOKENS_PER_TEXT


@settings(max_examples=50)
@given(n=st.integers(min_value=0, max_value=MAX_TOKENS_PER_TEXT * 5))
def test_truncate_boundary_lengths(n):
    # 全 ASCII 文本（约 4 字符/token）：覆盖 token 上限边界附近。
    text = "x" * n
    out = _truncate_to_token_limit(text)
    assert _estimate_tokens(out) <= MAX_TOKENS_PER_TEXT
    if _estimate_tokens(text) <= MAX_TOKENS_PER_TEXT:
        assert out == text
    else:
        # 截断到不超限的最长前缀：英文应能保留远多于 MAX_TOKENS 个字符
        # （旧的按字符截断会在 8192 字符处腰斩，这里验证不再发生）。
        assert text.startswith(out)
        assert len(out) > MAX_TOKENS_PER_TEXT


def test_truncate_non_string_raises_embed_error():
    # 截断机制本身失败（非字符串入参）必须抛 EmbedError，不静默跳过。
    from app.services.embedder import EmbedError
    import pytest

    with pytest.raises(EmbedError):
        _truncate_to_token_limit(12345)  # type: ignore[arg-type]


# ── _estimate_tokens: CJK 感知启发式 ──────────────────────────────────
@settings(max_examples=100)
@given(text=st.text(max_size=500))
def test_estimate_tokens_is_conservative_and_monotonic(text):
    est = _estimate_tokens(text)
    # 估算值不应超过字符数（CJK 1:1，非 CJK 更少），即仍是保守上界。
    assert est <= len(text) or len(text) == 0
    # 单调性：前缀的估算 token 不超过整体（截断二分依赖此性质）。
    if text:
        assert _estimate_tokens(text[:-1]) <= est


def test_estimate_tokens_english_cheaper_than_chinese():
    # 同字符数下，纯英文的估算 token 应远低于纯中文（这正是修复点）。
    english = "a" * 400
    chinese = "中" * 400
    assert _estimate_tokens(english) < _estimate_tokens(chinese)
    assert _estimate_tokens(chinese) == 400          # 中文 1:1
    assert _estimate_tokens(english) == 100          # 英文 ~4 字符/token
