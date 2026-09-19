"""Store each member's selected no-payment plan.

Revision ID: c58bf0d0a741
Revises: f219d57ce193
"""
import sqlalchemy as sa
from alembic import op


revision = "c58bf0d0a741"
down_revision = "f219d57ce193"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("subscription_plan", sa.String(length=20), nullable=False, server_default="free"))


def downgrade():
    op.drop_column("users", "subscription_plan")
