FROM python:3.12-slim

WORKDIR /app

# Use Aliyun debian mirror for faster apt-get in China
RUN sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g; s|http://security.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null \
    || sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g; s|http://security.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list

# Install system dependencies for document parsing and OCR
# libreoffice-nogui: Office 文档(doc/docx/xls/xlsx/ppt/pptx)→PDF 转换，
#   供 Web 端在线预览（/preview 路由）。--no-install-recommends 跳过 JRE 等
#   推荐依赖，纯格式转换不需要 Java，显著控制镜像体积。
RUN apt-get update && apt-get install -y --no-install-recommends \
    antiword \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    libreoffice-nogui \
    && rm -rf /var/lib/apt/lists/*

# Use Aliyun pip mirror for faster downloads in China
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
    && pip config set global.trusted-host mirrors.aliyun.com

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
