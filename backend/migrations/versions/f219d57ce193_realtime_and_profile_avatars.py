"""Store profile images durably and support authenticated realtime invalidations."""
import sqlalchemy as sa
from alembic import op


revision = "f219d57ce193"
down_revision = "e591b427c062"
branch_labels = None
depends_on = None


PRIVATE_TABLES = ("profile_avatars", "realtime_tickets", "realtime_events")


def upgrade():
    op.create_table(
        "profile_avatars",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "realtime_tickets",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_realtime_tickets_user_id", "realtime_tickets", ["user_id"])
    op.create_index("ix_realtime_tickets_session_id", "realtime_tickets", ["session_id"])
    op.create_index("ix_realtime_tickets_user_created", "realtime_tickets", ["user_id", "created_at"])
    op.create_index("ix_realtime_tickets_expires_at", "realtime_tickets", ["expires_at"])
    op.create_table(
        "realtime_events",
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_realtime_events_target_user_id", "realtime_events", ["target_user_id"])
    op.create_index("ix_realtime_events_target_created", "realtime_events", ["target_user_id", "created_at"])
    op.create_index("ix_realtime_events_created_at", "realtime_events", ["created_at"])
    # This migration runs after the initial Supabase RLS migration.  Secure
    # these later backend-only tables here as well, rather than weakening the
    # original migration's frozen table list.
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
    op.drop_index("ix_realtime_events_created_at", table_name="realtime_events")
    op.drop_index("ix_realtime_events_target_created", table_name="realtime_events")
    op.drop_index("ix_realtime_events_target_user_id", table_name="realtime_events")
    op.drop_table("realtime_events")
    op.drop_index("ix_realtime_tickets_expires_at", table_name="realtime_tickets")
    op.drop_index("ix_realtime_tickets_user_created", table_name="realtime_tickets")
    op.drop_index("ix_realtime_tickets_session_id", table_name="realtime_tickets")
    op.drop_index("ix_realtime_tickets_user_id", table_name="realtime_tickets")
    op.drop_table("realtime_tickets")
    op.drop_table("profile_avatars")
