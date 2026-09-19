"""Live demo-only validation; credentials stay in process memory and never in output."""
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
with httpx.Client(base_url="http://127.0.0.1:8000/api/v1", headers={"Origin": "http://localhost:3000"}, timeout=30) as client:
    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"Local check failed: {method} {path} status={response.status_code}")
        return response.json()
    accounts = request("GET", "/dev/accounts")["items"]
    user = next(account for account in accounts if account["name"] == "김민준")
    login = request("POST", "/dev/login", json={"user_id": user["id"]})
    client.headers["Authorization"] = "Bearer " + login["access_token"]
    sites = request("GET", "/me/sites")["items"]
    pending = []
    documents = [] if "--reference-only" in sys.argv else [("portfolio", "대표 프로젝트와 내 역할, 접근 과정과 배운 점을 보여주는 웹 포트폴리오를 만들어 주세요. 작업 카드는 펼쳐 읽을 수 있게 해 주세요."), ("cv", "같은 공개 사실로 경력·학력·기술을 간결하게 정리한 A4 이력서를 만들어 주세요.")]
    for kind, instruction in documents:
        site = next((item for item in sites if item["site_kind"] == kind), None)
        version = request("POST", f"/me/sites/{kind}/versions", json={"style_id": "editorial", "instruction": instruction, "consent": True, "revision": site["revision"] if site else 0})
        pending.append((kind, version["id"]))
    request("POST", "/portfolio-styles/editorial/preview", json={"consent": True})
    print("Queued: requested demo documents and editorial reference images.", flush=True)
    deadline = time.monotonic() + 650
    while pending and time.monotonic() < deadline:
        for kind, version_id in pending[:]:
            version = request("GET", f"/me/site-versions/{version_id}")
            if version["status"] not in ("queued", "running"):
                print(f"{kind}: {version['status']}", flush=True)
                if version["status"] != "preview_ready":
                    raise RuntimeError("Generated demo did not pass validation")
                if kind == "portfolio":
                    (ROOT / ".runtime/live-generation.json").write_text(json.dumps({"version_id": version_id, "user_id": user["id"]}), encoding="utf-8")
                pending.remove((kind, version_id))
        time.sleep(5)
    if pending:
        raise RuntimeError("AI generation remained pending")
    while time.monotonic() < deadline:
        style = request("GET", "/portfolio-styles/editorial")
        if style["status"] == "ready":
            assert style["reference_image"].startswith("data:image/png;base64,")
            assert style["mobile_reference_image"].startswith("data:image/png;base64,")
            print("Reference images: saved desktop and mobile PNGs. No document was published.", flush=True)
            break
        if style["status"] == "failed":
            raise RuntimeError("Reference image generation failed")
        time.sleep(5)
    else:
        raise RuntimeError("Reference generation remained pending")
