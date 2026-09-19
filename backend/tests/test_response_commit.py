from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Material


def test_write_is_committed_before_success_response_starts(world):
    observed = []
    app = world["client"].app

    async def capture(scope, receive, send):
        async def inspect(message):
            if message["type"] == "http.response.start" and message["status"] == 201:
                with world["factory"]() as db:
                    observed.append(db.scalar(select(Material.id).where(Material.display_name == "committed-before-response")) is not None)
            await send(message)
        await app(scope, receive, inspect)

    response = TestClient(capture).post("/api/v1/me/source-materials", headers=world["auth"](0),
                                       json={"display_name": "committed-before-response", "text": "Fixture"})
    assert response.status_code == 201
    assert observed == [True]
