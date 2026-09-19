"""Link verified Supabase subjects without changing existing application owners."""
import sqlalchemy as sa
from alembic import op

revision = "d43067a98f21"
down_revision = "c28170e1b9ad"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("supabase_user_id", sa.String(36), nullable=True))
    op.create_index("uq_users_supabase_user_id", "users", ["supabase_user_id"], unique=True)
    op.add_column("auth_sessions", sa.Column("auth_provider", sa.String(), nullable=False, server_default="local"))


def downgrade():
    op.drop_column("auth_sessions", "auth_provider")
    op.drop_index("uq_users_supabase_user_id", table_name="users")
    op.drop_column("users", "supabase_user_id")
