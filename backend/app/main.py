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
    document_references,
    external_accounts,
    materials,
    profiles,
    projects,
    realtime,
    rewards,
    search,
    sites,
    subscriptions,
    supabase_auth,
)
from .common import DB


class _UploadBodyTooLarge(Exception):
    pass


class UploadBodySizeMiddleware:
    """Reject selected oversized multipart bodies before Starlette spools them.

    A Content-Length check handles ordinary browser uploads immediately; the
    wrapped receive function also covers chunked requests, which otherwise
    bypass a header-only limit.
    """

    def __init__(self, app, limits: dict[str, tuple[int, str]]):
        self.app = app
        self.limits = limits

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        limit = self.limits.get(scope["path"])
        if not limit:
            await self.app(scope, receive, send)
            return
        max_bytes, message = limit
        headers = dict(scope.get("headers", ()))
        try:
            content_length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            content_length = 0
        if content_length > max_bytes:
            await JSONResponse(status_code=413, content={"detail": message})(scope, receive, send)
            return
        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    raise _UploadBodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _UploadBodyTooLarge:
            # Parsing happens before a route can begin a response, but retain
            # this guard if a future endpoint changes that ordering.
            if not response_started:
                await JSONResponse(status_code=413, content={"detail": message})(scope, receive, send)


def create_app():
    application = FastAPI(title="두드리 API", version="0.1.0")
    reference_paths = {f"/api/v1/me/document-references/{kind}": (
        document_references.MAX_REFERENCE_REQUEST_BYTES,
        "참고 파일은 파일당 10MB까지 업로드할 수 있습니다.",
    ) for kind in ("portfolio", "profile_pr", "cv", "cover_letter")}
    application.add_middleware(UploadBodySizeMiddleware, limits={
        "/api/v1/me/avatar": (profiles.MAX_AVATAR_REQUEST_BYTES, "프로필 이미지는 최대 2MB까지 업로드할 수 있습니다."),
        **reference_paths,
    })
    for module in (auth, supabase_auth, profiles, subscriptions, rewards, coffee, projects, realtime, search, dev, ai_routes, sites, materials,
                   document_references,
                   external_accounts, career, design_upload):
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
