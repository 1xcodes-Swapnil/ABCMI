"""Preserve unknown confidence from REAL translation providers."""
from alembic import op
import sqlalchemy as sa
revision = "0014_translation_confidence"
down_revision = "0013_account_password"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("derived_translations", "confidence", existing_type=sa.Float(), nullable=True, server_default=None)


def downgrade():
    raise RuntimeError("Unknown translation confidence cannot be replaced by a fabricated score.")
