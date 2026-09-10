"""Add source_module column and index to knowledge_objects

Revision ID: 0003_add_source_module_to_knowledge_objects
Revises: 0002_knowledge_object_hardening
Create Date: 2026-08-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003_add_source_module_to_knowledge_objects'
down_revision: Union[str, None] = '0002_knowledge_object_hardening'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('knowledge_objects') as batch_op:
        batch_op.add_column(sa.Column('source_module', sa.String(length=100), nullable=True))
        batch_op.create_index('ix_knowledge_objects_source_module', ['source_module'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('knowledge_objects') as batch_op:
        batch_op.drop_index('ix_knowledge_objects_source_module')
        batch_op.drop_column('source_module')
