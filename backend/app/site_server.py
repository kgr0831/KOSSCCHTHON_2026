import html

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from .common import DB
from .models import PersonalSite, Publication, SiteVersion, User
from .site_render import html_document

app = FastAPI(title="두드리 공개 프로필", docs_url=None, redoc_url=None, openapi_url=None)
router = APIRouter()


@app.get("/")
def health():
    return {"status": "ok", "service": "dudri-sites"}


@app.get("/api/v1/health")
def database_health(db: DB):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "service": "dudri-sites", "database": "ok"}


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exception):
    return JSONResponse(status_code=503, content={"detail": "게시된 문서를 불러올 수 없어요. 잠시 후 다시 시도해 주세요."})


@router.get("/s/{slug}")
def serve(slug: str, db: DB):
    site = db.scalar(select(PersonalSite).where(PersonalSite.slug == slug))
    if not site or not site.published_version_id:
        raise HTTPException(404, "게시된 프로필이 없습니다.")
    user, version = db.get(User, site.user_id), db.get(SiteVersion, site.published_version_id)
    active = db.scalar(select(Publication.id).where(Publication.site_id == site.id,
                       Publication.version_id == site.published_version_id, Publication.revoked_at.is_(None)))
    if not active or not user or user.account_status != "active" or not version or version.status != "preview_ready" or version.facts_revision != user.facts_revision:
        raise HTTPException(404, "게시된 프로필이 없습니다.")
    inner = html.escape(html_document(version.code), quote=True)
    wrapper = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
               '<title>두드리 공개 프로필</title><style>html,body{margin:0;height:100%}iframe{display:block;border:0;width:100%;height:100%}</style></head>'
               f'<body><iframe title="공개 프로필" sandbox="allow-scripts" referrerpolicy="no-referrer" srcdoc="{inner}"></iframe></body></html>')
    return HTMLResponse(wrapper, headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-src 'self'; base-uri 'none'; form-action 'none'",
                        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})


app.include_router(router)
