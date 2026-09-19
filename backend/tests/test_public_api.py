from fastapi.testclient import TestClient
from sqlalchemy import select
from test_database import add_saved_portfolio

from app.db import get_db
from app.models import Publication, SiteVersion
from app.public_api import app


def test_free_host_keeps_published_code_sandboxed_and_api_authenticated(world):
    site_id, _, version_id = add_saved_portfolio(world)
    with world["factory"].begin() as db:
        version = db.get(SiteVersion, version_id)
        version.status = "preview_ready"
        version.code = {"html": "<h1>Saved portfolio</h1>", "css": "", "javascript": ""}
        db.add(Publication(site_id=site_id, version_id=version_id))
    app.dependency_overrides[get_db] = world["client"].app.dependency_overrides[get_db]
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/health").json()["database"] == "ok"
            assert client.get("/api/v1/me").status_code == 401
            published = client.get("/s/fixture")
            assert published.status_code == 200
            assert 'sandbox="allow-scripts"' in published.text
            assert "allow-same-origin" not in published.text
            assert "default-src 'none'" in published.headers["Content-Security-Policy"]
            assert "set-cookie" not in published.headers
            assert client.get("/api/v1/me/site-versions/" + version_id, headers=world["auth"](1)).status_code == 403
            result = client.post("/api/v1/me/sites/" + site_id + "/revoke", headers=world["auth"](0), json={"revision": 1})
            assert result.status_code == 200
            assert client.get("/s/fixture").status_code == 404
        with world["factory"]() as db:
            assert db.scalar(select(Publication).where(Publication.site_id == site_id)).revoked_at is not None
    finally:
        app.dependency_overrides.clear()
