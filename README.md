# opincer-brain

Opincer 平台的 AI/NLP 能力服务。为 Go 后端（opincer-service）提供文档解析、文本分块、向量化、语义搜索等能力。

## 技术栈

- Python 3.12+
- FastAPI + uvicorn
- pypdf / python-docx / openpyxl / python-pptx

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Docker

```bash
docker build -t opincer-brain .
docker run -p 8000:8000 opincer-brain
```

## API

### POST /parse

文档解析，提取纯文本。

请求：
```json
{
  "file_url": "https://oss.example.com/file.pdf",
  "file_name": "report.pdf"
}
```

或上传文件：`multipart/form-data`，字段 `file`

响应：
```json
{
  "text": "提取的文本内容...",
  "pages": 10,
  "metadata": {
    "title": "文档标题",
    "author": "作者"
  }
}
```

### POST /chunk

文本分块。

请求：
```json
{
  "text": "长文本内容...",
  "chunk_size": 1000,
  "chunk_overlap": 200
}
```

响应：
```json
{
  "chunks": [
    {"index": 0, "content": "第一段...", "char_count": 980},
    {"index": 1, "content": "第二段...", "char_count": 1020}
  ],
  "total_chunks": 2
}
```

### GET /health

健康检查。
