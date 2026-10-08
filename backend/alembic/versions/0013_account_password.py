"""Opt-in password sign-in for existing authorized accounts. No credential backfill."""
from alembic import op
import sqlalchemy as sa

revision = "0013_account_password"
down_revision = "0012_nullable_query_confidence"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("login_tenant_id", sa.String(255), nullable=True))


def downgrade():
    raise RuntimeError("Review enrolled credentials before removing account authentication columns.")
