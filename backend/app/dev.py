import os

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field

from .auth import Input, check_origin, issue_session
from .common import DB
from .config import get_settings
from .models import Profile, User
from .seed import DEMO_USERS, PEOPLE

router = APIRouter(prefix="/api/v1/dev", tags=["local demo"])


def local_only(request: Request):
    settings = get_settings()
    if settings.environment != "development" or not settings.local_demo_enabled:
        raise HTTPException(404, "로컬 체험 모드가 아닙니다.")
    if not request.client or request.client.host not in ("127.0.0.1", "::1", "testclient"):
        raise HTTPException(403, "이 PC에서만 사용할 수 있습니다.")


@router.get("/accounts")
def accounts(request: Request, db: DB):
    local_only(request)
    return {"items": [{"id": user_id, "name": db.get(Profile, user_id).display_name,
                        "school": PEOPLE[i][1], "role": PEOPLE[i][3], "is_demo": True}
                       for i, user_id in enumerate(DEMO_USERS) if db.get(Profile, user_id)]}


@router.get("/instance")
def instance(request: Request):
    local_only(request)
    return {"service": "dudri-local", "instance": os.environ.get("DUDRI_LOCAL_INSTANCE", ""),
            "supervisor": os.environ.get("DUDRI_LOCAL_SUPERVISOR", "")}


class DemoLogin(Input):
    user_id: str = Field(min_length=36, max_length=36)


@router.post("/login")
def login(body: DemoLogin, request: Request, response: Response, db: DB):
    local_only(request)
    check_origin(request)
    user = db.get(User, body.user_id) if body.user_id in DEMO_USERS else None
    if not user or user.account_status != "active":
        raise HTTPException(403, "사용 가능한 데모 계정을 선택해 주세요.")
    return issue_session(db, user.id, response)
