"""Protect backend-only tables on Supabase and repair the PostgreSQL site FK."""
from alembic import op

revision = "c28170e1b9ad"
down_revision = "a427080b2017"
branch_labels = None
depends_on = None

# Frozen table list: never change another application's tables or schema grants.
TABLES = (
    "tags", "universities", "users", "analysis_runs", "auth_challenges", "auth_sessions",
    "career_events", "coffee_requests", "external_accounts", "idempotency_records", "jobs",
    "notifications", "personal_sites", "profiles", "projects", "school_affiliations",
    "university_domains", "user_preferences", "user_tags", "ai_suggestions", "coffee_bookings",
    "coffee_proposed_slots", "email_verifications", "project_members", "recruitment_posts",
    "site_versions", "source_materials", "analysis_inputs", "attendance_records", "booking_changes",
    "disputes", "project_sources", "role_openings", "site_publications", "trust_events",
    "project_requests", "career_plans", "user_ai_settings", "alembic_version",
)


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.create_foreign_key("fk_personal_sites_published_version", "personal_sites", "site_versions",
                          ["published_version_id"], ["id"])
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE public."{table}" FROM PUBLIC')
        for role in ("anon", "authenticated", "service_role"):
            op.execute(f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    REVOKE ALL ON TABLE public."{table}" FROM {role};
                END IF;
            END $$""")


def downgrade():
    if op.get_context().dialect.name == "postgresql":
        op.drop_constraint("fk_personal_sites_published_version", "personal_sites", type_="foreignkey")
    # Do not restore unknown former grants or expose private data on downgrade.
