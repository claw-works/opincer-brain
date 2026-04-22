"""文本分块器 — 按段落和字符数切分文本"""

from typing import List

# 段落分隔符优先级
_SEPARATORS = ["\n\n", "\n", "。", ".", "！", "!", "？", "?", "；", ";", " "]


def split_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[str]:
    """
    将长文本切分为多个片段。

    策略：优先按段落分隔，如果单段超过 chunk_size 则按句子分隔，
    最后按字符数硬切。相邻片段有 chunk_overlap 字符的重叠。
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    _recursive_split(text, chunk_size, chunk_overlap, _SEPARATORS, chunks)
    return chunks


def _recursive_split(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: List[str],
    result: List[str],
) -> None:
    """递归分块：尝试用当前分隔符切分，切不动就换下一个"""
    if len(text) <= chunk_size:
        if text.strip():
            result.append(text.strip())
        return

    sep = separators[0] if separators else ""
    remaining_seps = separators[1:] if len(separators) > 1 else []

    if not sep:
        # 没有分隔符了，硬切
        _hard_split(text, chunk_size, chunk_overlap, result)
        return

    parts = text.split(sep)
    if len(parts) <= 1:
        # 当前分隔符切不动，尝试下一个
        _recursive_split(text, chunk_size, chunk_overlap, remaining_seps, result)
        return

    # 合并小段落到 chunk_size 以内
    current = ""
    for part in parts:
        candidate = (current + sep + part) if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current.strip():
                result.append(current.strip())
            if len(part) > chunk_size:
                _recursive_split(part, chunk_size, chunk_overlap, remaining_seps, result)
                current = ""
            else:
                # 添加重叠
                if chunk_overlap > 0 and current:
                    overlap = current[-chunk_overlap:]
                    current = overlap + sep + part
                else:
                    current = part

    if current.strip():
        result.append(current.strip())


def _hard_split(
    text: str, chunk_size: int, chunk_overlap: int, result: List[str]
) -> None:
    """按字符数硬切"""
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            result.append(chunk)
        start = end - chunk_overlap if chunk_overlap > 0 else end
        if start >= end:
            break
