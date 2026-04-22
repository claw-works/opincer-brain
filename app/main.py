"""opincer-brain — Opincer 平台 AI/NLP 能力服务"""

from fastapi import FastAPI
from app.api import parse, chunk

app = FastAPI(
    title="opincer-brain",
    description="Opincer 平台的 AI/NLP 能力服务",
    version="0.1.0",
)

app.include_router(parse.router, prefix="/parse", tags=["parse"])
app.include_router(chunk.router, prefix="/chunk", tags=["chunk"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "opincer-brain"}
