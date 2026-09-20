import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.models import AuthSession, PersonalSite, ProfileAvatar, Tag
from app.profiles import MAX_AVATAR_REQUEST_BYTES


def test_school_domain_and_single_use_auth(world):
    c = world["client"]
    signup = {"name": "새 사용자", "email": "new@wrong.example", "university_id": world["university"],
              "enrollment_status": "graduate"}
    assert c.post("/api/v1/auth/school-email-verifications", json=signup).status_code == 422
    assert not world["mailer"].deliveries
    signup["email"] = "new@university.example"
    assert c.post("/api/v1/auth/school-email-verifications", json=signup).status_code == 202
    token = world["mailer"].deliveries[-1][2]
    answer = c.post("/api/v1/auth/school-email-verifications/confirm", json={"token": token})
    assert answer.status_code == 200
    headers = {"Authorization": "Bearer " + answer.json()["access_token"]}
    profile = c.get("/api/v1/me", headers=headers).json()
    assert profile["school_affiliations"][0]["enrollment_status"] == "graduate"
    assert profile["school_affiliations"][0]["status_source"] == "user_input"
    assert c.post("/api/v1/auth/school-email-verifications/confirm", json={"token": token}).status_code == 401
    with world["factory"]() as db:
        sessions = list(db.scalars(select(AuthSession)))
        assert all(token not in row.refresh_hash and token not in row.access_hash for row in sessions)


def test_refresh_origin_rotation_reuse_and_logout(world):
    c = world["client"]
    c.post("/api/v1/auth/login-links", json={"email": "person0@university.example"})
    token = world["mailer"].deliveries[-1][2]
    response = c.post("/api/v1/auth/login-links/confirm", json={"token": token})
    old_cookie = c.cookies.get("dudri_refresh")
    assert "HttpOnly" in response.headers["set-cookie"]
    assert c.post("/api/v1/auth/refresh").status_code == 403
    headers = {"Origin": "http://localhost:3000"}
    renewed = c.post("/api/v1/auth/refresh", headers=headers)
    assert renewed.status_code == 200
    access = {"Authorization": "Bearer " + renewed.json()["access_token"]}
    assert c.get("/api/v1/me", headers=access).status_code == 200
    c.cookies.clear()
    c.cookies.set("dudri_refresh", old_cookie, path="/api/v1/auth")
    assert c.post("/api/v1/auth/refresh", headers=headers).status_code == 401
    assert c.get("/api/v1/me", headers=access).status_code == 401


def test_private_fields_and_revision_conflict(world):
    c, a, b = world["client"], world["auth"](0), world["auth"](1)
    private = {"revision": 1, "display_name": "비밀 이름", "bio": "비공개 프로젝트 Orion",
               "name_is_public": False, "bio_is_public": False}
    assert c.patch("/api/v1/me", headers=a, json=private).status_code == 200
    public = c.get(f"/api/v1/users/{world['users'][0]}", headers=b).json()
    assert "Orion" not in str(public) and "비밀 이름" not in str(public)
    assert "login_email" not in public
    assert c.get("/api/v1/me", headers=a).json()["profile"]["bio"] == private["bio"]
    assert c.patch("/api/v1/me", headers=a, json=private).status_code == 409


def test_recommendations_batch_public_profiles_without_leaking_private_fields(world):
    c, owner, viewer = world["client"], world["auth"](0), world["auth"](1)
    private = {"revision": 1, "display_name": "비공개 이름", "bio": "비공개 소개",
               "name_is_public": False, "bio_is_public": False}
    assert c.patch("/api/v1/me", headers=owner, json=private).status_code == 200

    response = c.get("/api/v1/recommendations", headers=viewer)
    assert response.status_code == 200
    profile = next(item for item in response.json()["items"] if item["id"] == world["users"][0])
    assert profile["display_name"] == "동문"
    assert "bio" not in profile


def test_concurrent_profile_edits_one_wins(world):
    c, headers = world["client"], world["auth"](0)
    def edit(name):
        return c.patch("/api/v1/me", headers=headers, json={"revision": 1, "display_name": name}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(edit, ["모바일", "PC"])) == [200, 409]


def test_profile_avatar_upload_is_durable_and_respects_visibility(world):
    c, owner, other = world["client"], world["auth"](0), world["auth"](1)
    png = b"\x89PNG\r\n\x1a\n" + b"profile-image"
    uploaded = c.post("/api/v1/me/avatar", headers=owner,
                      files={"file": ("avatar.png", png, "image/png")})
    assert uploaded.status_code == 200
    profile = uploaded.json()
    image_path = profile["avatar_url"]
    assert image_path.startswith(f"/api/v1/users/{world['users'][0]}/avatar?v=")
    assert c.get(image_path).content == png
    assert c.get(image_path, headers=other).headers["content-type"] == "image/png"
    with world["factory"]() as db:
        assert db.get(ProfileAvatar, world["users"][0]).content == png

    hidden = c.patch("/api/v1/me", headers=owner,
                     json={"revision": profile["revision"], "avatar_is_public": False})
    assert hidden.status_code == 200
    assert c.get(image_path).status_code == 404
    assert c.get(image_path, headers=other).status_code == 404
    assert c.get(image_path, headers=owner).content == png


def test_profile_avatar_rejects_non_image_uploads(world):
    response = world["client"].post("/api/v1/me/avatar", headers=world["auth"](0),
                                     files={"file": ("avatar.svg", b"<svg></svg>", "image/svg+xml")})
    assert response.status_code == 422


def test_avatar_request_limit_rejects_large_and_chunked_bodies_before_parsing(world):
    response = world["client"].post(
        "/api/v1/me/avatar",
        headers=world["auth"](0),
        files={"file": ("too-large.png", b"x" * MAX_AVATAR_REQUEST_BYTES, "image/png")},
    )
    assert response.status_code == 413
    with world["factory"]() as db:
        assert db.get(ProfileAvatar, world["users"][0]) is None

    from app.main import UploadBodySizeMiddleware

    completed, sent = [], []

    async def downstream(scope, receive, send):
        while (await receive())["more_body"]:
            pass
        completed.append(True)

    messages = iter([
        {"type": "http.request", "body": b"a" * 8, "more_body": True},
        {"type": "http.request", "body": b"b" * 8, "more_body": False},
    ])

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    asyncio.run(UploadBodySizeMiddleware(downstream, limits={"/api/v1/me/avatar": (12, "too large")})(
        {"type": "http", "method": "POST", "path": "/api/v1/me/avatar", "headers": []}, receive, send))
    assert not completed
    assert sent[0]["status"] == 413


def test_career_owner_and_public_graph(world):
    c, a, b = world["client"], world["auth"](0), world["auth"](1)
    body = {"event_kind": "employment", "title": "비공개 회사 경력", "is_public": False,
            "started_on": "2022-01-01"}
    row = c.post("/api/v1/me/career-events", headers=a, json=body).json()
    assert c.patch(f"/api/v1/me/career-events/{row['id']}", headers=b, json=body | {"revision": 1}).status_code == 403
    path = f"/api/v1/users/{world['users'][0]}/career-path-graph"
    assert not c.get(path, headers=b).json()["nodes"]
    assert c.patch(f"/api/v1/me/career-events/{row['id']}", headers=a,
                   json=body | {"revision": 1, "is_public": True}).status_code == 200
    assert len(c.get(path, headers=b).json()["nodes"]) == 1
    assert not c.get(path, headers=b).json()["edges"]
    assert c.delete(f"/api/v1/me/career-events/{row['id']}?revision=2", headers=a).status_code == 204
    assert not c.get(path, headers=b).json()["nodes"]


def test_tags_are_not_public_by_default(world):
    c, a, b = world["client"], world["auth"](0), world["auth"](1)
    with world["factory"].begin() as db:
        tag = Tag(kind="skill", name="SecretSkill")
        db.add(tag)
        db.flush()
        tag_id = tag.id
    result = c.put("/api/v1/me/tags", headers=a, json={"revision": 1,
        "items": [{"tag_id": tag_id, "usage": "experienced"}]})
    assert result.status_code == 200
    assert "SecretSkill" not in str(c.get(f"/api/v1/users/{world['users'][0]}", headers=b).json())


def test_fact_change_increments_site_revision(world):
    with world["factory"].begin() as db:
        site = PersonalSite(user_id=world["users"][0], site_kind="profile_pr", slug="sample")
        db.add(site)
        db.flush()
        site_id = site.id
    world["client"].patch("/api/v1/me", headers=world["auth"](0), json={"revision": 1, "bio_is_public": False})
    with world["factory"]() as db:
        assert db.get(PersonalSite, site_id).revision == 2


def test_normal_user_cannot_manage_universities(world):
    result = world["client"].post("/api/v1/admin/universities", headers=world["auth"](0), json={"name": "새 학교"})
    assert result.status_code == 403
