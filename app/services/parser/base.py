"""解析器基类"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseParser(ABC):
    """文档解析器基类"""

    @abstractmethod
    def parse(self, data: bytes, filename: str) -> Dict[str, Any]:
        """
        解析文件内容，返回提取的文本。

        Args:
            data: 文件二进制内容
            filename: 文件名

        Returns:
            dict with keys:
                - text: str — 提取的纯文本
                - pages: int — 页数（如适用）
                - metadata: dict — 元数据（标题、作者等）
        """
        ...
