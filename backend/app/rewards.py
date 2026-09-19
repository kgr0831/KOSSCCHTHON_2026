"""Persisted points and monthly opportunity limits.

Points are awarded after a mutually completed coffee chat but intentionally
have no spending feature yet. Opportunities are shared across the three
actions that create a new connection: coffee request, recruitment publishing,
and a participation application.
"""
from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from .auth import Actor
from .common import DB, lock_user
from .models import MonthlyOpportunity, PointTransaction, User, now

router = APIRouter(prefix="/api/v1", tags=["rewards"])

KOREA = ZoneInfo("Asia/Seoul")
FREE_OPPORTUNITY_LIMIT: Final = 5
PREMIUM_OPPORTUNITY_LIMIT: Final = 20
COFFEE_COMPLETION_POINTS: Final = 1
MENTOR_BONUS_OPPORTUNITIES: Final = 1


def period_key(at: datetime | None = None) -> str:
    return (at or now()).astimezone(KOREA).strftime("%Y-%m")


def reset_at(period: str) -> str:
    year, month = (int(value) for value in period.split("-", 1))
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    return datetime(year, month, 1, tzinfo=KOREA).isoformat()


def opportunity_limit(user: User) -> int:
    return PREMIUM_OPPORTUNITY_LIMIT if user.subscription_plan == "premium" else FREE_OPPORTUNITY_LIMIT


def monthly_balance(db, user: User, period: str | None = None) -> MonthlyOpportunity:
    period = period or period_key()
    row = db.scalar(select(MonthlyOpportunity).where(MonthlyOpportunity.user_id == user.id,
                                                      MonthlyOpportunity.period_key == period))
    if row:
        return row
    row = MonthlyOpportunity(user_id=user.id, period_key=period)
    db.add(row)
    db.flush()
    return row


def opportunity_data(db, user: User) -> dict[str, int | str]:
    row = monthly_balance(db, user)
    limit = opportunity_limit(user)
    return {
        "period": row.period_key,
        "limit": limit,
        "bonus": row.bonus_count,
        "used": row.used_count,
        "remaining": max(0, limit + row.bonus_count - row.used_count),
        "resets_at": reset_at(row.period_key),
    }


def consume_opportunity(db, user: User):
    """Spend one shared opportunity after the caller's validation succeeds."""
    user = lock_user(db, user.id)
    row = monthly_balance(db, user)
    if row.used_count >= opportunity_limit(user) + row.bonus_count:
        raise HTTPException(429, "This month's connection opportunities have been used. They reset next month.")
    row.used_count += 1
    db.flush()


def grant_coffee_completion_rewards(db, booking, requester_id: str, recipient_id: str):
    """Award both attendees once and grant the request recipient one bonus use."""
    if booking.completion_rewarded_at:
        return
    for user_id in (requester_id, recipient_id):
        db.add(PointTransaction(user_id=user_id, booking_id=booking.id, amount=COFFEE_COMPLETION_POINTS,
                                reason="coffee_completion"))
    recipient = lock_user(db, recipient_id)
    monthly_balance(db, recipient).bonus_count += MENTOR_BONUS_OPPORTUNITIES
    booking.completion_rewarded_at = now()
    db.flush()


def reward_data(db, user: User) -> dict:
    points = db.scalar(select(func.coalesce(func.sum(PointTransaction.amount), 0)).where(
        PointTransaction.user_id == user.id))
    return {"points": int(points or 0), "opportunities": opportunity_data(db, user)}


@router.get("/me/rewards")
def rewards(db: DB, user: Actor):
    # A user-row lock serializes a first request in a new month with a
    # simultaneous action that spends an opportunity.
    user = lock_user(db, user.id)
    return reward_data(db, user)
