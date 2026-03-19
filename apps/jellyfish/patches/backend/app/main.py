"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import router as api_v1_router
from app.config import settings
from app.core.db import init_db
from app.core.storage import init_storage
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

app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
app.mount("/local-files", StaticFiles(directory=Path(settings.local_storage_dir), check_dir=False), name="local-files")


@app.get("/health")
async def health():
    from app.schemas.common import success_response

    return success_response({"status": "ok"})
