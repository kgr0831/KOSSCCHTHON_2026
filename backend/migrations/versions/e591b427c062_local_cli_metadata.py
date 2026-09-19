"""Store only CLI metadata and keep PC jobs on their originating PC."""
import sqlalchemy as sa
from alembic import op

revision = "e591b427c062"
down_revision = "d43067a98f21"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_ai_settings", sa.Column("cli_provider", sa.String(), nullable=False, server_default="codex"))
    op.add_column("user_ai_settings", sa.Column("cli_model", sa.String(), nullable=False, server_default=""))
    op.add_column("user_ai_settings", sa.Column("cli_connections", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("jobs", sa.Column("execution_target", sa.String(), nullable=False, server_default="server"))
    op.create_index("ix_jobs_execution_target", "jobs", ["execution_target"])


def downgrade():
    op.drop_index("ix_jobs_execution_target", table_name="jobs")
    op.drop_column("jobs", "execution_target")
    for column in ("cli_connections", "cli_model", "cli_provider"):
        op.drop_column("user_ai_settings", column)
