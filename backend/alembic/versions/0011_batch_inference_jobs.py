"""Reuse the durable GPU queue for uploaded meetings, retaining all live jobs."""
from alembic import op
import sqlalchemy as sa
revision = "0011_batch_inference_jobs"
down_revision = "0010_live_inference_jobs"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("inference_jobs")}
    if "payload" not in columns:
        op.add_column("inference_jobs", sa.Column("payload", sa.JSON(), nullable=True))
    op.alter_column("inference_jobs", "session_id", existing_type=sa.Uuid(), nullable=True)

def downgrade():
    raise RuntimeError("Batch jobs may exist. Review their data before downgrading.")
