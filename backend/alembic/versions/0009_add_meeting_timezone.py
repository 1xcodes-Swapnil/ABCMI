"""Add the meeting timezone column used by the ORM and CLI.

Revision ID: 0009_add_meeting_timezone
Revises: 0008_external_reference_connection_optional
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_add_meeting_timezone"
down_revision: Union[str, None] = "0008_external_reference_connection_optional"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("timezone", sa.String(length=50), nullable=True, server_default="UTC"),
    )


def downgrade() -> None:
    op.drop_column("meetings", "timezone")
