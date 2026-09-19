from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select, update

from .auth import Actor, Input
from .common import (
    DB,
    Page,
    data,
    idempotent_lookup,
    lock_user,
    notify,
    remember,
    required,
    update_revision,
    utc,
)
from .models import (
    Attendance,
    Booking,
    BookingChange,
    CoffeeRequest,
    CoffeeSlot,
    Dispute,
    Notification,
    Preference,
    TrustEvent,
    User,
    now,
)

router = APIRouter(prefix="/api/v1")


class SlotInput(Input):
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def times(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("시간대가 포함된 일시를 입력해 주세요.")
        self.starts_at, self.ends_at = utc(self.starts_at), utc(self.ends_at)
        if self.ends_at <= self.starts_at:
            raise ValueError("종료 시각은 시작 시각 이후여야 합니다.")
        return self


class CoffeeInput(Input):
    recipient_id: str
    purpose: str = Field(min_length=1, max_length=200)
    introduction: str = Field(default="", max_length=3000)
    questions: str = Field(min_length=1, max_length=5000)
    proposed_slots: list[SlotInput] = Field(min_length=1, max_length=10)


class Decision(Input):
    decision: Literal["accepted", "rejected"]
    revision: int = Field(ge=1)


class BookingInput(Input):
    slot_id: str
    meeting_mode: Literal["online", "offline"]
    meeting_location: str = Field(min_length=1, max_length=1000)


def chat_data(db, row):
    booking = db.scalar(select(Booking).where(Booking.request_id == row.id))
    return data(row) | {"proposed_slots": [data(x) for x in db.scalars(select(CoffeeSlot).where(
        CoffeeSlot.request_id == row.id))], "booking_id": booking.id if booking else None}


def participant(db, row, user):
    chat = required(db, CoffeeRequest, row.request_id) if isinstance(row, Booking) else row
    if user.id not in (chat.requester_id, chat.recipient_id):
        raise HTTPException(403, "예약 당사자만 확인할 수 있습니다.")
    return chat


def lock_booking(db, booking_id, user):
    row = required(db, Booking, booking_id)
    chat = participant(db, row, user)
    # Stable lock order also serializes concurrent bookings involving either participant.
    for user_id in sorted([chat.requester_id, chat.recipient_id]):
        lock_user(db, user_id)
    db.refresh(row)
    return row, chat


def other_person(chat, user_id):
    return chat.recipient_id if chat.requester_id == user_id else chat.requester_id


def check_overlap(db, chat, starts_at, ends_at, except_booking=None):
    users = [chat.requester_id, chat.recipient_id]
    query = select(Booking).join(CoffeeRequest).where(Booking.status == "confirmed",
        (CoffeeRequest.requester_id.in_(users)) | (CoffeeRequest.recipient_id.in_(users)),
        Booking.starts_at < ends_at, Booking.ends_at > starts_at)
    if except_booking:
        query = query.where(Booking.id != except_booking)
    if db.scalar(query):
        raise HTTPException(409, "참여자의 다른 예약과 시간이 겹칩니다.")


@router.post("/coffee-chats", status_code=201)
def create_chat(body: CoffeeInput, db: DB, user: Actor,
                idempotency_key: Annotated[str | None, Header()] = None):
    lock_user(db, user.id)
    existing, request_hash = idempotent_lookup(db, user.id, "coffee-create", idempotency_key, body.model_dump())
    if existing:
        return existing.response_body
    recipient = required(db, User, body.recipient_id)
    if recipient.id == user.id:
        raise HTTPException(422, "본인에게 커피챗을 요청할 수 없습니다.")
    if recipient.account_status != "active" or not required(db, Preference, recipient.id).coffee_chat_available:
        raise HTTPException(409, "현재 커피챗 요청을 받지 않는 사용자입니다.")
    if any(slot.starts_at <= now() for slot in body.proposed_slots):
        raise HTTPException(422, "희망 일정은 미래 시각이어야 합니다.")
    row = CoffeeRequest(requester_id=user.id, **body.model_dump(exclude={"proposed_slots"}))
    db.add(row)
    db.flush()
    db.add_all([CoffeeSlot(request_id=row.id, **slot.model_dump()) for slot in body.proposed_slots])
    notify(db, recipient.id, "coffee_request", "새 커피챗 요청이 도착했어요", f"/coffee/{row.id}")
    db.flush()
    result = chat_data(db, row)
    remember(db, user.id, "coffee-create", idempotency_key, request_hash, result)
    return result


@router.get("/coffee-chats")
def chats(db: DB, user: Actor, page: Page, box: Literal["sent", "received"] = "received"):
    condition = CoffeeRequest.requester_id == user.id if box == "sent" else CoffeeRequest.recipient_id == user.id
    return page.page(db, select(CoffeeRequest).where(condition), CoffeeRequest, lambda x: chat_data(db, x))


@router.get("/coffee-chats/{chat_id}")
def chat_detail(chat_id: str, db: DB, user: Actor):
    row = required(db, CoffeeRequest, chat_id)
    participant(db, row, user)
    return chat_data(db, row)


@router.post("/coffee-chats/{chat_id}/decision")
def decide_chat(chat_id: str, body: Decision, db: DB, user: Actor):
    row = required(db, CoffeeRequest, chat_id)
    if row.recipient_id != user.id:
        raise HTTPException(403, "요청을 받은 사람만 결정할 수 있습니다.")
    if row.status != "pending":
        raise HTTPException(409, "이미 결정된 요청입니다.")
    update_revision(db, row, body.revision, {"status": body.decision, "decided_at": now()})
    notify(db, row.requester_id, "coffee_decision", "커피챗 요청에 답변이 도착했어요", f"/coffee/{row.id}")
    return chat_data(db, row)


@router.post("/coffee-chats/{chat_id}/booking", status_code=201)
def book_chat(chat_id: str, body: BookingInput, db: DB, user: Actor,
              idempotency_key: Annotated[str | None, Header()] = None):
    chat = required(db, CoffeeRequest, chat_id)
    if chat.recipient_id != user.id:
        raise HTTPException(403, "요청 수신자만 희망 슬롯을 확정할 수 있습니다.")
    for user_id in sorted([chat.requester_id, chat.recipient_id]):
        lock_user(db, user_id)
    db.refresh(chat)
    operation = f"booking:{chat_id}"
    existing, request_hash = idempotent_lookup(db, user.id, operation, idempotency_key, body.model_dump())
    if existing:
        return existing.response_body
    if chat.status != "accepted" or db.scalar(select(Booking).where(Booking.request_id == chat.id)):
        raise HTTPException(409, "수락한 요청에 예약을 한 번만 확정할 수 있습니다.")
    slot = required(db, CoffeeSlot, body.slot_id)
    if slot.request_id != chat.id:
        raise HTTPException(422, "이 요청의 희망 시간 후보가 아닙니다.")
    if utc(slot.starts_at) <= now():
        raise HTTPException(409, "지난 일정으로 예약할 수 없습니다.")
    check_overlap(db, chat, slot.starts_at, slot.ends_at)
    row = Booking(request_id=chat.id, starts_at=slot.starts_at, ends_at=slot.ends_at,
                  **body.model_dump(exclude={"slot_id"}))
    db.add(row)
    db.flush()
    notify(db, chat.requester_id, "booking_confirmed", "커피챗 일정이 확정되었어요", f"/bookings/{row.id}")
    result = data(row)
    remember(db, user.id, operation, idempotency_key, request_hash, result)
    return result


@router.get("/me/bookings")
def bookings(db: DB, user: Actor, page: Page):
    return page.page(db, select(Booking).join(CoffeeRequest).where(
        (CoffeeRequest.requester_id == user.id) | (CoffeeRequest.recipient_id == user.id)), Booking)


@router.get("/bookings/{booking_id}")
def booking_detail(booking_id: str, db: DB, user: Actor):
    row = required(db, Booking, booking_id)
    chat = participant(db, row, user)
    return data(row) | {"requester_id": chat.requester_id, "recipient_id": chat.recipient_id,
                        "changes": [data(x) for x in db.scalars(select(BookingChange).where(
                            BookingChange.booking_id == row.id))]}


class ChangeInput(Input):
    change_kind: Literal["reschedule", "cancel"]
    revision: int = Field(ge=1)
    slot: SlotInput | None = None
    meeting_mode: Literal["online", "offline"] | None = None
    meeting_location: str | None = Field(default=None, min_length=1, max_length=1000)


@router.post("/bookings/{booking_id}/changes", status_code=201)
def propose_change(booking_id: str, body: ChangeInput, db: DB, user: Actor):
    row, chat = lock_booking(db, booking_id, user)
    if row.status != "confirmed" or row.revision != body.revision:
        raise HTTPException(409, "현재 예약 상태를 다시 확인해 주세요.")
    if utc(row.starts_at) <= now():
        raise HTTPException(409, "이미 시작된 예약은 변경할 수 없습니다. 참석 확인 또는 분쟁을 이용해 주세요.")
    if body.change_kind == "reschedule" and (not body.slot or body.slot.starts_at <= now()):
        raise HTTPException(422, "변경할 미래 일정을 입력해 주세요.")
    pending = db.scalar(select(BookingChange).where(BookingChange.booking_id == row.id,
                                                   BookingChange.status == "pending"))
    if pending:
        raise HTTPException(409, "이전 변경 요청의 응답을 기다리고 있습니다.")
    change = BookingChange(booking_id=row.id, proposer_id=user.id, change_kind=body.change_kind,
                           base_revision=row.revision, proposed_value=body.model_dump(
                               mode="json", exclude={"revision", "change_kind"}, exclude_none=True))
    db.add(change)
    db.flush()
    notify(db, other_person(chat, user.id), "booking_change", "예약 변경 요청을 확인해 주세요", f"/bookings/{row.id}")
    return data(change)


class ChangeDecision(Input):
    decision: Literal["accepted", "rejected"]


@router.post("/bookings/{booking_id}/changes/{change_id}/decision")
def decide_change(booking_id: str, change_id: str, body: ChangeDecision, db: DB, user: Actor):
    booking, chat = lock_booking(db, booking_id, user)
    change = required(db, BookingChange, change_id)
    if change.booking_id != booking.id or change.proposer_id == user.id:
        raise HTTPException(403, "상대방의 변경 요청만 결정할 수 있습니다.")
    if change.status != "pending" or booking.status != "confirmed":
        raise HTTPException(409, "이미 처리된 변경 요청입니다.")
    if body.decision == "accepted":
        if utc(booking.starts_at) <= now():
            raise HTTPException(409, "이미 시작된 예약은 변경할 수 없습니다.")
        changes = {"status": "cancelled"}
        if change.change_kind == "reschedule":
            slot = SlotInput.model_validate(change.proposed_value["slot"])
            if slot.starts_at <= now():
                raise HTTPException(409, "변경 일정이 이미 지났습니다.")
            check_overlap(db, chat, slot.starts_at, slot.ends_at, booking.id)
            changes = slot.model_dump() | {key: value for key, value in change.proposed_value.items() if key != "slot"}
        update_revision(db, booking, change.base_revision, changes)
    change.status, change.decided_at = body.decision, now()
    notify(db, change.proposer_id, "booking_change_decision", "예약 변경에 답변이 도착했어요", f"/bookings/{booking.id}")
    return data(change)


class ClaimInput(Input):
    attendance_claim: Literal["attended", "absent"]


@router.put("/bookings/{booking_id}/attendance-claim")
def claim_attendance(booking_id: str, body: ClaimInput, db: DB, user: Actor):
    booking, chat = lock_booking(db, booking_id, user)
    if booking.status not in ("confirmed", "completed") or utc(booking.ends_at) > now():
        raise HTTPException(409, "약속 종료 후 참석 여부를 확인할 수 있습니다.")
    record = db.scalar(select(Attendance).where(Attendance.booking_id == booking.id, Attendance.user_id == user.id))
    if record and record.attendance_claim:
        if record.attendance_claim != body.attendance_claim:
            raise HTTPException(409, "제출한 참석 기록은 분쟁 검토로 정정할 수 있습니다.")
        return data(record)
    if not record:
        record = Attendance(booking_id=booking.id, user_id=user.id)
        db.add(record)
    record.attendance_claim, record.claimed_at = body.attendance_claim, now()
    # Never synthesize or backdate checked_in_at from a later attendance claim.
    db.flush()
    records = list(db.scalars(select(Attendance).where(Attendance.booking_id == booking.id)))
    open_dispute = db.scalar(select(Dispute).where(Dispute.booking_id == booking.id, Dispute.status == "open"))
    if len(records) == 2 and not open_dispute:
        if all(x.attendance_claim == "attended" for x in records):
            booking.status = "completed"
            booking.revision += 1
            for x in records:
                db.add(TrustEvent(user_id=x.user_id, booking_id=booking.id, event_kind="mutual_completion",
                                  evidence={"source": "mutual_attendance_claim", "claimed_at": data(x)["claimed_at"]}))
        elif len({x.attendance_claim for x in records}) > 1:
            db.add(Dispute(booking_id=booking.id, reporter_id=user.id, reason="참여자의 참석 주장이 서로 다릅니다."))
    return data(record)


@router.get("/bookings/{booking_id}/attendance")
def attendance(booking_id: str, db: DB, user: Actor):
    participant(db, required(db, Booking, booking_id), user)
    return {"items": [data(x) for x in db.scalars(select(Attendance).where(Attendance.booking_id == booking_id))],
            "next_cursor": None}


@router.post("/bookings/{booking_id}/check-ins")
def checkin(booking_id: str, db: DB, user: Actor):
    participant(db, required(db, Booking, booking_id), user)
    raise HTTPException(503, "GPS·QR 체크인 운영 방식이 아직 확정되지 않았습니다. 사후 참석 확인을 이용할 수 있습니다.")


class DisputeInput(Input):
    reason: str = Field(min_length=1, max_length=5000)


@router.post("/bookings/{booking_id}/disputes", status_code=201)
def report_dispute(booking_id: str, body: DisputeInput, db: DB, user: Actor):
    booking, chat = lock_booking(db, booking_id, user)
    existing = db.scalar(select(Dispute).where(Dispute.booking_id == booking.id, Dispute.status == "open"))
    if existing:
        raise HTTPException(409, "이 예약은 이미 분쟁 검토 중입니다.")
    row = Dispute(booking_id=booking.id, reporter_id=user.id, reason=body.reason)
    db.add(row)
    db.flush()
    notify(db, other_person(chat, user.id), "dispute", "예약에 분쟁 검토가 요청되었어요", f"/bookings/{booking.id}")
    return data(row)


@router.get("/bookings/{booking_id}/disputes")
def disputes(booking_id: str, db: DB, user: Actor):
    participant(db, required(db, Booking, booking_id), user)
    return {"items": [data(x) for x in db.scalars(select(Dispute).where(Dispute.booking_id == booking_id))],
            "next_cursor": None}


@router.get("/bookings/{booking_id}/deposits")
def deposits(booking_id: str, db: DB, user: Actor):
    participant(db, required(db, Booking, booking_id), user)
    return {"items": [], "next_cursor": None, "policy_status": "not_configured",
            "message": "보증금 금액·납부·환불 정책 확정 전에는 결제 의무를 생성하지 않습니다."}


@router.get("/me/trust-events")
def trust_events(db: DB, user: Actor, page: Page):
    return page.page(db, select(TrustEvent).where(TrustEvent.user_id == user.id), TrustEvent)


@router.get("/me/trust")
def trust(db: DB, user: Actor):
    return {"grade": None, "policy_status": "not_configured",
            "meaning": "약속 이행 기록입니다. 기술 실력을 나타내지 않습니다.",
            "events_count": len(list(db.scalars(select(TrustEvent.id).where(TrustEvent.user_id == user.id))))}


@router.get("/me/notifications")
def notifications(db: DB, user: Actor, page: Page):
    return page.page(db, select(Notification).where(Notification.user_id == user.id), Notification)


@router.patch("/me/notifications/{notification_id}")
def read_notification(notification_id: str, db: DB, user: Actor):
    row = required(db, Notification, notification_id)
    if row.user_id != user.id:
        raise HTTPException(403, "본인 알림만 변경할 수 있습니다.")
    db.execute(update(Notification).where(Notification.id == row.id).values(read_at=now()))
    db.refresh(row)
    return data(row)
