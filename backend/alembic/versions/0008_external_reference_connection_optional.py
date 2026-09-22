"""Allow URL-based meeting references without a stored platform connection.

Revision ID: 0008_external_reference_connection_optional
Revises: 0007_phase_4_20_26_schema_alignment
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0008_external_reference_connection_optional"
down_revision: Union[str, None] = "0007_phase_4_20_26_schema_alignment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("external_meeting_references", "connection_id", nullable=True)


def downgrade() -> None:
    op.alter_column("external_meeting_references", "connection_id", nullable=False)
