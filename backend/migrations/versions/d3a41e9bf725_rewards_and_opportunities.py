"""Persist coffee-chat points and monthly shared opportunities.

Revision ID: d3a41e9bf725
Revises: c58bf0d0a741
"""
import sqlalchemy as sa
from alembic import op


revision = "d3a41e9bf725"
down_revision = "c58bf0d0a741"
branch_labels = None
depends_on = None

PRIVATE_TABLES = ("monthly_opportunities", "point_transactions")


def upgrade():
    op.add_column("coffee_bookings", sa.Column("completion_rewarded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "monthly_opportunities",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("period_key", sa.String(length=7), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bonus_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "period_key"),
    )
    op.create_index("ix_monthly_opportunities_user_id", "monthly_opportunities", ["user_id"])
    op.create_table(
        "point_transactions",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("booking_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["coffee_bookings.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", "user_id", "reason"),
    )
    op.create_index("ix_point_transactions_user_id", "point_transactions", ["user_id"])
    op.create_index("ix_point_transactions_booking_id", "point_transactions", ["booking_id"])
    if op.get_context().dialect.name == "postgresql":
        for table in PRIVATE_TABLES:
            op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON TABLE public."{table}" FROM PUBLIC')
            for role in ("anon", "authenticated", "service_role"):
                op.execute(f"""DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        REVOKE ALL ON TABLE public."{table}" FROM {role};
                    END IF;
                END $$""")


def downgrade():
    op.drop_index("ix_point_transactions_booking_id", table_name="point_transactions")
    op.drop_index("ix_point_transactions_user_id", table_name="point_transactions")
    op.drop_table("point_transactions")
    op.drop_index("ix_monthly_opportunities_user_id", table_name="monthly_opportunities")
    op.drop_table("monthly_opportunities")
    op.drop_column("coffee_bookings", "completion_rewarded_at")
