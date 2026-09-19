"""Private, per-document reference files used as explicit generation memory."""
import io
import re
import zlib
from typing import Literal
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, UploadFile
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from .auth import Actor
from .common import DB, data, lock_user, owner, required
from .materials import extract_pdf
from .models import DocumentReference, Job, SiteVersionReferenceInput, now
from .subscriptions import AIPlanUser, can_generate_ai_documents

router = APIRouter(prefix="/api/v1", tags=["document references"])

DocumentKind = Literal["portfolio", "profile_pr", "cv", "cover_letter"]
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
# Multipart framing is included in the pre-parser request cap in main.py.
MAX_REFERENCE_REQUEST_BYTES = MAX_REFERENCE_BYTES + 128 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_REFERENCE_TEXT_CHARS = 60_000
MAX_REFERENCE_TOTAL_CHARS = 120_000
MAX_REFERENCE_COUNT = 5
MAX_STORED_REFERENCE_COUNT = 40
MAX_STORED_REFERENCE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_SIDE = 12_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DOCX_TEXT_TAG = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
DOCX_PARAGRAPH_TAG = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"


def display_name(value: str | None) -> str:
    name = (value or "참고 자료").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return name[:200] or "참고 자료"


def image_dimensions(width: int, height: int) -> None:
    if not width or not height or max(width, height) > MAX_IMAGE_SIDE or width * height > MAX_IMAGE_PIXELS:
        raise ValueError("IMAGE")


def png_dimensions(raw: bytes) -> None:
    if not raw.startswith(PNG_SIGNATURE):
        raise ValueError("IMAGE")
    position, dimensions, has_data = len(PNG_SIGNATURE), None, False
    while position < len(raw):
        if position + 12 > len(raw):
            raise ValueError("IMAGE")
        size = int.from_bytes(raw[position:position + 4], "big")
        tag = raw[position + 4:position + 8]
        end = position + 12 + size
        if end > len(raw):
            raise ValueError("IMAGE")
        content, checksum = raw[position + 8:position + 8 + size], raw[position + 8 + size:end]
        if zlib.crc32(tag + content).to_bytes(4, "big") != checksum:
            raise ValueError("IMAGE")
        if dimensions is None:
            if tag != b"IHDR" or size != 13:
                raise ValueError("IMAGE")
            image_dimensions(int.from_bytes(content[:4], "big"), int.from_bytes(content[4:8], "big"))
            bit_depth, color_type, compression, filter_method, interlace = content[8:]
            allowed_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if bit_depth not in allowed_depths.get(color_type, set()) or compression or filter_method or interlace not in {0, 1}:
                raise ValueError("IMAGE")
            dimensions = True
        elif tag == b"IDAT":
            has_data = has_data or bool(content)
        elif tag == b"IEND":
            if size or not has_data or end != len(raw):
                raise ValueError("IMAGE")
            return
        position = end
    raise ValueError("IMAGE")


def jpeg_dimensions(raw: bytes) -> None:
    if not raw.startswith(b"\xff\xd8") or not raw.endswith(b"\xff\xd9"):
        raise ValueError("IMAGE")
    position, dimensions = 2, False
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while position < len(raw) - 2:
        if raw[position] != 0xFF:
            raise ValueError("IMAGE")
        while position < len(raw) and raw[position] == 0xFF:
            position += 1
        if position >= len(raw):
            raise ValueError("IMAGE")
        marker, position = raw[position], position + 1
        if marker == 0xDA:  # Scan payload may contain byte-stuffed marker values.
            if not dimensions or position + 2 > len(raw):
                raise ValueError("IMAGE")
            size = int.from_bytes(raw[position:position + 2], "big")
            if size < 6 or position + size >= len(raw) - 2:
                raise ValueError("IMAGE")
            return
        if marker in {0xD8, 0xD9, 0x01, *range(0xD0, 0xD8)}:
            continue
        if position + 2 > len(raw):
            raise ValueError("IMAGE")
        size = int.from_bytes(raw[position:position + 2], "big")
        if size < 2 or position + size > len(raw):
            raise ValueError("IMAGE")
        if marker in sof_markers:
            if size < 8:
                raise ValueError("IMAGE")
            image_dimensions(int.from_bytes(raw[position + 5:position + 7], "big"),
                             int.from_bytes(raw[position + 3:position + 5], "big"))
            dimensions = True
        position += size
    raise ValueError("IMAGE")


def image_format(raw: bytes) -> tuple[str, str] | None:
    try:
        if raw.startswith(PNG_SIGNATURE):
            png_dimensions(raw)
            return "png", "image/png"
        if raw.startswith(b"\xff\xd8"):
            jpeg_dimensions(raw)
            return "jpg", "image/jpeg"
    except ValueError:
        return None
    return None


def decode_utf8(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("UTF-8") from None


def extract_html(raw: bytes) -> str:
    source = decode_utf8(raw)
    soup = BeautifulSoup(source, "html.parser")
    for node in soup(["script", "style", "noscript", "template", "iframe", "object", "embed"]):
        node.decompose()
    return "\n".join(soup.stripped_strings)


def extract_docx(raw: bytes) -> str:
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(entry.file_size for entry in entries) > 20 * 1024 * 1024:
                raise ValueError("archive")
            info = archive.getinfo("word/document.xml")
            if info.file_size > 5 * 1024 * 1024:
                raise ValueError("document")
            document = archive.read(info)
    except (BadZipFile, KeyError, OSError, ValueError):
        raise ValueError("DOCX") from None
    if b"<!DOCTYPE" in document or b"<!ENTITY" in document:
        raise ValueError("DOCX")
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError:
        raise ValueError("DOCX") from None
    paragraphs = []
    for paragraph in root.iter(DOCX_PARAGRAPH_TAG):
        text = "".join(node.text or "" for node in paragraph.iter(DOCX_TEXT_TAG))
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def parse_reference(raw: bytes, name: str) -> tuple[str, str, str | None, bytes | None]:
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix in {"png", "jpg", "jpeg"}:
        detected = image_format(raw)
        expected_format = "png" if suffix == "png" else "jpg"
        if not detected or detected[0] != expected_format or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("IMAGE")
        kind, content_type = detected
        return kind, content_type, None, raw
    if suffix == "pdf":
        text, reference_format, content_type = extract_pdf(raw), "pdf", "application/pdf"
    elif suffix in {"txt", "md"}:
        text, reference_format, content_type = decode_utf8(raw), "txt", "text/plain; charset=utf-8"
    elif suffix in {"html", "htm"}:
        text, reference_format, content_type = extract_html(raw), "html", "text/html; charset=utf-8"
    elif suffix == "docx":
        text, reference_format, content_type = extract_docx(raw), "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise ValueError("FORMAT")
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text or len(text) > MAX_REFERENCE_TEXT_CHARS:
        raise ValueError("TEXT")
    return reference_format, content_type, text, None


def reference_data(row: DocumentReference) -> dict:
    return data(row, exclude=("user_id", "text_content", "image_content"))


def selected_references(db, user_id: str, site_kind: str, reference_ids: list[str]) -> list[DocumentReference]:
    if len(reference_ids) > MAX_REFERENCE_COUNT or len(set(reference_ids)) != len(reference_ids):
        raise HTTPException(422, "참고 자료는 서로 다른 파일 최대 5개를 선택해 주세요.")
    if not reference_ids:
        return []
    rows = list(db.scalars(select(DocumentReference).where(DocumentReference.user_id == user_id,
        DocumentReference.site_kind == site_kind, DocumentReference.id.in_(reference_ids))))
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(reference_ids) or any(row.access_status != "available" for row in rows):
        raise HTTPException(409, "사용 가능한 현재 문서의 참고 자료를 다시 선택해 주세요.")
    selected = [by_id[identifier] for identifier in reference_ids]
    if sum(len(row.text_content or "") for row in selected) > MAX_REFERENCE_TOTAL_CHARS:
        raise HTTPException(422, "선택한 참고 자료의 텍스트는 합계 120,000자까지 사용할 수 있어요.")
    return selected


def version_reference_inputs(db, version_id: str, user_id: str, site_kind: str) -> tuple[list[dict], list[dict]]:
    """Return only still-authorized, immutable inputs for a queued job."""
    links = list(db.scalars(select(SiteVersionReferenceInput).where(SiteVersionReferenceInput.version_id == version_id)))
    rows = []
    for link in links:
        row = db.get(DocumentReference, link.reference_id)
        if (not row or row.user_id != user_id or row.site_kind != site_kind or row.access_status != "available"
                or row.revision != link.reference_revision):
            raise HTTPException(409, "참고 자료가 삭제되었거나 변경되어 생성을 계속할 수 없어요.")
        rows.append(row)
    if sum(len(row.text_content or "") for row in rows) > MAX_REFERENCE_TOTAL_CHARS:
        raise HTTPException(409, "참고 자료의 텍스트가 변경되어 생성을 계속할 수 없어요.")
    text_inputs = [{"name": row.display_name, "format": row.reference_format, "text": row.text_content}
                   for row in rows if row.text_content]
    images = [{"name": row.display_name, "content_type": row.content_type, "content": row.image_content}
              for row in rows if row.image_content]
    return text_inputs, images


@router.get("/me/document-references")
def references(kind: DocumentKind, db: DB, user: Actor):
    rows = db.scalars(select(DocumentReference).where(DocumentReference.user_id == user.id,
        DocumentReference.site_kind == kind, DocumentReference.access_status == "available").order_by(DocumentReference.created_at.desc()))
    return {"items": [reference_data(row) for row in rows]}


@router.post("/me/document-references/{kind}", status_code=201)
async def upload_reference(kind: DocumentKind, file: UploadFile, db: DB, user: AIPlanUser):
    raw = await file.read(MAX_REFERENCE_BYTES + 1)
    await file.close()
    if len(raw) > MAX_REFERENCE_BYTES:
        raise HTTPException(413, "참고 파일은 파일당 10MB까지 지원해요.")
    name = display_name(file.filename)
    try:
        reference_format, content_type, text_content, image_content = await run_in_threadpool(parse_reference, raw, name)
    except ValueError as error:
        messages = {
            "IMAGE": "PNG 또는 JPG 이미지 파일은 5MB 이하의 정상 이미지여야 해요.",
            "TEXT": "텍스트를 읽을 수 없어요. 텍스트 PDF·DOCX·UTF-8 TXT/HTML 파일을 선택해 주세요.",
            "DOCX": "정상적인 DOCX 파일을 선택해 주세요. 예전 DOC 형식은 DOCX로 저장한 뒤 올려 주세요.",
            "UTF-8": "TXT와 HTML은 UTF-8 인코딩 파일만 지원해요.",
            "FORMAT": "PDF, PNG, JPG, TXT, DOCX, HTML 파일을 지원해요.",
        }
        raise HTTPException(422, messages.get(str(error), "참고 파일을 읽을 수 없어요.")) from None
    user = lock_user(db, user.id)
    if not can_generate_ai_documents(user):
        raise HTTPException(403, "AI document generation requires a PREMIUM plan.")
    count, used_bytes = db.execute(select(func.count(DocumentReference.id),
        func.coalesce(func.sum(DocumentReference.byte_size), 0)).where(
            DocumentReference.user_id == user.id, DocumentReference.access_status == "available")).one()
    if count >= MAX_STORED_REFERENCE_COUNT:
        raise HTTPException(409, "저장 가능한 참고 파일은 최대 40개예요. 사용하지 않는 파일을 삭제한 뒤 다시 시도해 주세요.")
    if used_bytes + len(raw) > MAX_STORED_REFERENCE_BYTES:
        raise HTTPException(413, "저장한 참고 파일은 합계 50MB까지 보관할 수 있어요. 사용하지 않는 파일을 삭제한 뒤 다시 시도해 주세요.")
    row = DocumentReference(user_id=user.id, site_kind=kind, display_name=name, reference_format=reference_format,
                            content_type=content_type, text_content=text_content, image_content=image_content,
                            byte_size=len(raw))
    db.add(row)
    db.flush()
    return reference_data(row)


@router.delete("/me/document-references/{reference_id}", status_code=204)
def withdraw_reference(reference_id: str, db: DB, user: Actor):
    lock_user(db, user.id)
    row = owner(required(db, DocumentReference, reference_id), user)
    running_job = db.scalar(select(Job.id).join(SiteVersionReferenceInput,
        SiteVersionReferenceInput.version_id == Job.target_id).where(
            SiteVersionReferenceInput.reference_id == row.id, Job.kind == "site", Job.status == "running",
            Job.lease_until.is_not(None), Job.lease_until >= now()).limit(1))
    if running_job:
        raise HTTPException(409, "이미 참고 자료 전송을 시작한 생성 작업이 있어요. 작업이 끝난 뒤 삭제해 주세요.")
    row.access_status, row.text_content, row.image_content, row.revision = "withdrawn", None, None, row.revision + 1
