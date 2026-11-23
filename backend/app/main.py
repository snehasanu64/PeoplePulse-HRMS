from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import public_router, router
from backend.app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(public_router)

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")
