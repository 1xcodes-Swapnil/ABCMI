"""Harden KnowledgeObject constraints and indexes

Revision ID: 0002_knowledge_object_hardening
Revises: 0001_initial_schema
Create Date: 2026-08-12 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_knowledge_object_hardening'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('knowledge_objects') as batch_op:
        batch_op.create_check_constraint(
            'ck_knowledge_objects_confidence_range',
            'confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)'
        )
        batch_op.create_check_constraint(
            'ck_knowledge_objects_version_positive',
            'version >= 1'
        )
        batch_op.create_index(
            'ix_knowledge_objects_meeting_status_type',
            ['meeting_id', 'status', 'object_type'],
            unique=False
        )
        batch_op.create_index(
            'ix_knowledge_objects_qdrant_point_id',
            ['qdrant_point_id'],
            unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('knowledge_objects') as batch_op:
        batch_op.drop_index('ix_knowledge_objects_qdrant_point_id')
        batch_op.drop_index('ix_knowledge_objects_meeting_status_type')
        batch_op.drop_constraint('ck_knowledge_objects_version_positive', type_='check')
        batch_op.drop_constraint('ck_knowledge_objects_confidence_range', type_='check')
