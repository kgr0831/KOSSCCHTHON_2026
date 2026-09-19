import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from . import (
    ai_routes,
    auth,
    career,
    coffee,
    design_upload,
    dev,
    materials,
    profiles,
    projects,
    search,
    sites,
    supabase_auth,
)
from .common import DB


def create_app():
    application = FastAPI(title="두드리 API", version="0.1.0")
    for module in (auth, supabase_auth, profiles, coffee, projects, search, dev, ai_routes, sites, materials, career, design_upload):
        application.include_router(module.router)

    @application.get("/")
    def health():
        return {"service": "dudri", "status": "ok"}

    @application.get("/api/v1/health")
    def database_health(db: DB):
        db.execute(text("SELECT 1"))
        return {"service": "dudri", "status": "ok", "database": "ok"}

    @application.middleware("http")
    async def private_response(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Request-ID"] = str(uuid4())
        return response

    @application.exception_handler(IntegrityError)
    async def conflict(request, exception):
        return JSONResponse(status_code=409, content={"detail": "중복되거나 변경된 요청입니다. 최신 상태를 확인해 주세요."})

    @application.exception_handler(SQLAlchemyError)
    async def database_unavailable(request, exception):
        return JSONResponse(status_code=503, content={"code": "DATABASE_UNAVAILABLE",
                            "detail": "서버가 데이터베이스에 연결하지 못했어요. 실행 터미널에서 DB 설정과 연결 상태를 확인해 주세요."})

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exception):
        # Default validation output includes raw input; auth tokens and CV content must not be echoed.
        errors = [{"loc": x["loc"], "msg": x["msg"], "type": x["type"]} for x in exception.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    return application


class SafeAccessFilter(logging.Filter):
    def filter(self, record):
        # Uvicorn's request-line argument includes URL query credentials on legacy GET confirms.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            args[2] = str(args[2]).split("?", 1)[0]
            record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(SafeAccessFilter())
app = create_app()
