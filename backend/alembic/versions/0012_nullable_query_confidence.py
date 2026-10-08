"""Unknown answer confidence remains unknown; historical values are retained."""
from alembic import op
import sqlalchemy as sa
revision = "0012_nullable_query_confidence"
down_revision = "0011_batch_inference_jobs"
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column("query_records", "confidence", existing_type=sa.Float(), nullable=True, server_default=None)

def downgrade():
    raise RuntimeError("Review unknown confidence records before downgrading.")
