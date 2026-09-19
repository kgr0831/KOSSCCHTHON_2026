"""Store private document-reference memory inputs.

Revision ID: e4b9e6a2c8d1
Revises: d3a41e9bf725
"""
import sqlalchemy as sa
from alembic import op


revision = "e4b9e6a2c8d1"
down_revision = "d3a41e9bf725"
branch_labels = None
depends_on = None


PRIVATE_TABLES = ("document_references", "site_version_reference_inputs")


def upgrade():
    op.create_table(
        "document_references",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("site_kind", sa.String(length=30), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("reference_format", sa.String(length=20), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("image_content", sa.LargeBinary(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("access_status", sa.String(length=20), nullable=False, server_default="available"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_references_user_id", "document_references", ["user_id"])
    op.create_index("ix_document_references_site_kind", "document_references", ["site_kind"])
    op.create_table(
        "site_version_reference_inputs",
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("reference_id", sa.String(length=36), nullable=False),
        sa.Column("reference_revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["reference_id"], ["document_references.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["site_versions.id"]),
        sa.PrimaryKeyConstraint("version_id", "reference_id"),
    )
    op.create_index("ix_site_version_reference_inputs_reference_id", "site_version_reference_inputs", ["reference_id"])
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
    op.drop_index("ix_site_version_reference_inputs_reference_id", table_name="site_version_reference_inputs")
    op.drop_table("site_version_reference_inputs")
    op.drop_index("ix_document_references_site_kind", table_name="document_references")
    op.drop_index("ix_document_references_user_id", table_name="document_references")
    op.drop_table("document_references")
