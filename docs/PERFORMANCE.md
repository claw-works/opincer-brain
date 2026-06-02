# 文档解析性能参考

> 基于 2 核云主机（阿里云 ECS / ACK Pod）的预估数据。
> 解析库：pypdf 5.x / python-docx 1.x / openpyxl 3.x / python-pptx 1.x

## 文件大小限制

当前配置：**50 MB**（下载 + 上传均适用）

- URL 下载：流式读取，先检查 `Content-Length` header 快速拒绝，再边读边计数
- 文件上传：读完后检查 `len(data) > MAX_FILE_SIZE`

## PDF（pypdf，纯 Python）

pypdf 是纯 Python 实现，无 C 依赖，解析速度取决于页面复杂度。

| 文件大小 | 典型页数 | 解析耗时 | 说明 |
|---|---|---|---|
| 10 MB | 100-200 页 | 2-5 秒 | 普通文本 PDF（Word/LaTeX 导出） |
| 20 MB | 200-500 页 | 5-15 秒 | 含部分图片（图片被跳过但仍需扫描结构） |
| 50 MB | 500-1000+ 页 | 15-60 秒 | 纯文本约 20-30s；扫描件/大量图片更慢 |

**影响因素**：
- 纯文本 PDF：最快，约 50-100 页/秒
- 扫描件 PDF：pypdf 只提取文本层，无 OCR 层时提取不到内容，但仍需解析 PDF 结构
- 加密/复杂排版：解密解压多花 2-3 倍时间
- 内存：50MB PDF 解压后峰值 200-400 MB

**提速方案**（如需）：换用 `pymupdf`（基于 MuPDF C 库），比 pypdf 快 5-10 倍，但需 Dockerfile 加装 C 依赖。

## DOCX（python-docx）

DOCX 是 ZIP 包装的 XML，解压后直接遍历段落和表格。

| 文件大小 | 场景 | 解析耗时 | 说明 |
|---|---|---|---|
| 10 MB | 200-500 页纯文本 | 1-3 秒 | 文本提取极快 |
| 20 MB | 嵌入图片为主 | 2-5 秒 | 图片占体积但不读内容 |
| 50 MB | 大量嵌入图片/附件 | 3-8 秒 | 解压慢，文本本身很快 |

**特点**：体积主要由嵌入媒体（图片、图表）贡献，实际文本量不大，所以大文件也很快。

## XLSX（openpyxl）

Excel 是所有格式里最容易慢的——需要逐行遍历所有单元格。

| 文件大小 | 场景 | 解析耗时 | 说明 |
|---|---|---|---|
| 10 MB | 10-50 个 sheet，几十万行 | 3-8 秒 | `read_only=True` 但仍需迭代 |
| 20 MB | 大表（百万行级） | 8-20 秒 | 内存峰值 200MB+ |
| 50 MB | 超大表 | 20-60 秒 | 最接近 timeout 的格式 |

**影响因素**：
- 行数 >> 列数时最慢（逐行迭代）
- `read_only=True` 已启用（节省内存），但不能跳过空行
- 每个 cell 都转 str 拼接

**提速方案**（如需）：
- 加行数上限（如只读前 10 万行）
- 换用 `python-calamine`（Rust 实现的 xlsx reader），比 openpyxl 快约 10 倍

## PPTX（python-pptx）

PPTX 和 DOCX 类似，ZIP + XML，大部分体积是嵌入的图片/视频。

| 文件大小 | 场景 | 解析耗时 | 说明 |
|---|---|---|---|
| 10 MB | 50-100 张幻灯片 | 1-3 秒 | 多数体积是图片 |
| 20 MB | 有视频/高清图嵌入 | 2-5 秒 | 只读 text_frame 和表格 |
| 50 MB | 大量高清图 | 3-8 秒 | 解压慢但文本提取快 |

**特点**：PPT 文件通常文本很少（每页几行），实际需要提取的内容量最小。

## 纯文本（TXT/MD/CSV/JSON 等）

| 文件大小 | 解析耗时 | 说明 |
|---|---|---|
| 任意大小 | < 1 秒 | 只做编码检测 + decode，极快 |

## 汇总对比

| 格式 | 10 MB | 20 MB | 50 MB | 瓶颈 |
|---|---|---|---|---|
| PDF | 2-5s | 5-15s | 15-60s | 纯 Python 页面结构解析 |
| DOCX | 1-3s | 2-5s | 3-8s | ZIP 解压 |
| XLSX | 3-8s | 8-20s | 20-60s | 逐行遍历所有单元格 |
| PPTX | 1-3s | 2-5s | 3-8s | ZIP 解压 |
| TXT | <1s | <1s | <1s | 几乎无 |

## 当前 timeout 配置

- HTTP 下载：120 秒
- uvicorn 请求：无硬限制（由调用方/nginx 控制）
- 建议 nginx 端配 `proxy_read_timeout 180s` 给大文件留余量

## OCR Fallback（PaddleOCR）

当 pypdf 提取的文本 < 50 字符时，自动 fallback 到 PaddleOCR 处理扫描件。

**触发条件**：`len(text.strip()) < 50`（即 pypdf 基本没提取到东西）

**流程**：PDF → pdf2image 逐页渲染为 JPEG（150 DPI）→ PaddleOCR 逐页识别 → 拼接

**性能**（CPU 模式，2 核）：

| 页数 | OCR 耗时 | 说明 |
|---|---|---|
| 5 页 | 3-10 秒 | 快 |
| 20 页 | 10-40 秒 | 可接受 |
| 50 页 | 25-100 秒 | 接近 timeout |
| 100+ 页 | 可能超时 | 建议 GPU 或限制页数 |

**依赖**：
- `paddleocr` + `paddlepaddle`（CPU 版，约 800MB 安装体积）
- `pdf2image`（需要系统 `poppler-utils`）
- `libgl1` + `libglib2.0-0`（OpenCV 的系统依赖）

**镜像体积影响**：从约 200MB → 约 1.2GB（主要是 PaddlePaddle 和 OCR 模型）

**API 响应变化**：返回的 `metadata.parse_method` 字段标识使用了哪种方式：
- `"pypdf"` — 正常文本提取
- `"ocr"` — 走了 OCR fallback

## 建议

1. 绝大多数用户上传的文档在 1-20MB，体验良好（< 10 秒）
2. 50MB 的 PDF/Excel 是极端场景，可能接近 60 秒，但在 timeout 内
3. 如果后续出现超时投诉，优先排查是 PDF 还是 Excel，针对性换库
