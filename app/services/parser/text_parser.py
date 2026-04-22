"""纯文本文件解析器（TXT/MD/CSV/JSON 等）"""

from typing import Any, Dict

import chardet

from app.services.parser.base import BaseParser


class TextParser(BaseParser):
    """直接读取纯文本文件，自动检测编码"""

    def parse(self, data: bytes, filename: str) -> Dict[str, Any]:
        # 自动检测编码
        detected = chardet.detect(data)
        encoding = detected.get("encoding", "utf-8") or "utf-8"

        try:
            text = data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            text = data.decode("utf-8", errors="replace")

        return {
            "text": text.strip(),
            "pages": 0,
            "metadata": {"encoding": encoding},
        }
