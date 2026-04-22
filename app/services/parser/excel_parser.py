"""Excel (XLSX/XLS) 文档解析器"""

import io
from typing import Any, Dict

from openpyxl import load_workbook

from app.services.parser.base import BaseParser


class ExcelParser(BaseParser):
    """使用 openpyxl 提取 Excel 文本"""

    def parse(self, data: bytes, filename: str) -> Dict[str, Any]:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheets_text = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                line = " | ".join(cells).strip()
                if line.replace("|", "").strip():
                    rows.append(line)
            if rows:
                sheets_text.append(f"## {sheet_name}\n\n" + "\n".join(rows))

        wb.close()

        return {
            "text": "\n\n".join(sheets_text),
            "pages": len(wb.sheetnames),
            "metadata": {"sheets": wb.sheetnames},
        }
