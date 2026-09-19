"""Durable plan selection and server-side AI document entitlements.

There is deliberately no payment-provider state in this MVP: a signed-in
member selects a plan themselves. The entitlement still lives at the API
boundary (and is checked again by queued workers), never only in the UI.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException

from .auth import Actor, Input
from .common import DB, lock_user
from .models import User

router = APIRouter(prefix="/api/v1", tags=["subscriptions"])

Plan = Literal["free", "premium"]
PAID_PLANS = frozenset(("premium",))


def can_generate_ai_documents(user: User) -> bool:
    """Return whether a user may start or finish paid AI document work."""
    return user.subscription_plan in PAID_PLANS


def require_ai_document_plan(user: Actor) -> User:
    if not can_generate_ai_documents(user):
        raise HTTPException(403, "AI document generation requires a PREMIUM plan.")
    return user


AIPlanUser = Annotated[User, Depends(require_ai_document_plan)]


def subscription_data(user: User) -> dict[str, str]:
    return {"plan": user.subscription_plan}


@router.get("/me/subscription")
def subscription(db: DB, user: Actor):
    return subscription_data(user)


class SubscriptionChange(Input):
    plan: Plan


@router.put("/me/subscription")
def change_subscription(body: SubscriptionChange, db: DB, user: Actor):
    # Lock the account row so concurrent browser tabs cannot interleave a
    # selection with a queued-job entitlement check.
    user = lock_user(db, user.id)
    user.subscription_plan = body.plan
    db.flush()
    return subscription_data(user)
