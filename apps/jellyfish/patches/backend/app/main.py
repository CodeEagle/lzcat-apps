"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import router as api_v1_router
from app.config import settings
from app.core.db import init_db
from app.core.storage import init_storage
from app.dependencies import get_db
from app.models.llm import Provider, ProviderStatus
from app.models.studio import Chapter, FileItem, Shot, ShotDetail, ShotDialogLine, TimelineClip
from app.schemas.common import ApiResponse


def _error_message(detail: object) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict) and "msg" in item:
                loc = item.get("loc", ())
                loc_str = ".".join(str(x) for x in loc if x != "body")
                parts.append(f"{loc_str}: {item['msg']}" if loc_str else item["msg"])
            else:
                parts.append(str(item))
        return "; ".join(parts) if parts else "Validation error"
    return str(detail)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        code = exc.status_code
        message = _error_message(exc.detail)
    else:
        code = 500
        message = "Internal server error"
    body = ApiResponse[None](code=code, message=message, data=None).model_dump()
    return JSONResponse(status_code=code, content=body)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    message = _error_message(exc.errors())
    body = ApiResponse[None](code=422, message=message, data=None).model_dump()
    return JSONResponse(status_code=422, content=body)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    init_storage()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, http_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


legacy_router = APIRouter(prefix="/api", tags=["legacy"])


def _ts(value: object) -> str:
    text = str(value or "")
    return text.replace(" ", "T")


@legacy_router.get("/files")
async def legacy_list_files(db: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    rows = (await db.execute(select(FileItem).order_by(FileItem.updated_at.desc()))).scalars().all()
    return [
        {
            "id": row.id,
            "type": row.type,
            "name": row.name,
            "thumbnail": row.thumbnail,
            "tags": row.tags or [],
            "createdAt": _ts(getattr(row, "created_at", "")),
            "projectId": "",
            "chapterId": None,
        }
        for row in rows
    ]


@legacy_router.get("/chapters/{chapter_id}/shots")
async def legacy_list_shots(chapter_id: str, db: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    rows = (
        await db.execute(select(Shot).where(Shot.chapter_id == chapter_id).order_by(Shot.index.asc()))
    ).scalars().all()
    return [
        {
            "id": row.id,
            "chapterId": row.chapter_id,
            "index": row.index,
            "title": row.title,
            "duration": 0,
            "thumbnail": row.thumbnail,
            "status": row.status,
            "scriptExcerpt": row.script_excerpt,
        }
        for row in rows
    ]


@legacy_router.get("/shots/{shot_id}")
async def legacy_get_shot(shot_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    detail = await db.get(ShotDetail, shot_id)
    lines = (
        await db.execute(
            select(ShotDialogLine).where(ShotDialogLine.shot_detail_id == shot_id).order_by(ShotDialogLine.index.asc())
        )
    ).scalars().all()
    return {
        "id": shot.id,
        "cameraShot": getattr(detail, "camera_shot", "MS"),
        "angle": getattr(detail, "angle", "EYE_LEVEL"),
        "movement": getattr(detail, "movement", "STATIC"),
        "sceneAssetId": getattr(detail, "scene_id", None),
        "duration": 0,
        "moodTags": list(getattr(detail, "mood_tags", []) or []),
        "atmosphere": getattr(detail, "atmosphere", ""),
        "followAtmosphere": bool(getattr(detail, "follow_atmosphere", False)),
        "dialog": [
            {"role": str(getattr(line, "speaker_character_id", "") or ""), "text": line.text}
            for line in lines
        ],
        "hasBgm": bool(getattr(detail, "has_bgm", False)),
    }


@legacy_router.get("/projects/{project_id}/timeline")
async def legacy_get_timeline(project_id: str, db: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    chapter_ids = (
        await db.execute(select(Chapter.id).where(Chapter.project_id == project_id))
    ).scalars().all()
    shot_ids = []
    if chapter_ids:
        shot_ids = (
            await db.execute(select(Shot.id).where(Shot.chapter_id.in_(chapter_ids)))
        ).scalars().all()
    rows = (await db.execute(select(TimelineClip).order_by(TimelineClip.track.asc(), TimelineClip.start.asc()))).scalars().all()
    if shot_ids:
        rows = [row for row in rows if row.source_id in shot_ids]
    return [
        {
            "id": row.id,
            "type": row.type,
            "sourceId": row.source_id,
            "label": row.label,
            "start": row.start,
            "end": row.end,
            "track": row.track,
        }
        for row in rows
    ]


def _provider_to_legacy_agent(provider: Provider) -> dict[str, object]:
    return {
        "id": provider.id,
        "name": provider.name,
        "type": "other",
        "description": provider.description,
        "isDefault": provider.status == ProviderStatus.active,
        "version": "v1",
        "updatedAt": _ts(getattr(provider, "updated_at", "")),
        "createdAt": _ts(getattr(provider, "created_at", "")),
        "createdBy": provider.created_by or "",
        "updatedBy": provider.created_by or "",
    }


@legacy_router.get("/agents")
async def legacy_list_agents(db: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    rows = (await db.execute(select(Provider).order_by(Provider.updated_at.desc()))).scalars().all()
    return [_provider_to_legacy_agent(row) for row in rows]


@legacy_router.get("/agents/{agent_id}")
async def legacy_get_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    provider = await db.get(Provider, agent_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _provider_to_legacy_agent(provider)


app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
app.include_router(legacy_router)
app.mount("/local-files", StaticFiles(directory=Path(settings.local_storage_dir), check_dir=False), name="local-files")


@app.get("/health")
async def health():
    from app.schemas.common import success_response

    return success_response({"status": "ok"})
