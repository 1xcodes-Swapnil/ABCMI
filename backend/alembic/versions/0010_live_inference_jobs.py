"""Durable live inference jobs. Existing live tables/data are retained.

Revision ID: 0010_live_inference_jobs
Revises: 0009_add_meeting_timezone
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_live_inference_jobs"
down_revision = "0009_add_meeting_timezone"
branch_labels = None
depends_on = None


def upgrade():
    # Earlier installations created these through metadata.create_all rather
    # than Alembic. Create missing tables without replacing existing tables.
    from app.models.live_session import LiveSession, LiveAudioChunk
    from app.models.inference_job import InferenceJob
    bind = op.get_bind()
    for model in (LiveSession, LiveAudioChunk, InferenceJob):
        newly_created = not sa.inspect(bind).has_table(model.__tablename__)
        model.__table__.create(bind, checkfirst=True)
        if bind.dialect.name == "postgresql" and (newly_created or model is InferenceJob):
            op.execute(sa.text(f'ALTER TABLE "{model.__tablename__}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    op.drop_table("inference_jobs")
