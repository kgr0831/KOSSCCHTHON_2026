"""Pair deployment accounts with a local CLI connector."""
import sqlalchemy as sa
from alembic import op


revision = "a8f4c0d8e112"
down_revision = ("f219d57ce193", "e4b9e6a2c8d1")
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_ai_settings", sa.Column("cli_device_id", sa.String(length=64), nullable=False, server_default=""))
    op.create_table(
        "ai_cli_connectors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("device_name", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pairing_hash", sa.String(length=64), nullable=True),
        sa.Column("pairing_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        sa.UniqueConstraint("pairing_hash"),
    )
    op.create_index("ix_ai_cli_connectors_user_id", "ai_cli_connectors", ["user_id"])
    op.create_index("ix_ai_cli_connectors_device_id", "ai_cli_connectors", ["device_id"])
    op.create_index("ix_ai_cli_connectors_status", "ai_cli_connectors", ["status"])
    if op.get_context().dialect.name == "postgresql":
        op.execute('ALTER TABLE public."ai_cli_connectors" ENABLE ROW LEVEL SECURITY')
        op.execute('REVOKE ALL ON TABLE public."ai_cli_connectors" FROM PUBLIC')
        for role in ("anon", "authenticated", "service_role"):
            op.execute(f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    REVOKE ALL ON TABLE public."ai_cli_connectors" FROM {role};
                END IF;
            END $$""")


def downgrade():
    op.drop_index("ix_ai_cli_connectors_status", table_name="ai_cli_connectors")
    op.drop_index("ix_ai_cli_connectors_device_id", table_name="ai_cli_connectors")
    op.drop_index("ix_ai_cli_connectors_user_id", table_name="ai_cli_connectors")
    op.drop_table("ai_cli_connectors")
    op.drop_column("user_ai_settings", "cli_device_id")
