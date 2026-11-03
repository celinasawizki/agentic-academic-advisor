import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import SessionLocal
from app.routers import advisor, catalog, integration, plans, students
from app.seed import init_db, seed

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Temple Academic Planning AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
for r in (catalog.router, students.router, plans.router, integration.router, advisor.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "llm_enabled": settings.llm_enabled, "data_mode": "demo_fixture"}
