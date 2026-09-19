import struct
import zlib
from base64 import b64decode
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

from sqlalchemy import select
from test_studio import fake_result

from app.ai import AIProvider
from app.models import DocumentReference, Job, SiteVersion, SiteVersionReferenceInput, now
from app.worker import process_one


def docx(text: str) -> bytes:
    body = ("<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>")
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", body)
    return output.getvalue()


def png() -> bytes:
    def chunk(tag: bytes, content: bytes) -> bytes:
        return struct.pack(">I", len(content)) + tag + content + struct.pack(">I", zlib.crc32(tag + content))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) + chunk(
        b"IDAT", zlib.compress(b"\0\xff\xff\xff\xff")) + chunk(b"IEND", b"")


def jpeg() -> bytes:
    return b64decode("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/Aaf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/Aaf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Aqf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IX//2gAMAwEAAgADAAAAEP/EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EABQQAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAT8QH//Z")  # noqa: E501


def upload(world, kind: str, filename: str, content: bytes, index=0):
    response = world["client"].post(f"/api/v1/me/document-references/{kind}", headers=world["auth"](index),
                                    files={"file": (filename, content)})
    assert response.status_code == 201, response.text
    return response.json()


def test_document_reference_files_are_private_and_kind_scoped(world):
    headers = world["auth"](0)
    text = upload(world, "cv", "resume.txt", b"I built a campus application.")
    html = upload(world, "cv", "portfolio.html", b"<h1>Work</h1><script>ignore()</script><p>Real contribution</p>")
    word = upload(world, "cv", "career.docx", docx("Led the release"))
    image = upload(world, "cv", "reference.png", png())
    assert text["reference_format"] == "txt" and "text_content" not in text and "image_content" not in text
    assert html["reference_format"] == "html" and word["reference_format"] == "docx"
    assert image["reference_format"] == "png" and image["content_type"] == "image/png"
    listed = world["client"].get("/api/v1/me/document-references?kind=cv", headers=headers)
    assert listed.status_code == 200 and {item["id"] for item in listed.json()["items"]} == {text["id"], html["id"], word["id"], image["id"]}
    with world["factory"]() as db:
        assert "ignore" not in db.get(DocumentReference, html["id"]).text_content
        assert db.get(DocumentReference, word["id"]).text_content == "Led the release"
        assert db.get(DocumentReference, image["id"]).image_content == png()
    assert world["client"].get("/api/v1/me/document-references?kind=portfolio", headers=headers).json()["items"] == []
    assert world["client"].post("/api/v1/me/document-references/cv", headers=headers,
                                files={"file": ("old.doc", b"legacy")}).status_code == 422
    assert world["client"].post("/api/v1/me/document-references/cv", headers=headers,
                                files={"file": ("broken.png", b"\x89PNG\r\n\x1a\nbroken")}).status_code == 422
    assert world["client"].post("/api/v1/me/document-references/cv", headers=headers,
                                files={"file": ("wrong-extension.jpg", png())}).status_code == 422
    assert world["client"].get("/api/v1/me/document-references?kind=cv", headers=world["auth"](1)).json()["items"] == []


def test_text_reference_is_bound_to_the_queued_version_and_withdrawal_blocks_it(world, monkeypatch):
    reference = upload(world, "portfolio", "notes.txt", b"I owned the API integration and wrote tests.")
    captured = []

    def generate(_self, _prompt, inputs, _schema, **_kwargs):
        captured.append(inputs["reference_materials"])
        return fake_result()

    monkeypatch.setattr(AIProvider, "generate", generate)
    created = world["client"].post("/api/v1/me/sites/portfolio/versions", headers=world["auth"](0),
                                   json={"style_id": "linear", "consent": True, "revision": 0,
                                         "reference_ids": [reference["id"]]})
    assert created.status_code == 202, created.text
    with world["factory"]() as db:
        assert db.scalar(select(SiteVersionReferenceInput).where(SiteVersionReferenceInput.version_id == created.json()["id"]))
        assert "API integration" not in db.get(SiteVersion, created.json()["id"]).public_input_snapshot
    assert process_one(world["factory"])
    assert captured == [[{"name": "notes.txt", "format": "txt", "text": "I owned the API integration and wrote tests."}]]

    retry = world["client"].post("/api/v1/me/sites/portfolio/versions", headers=world["auth"](0),
                                  json={"style_id": "linear", "consent": True, "revision": 1,
                                        "reference_ids": [reference["id"]]})
    assert retry.status_code == 202, retry.text
    assert world["client"].delete(f"/api/v1/me/document-references/{reference['id']}", headers=world["auth"](0)).status_code == 204
    assert process_one(world["factory"])
    with world["factory"]() as db:
        assert db.get(SiteVersion, retry.json()["id"]).status == "failed"


def test_reference_ownership_plan_and_image_transport_are_enforced(world):
    image = upload(world, "profile_pr", "visual.jpg", jpeg())
    body = {"style_id": "linear", "consent": True, "revision": 0, "reference_ids": [image["id"]]}
    assert world["client"].post("/api/v1/me/sites/profile_pr/versions", headers=world["auth"](0), json=body).status_code == 422
    assert world["client"].post("/api/v1/me/sites/profile_pr/versions", headers=world["auth"](1),
                                json={**body, "revision": 0}).status_code == 409
    assert world["client"].put("/api/v1/me/subscription", headers=world["auth"](0), json={"plan": "free"}).status_code == 200
    assert world["client"].get("/api/v1/me/document-references?kind=profile_pr", headers=world["auth"](0)).status_code == 200
    assert world["client"].delete(f"/api/v1/me/document-references/{image['id']}", headers=world["auth"](0)).status_code == 204
    assert world["client"].post("/api/v1/me/document-references/cv", headers=world["auth"](0),
                                files={"file": ("resume.txt", b"Reference")}).status_code == 403


def test_reference_cannot_be_deleted_after_its_generation_starts(world):
    reference = upload(world, "portfolio", "notes.txt", b"A real implementation note.")
    created = world["client"].post("/api/v1/me/sites/portfolio/versions", headers=world["auth"](0),
                                   json={"style_id": "linear", "consent": True, "revision": 0,
                                         "reference_ids": [reference["id"]]})
    assert created.status_code == 202, created.text
    with world["factory"].begin() as db:
        job = db.scalar(select(Job).where(Job.target_id == created.json()["id"]))
        job.status, job.lease_until = "running", now() + timedelta(minutes=2)
    blocked = world["client"].delete(f"/api/v1/me/document-references/{reference['id']}", headers=world["auth"](0))
    assert blocked.status_code == 409
    with world["factory"]() as db:
        assert db.get(DocumentReference, reference["id"]).text_content
    with world["factory"].begin() as db:
        job = db.scalar(select(Job).where(Job.target_id == created.json()["id"]))
        job.status, job.lease_until = "queued", None
    assert world["client"].delete(f"/api/v1/me/document-references/{reference['id']}", headers=world["auth"](0)).status_code == 204


def test_reference_upload_body_is_rejected_before_multipart_parsing(world):
    # The file is deliberately above the multipart body cap, not merely the
    # parsed 10MB file cap. The app middleware rejects it before UploadFile.
    oversized = b"x" * (10 * 1024 * 1024 + 128 * 1024)
    response = world["client"].post("/api/v1/me/document-references/cv", headers=world["auth"](0),
                                    files={"file": ("oversized.txt", oversized)})
    assert response.status_code == 413


def test_reference_storage_count_is_bounded(world, monkeypatch):
    monkeypatch.setattr("app.document_references.MAX_STORED_REFERENCE_COUNT", 1)
    upload(world, "cv", "first.txt", b"First reference")
    response = world["client"].post("/api/v1/me/document-references/cv", headers=world["auth"](0),
                                    files={"file": ("second.txt", b"Second reference")})
    assert response.status_code == 409
