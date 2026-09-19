import os

from fastapi import APIRouter, HTTPException, Request

from .config import get_settings

router = APIRouter(prefix="/api/v1/dev", tags=["local runtime"])


@router.get("/instance")
def instance(request: Request):
    if get_settings().environment != "development":
        raise HTTPException(404, "로컬 실행 정보가 없습니다.")
    if not request.client or request.client.host not in ("127.0.0.1", "::1", "testclient"):
        raise HTTPException(403, "이 PC에서만 사용할 수 있습니다.")
    return {"service": "dudri-local", "instance": os.environ.get("DUDRI_LOCAL_INSTANCE", ""),
            "supervisor": os.environ.get("DUDRI_LOCAL_SUPERVISOR", "")}
