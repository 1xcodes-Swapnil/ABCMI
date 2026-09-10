"""Add notifications table for real-time user events and system notifications

Revision ID: 0004_notifications_schema
Revises: 0003_add_source_module_to_knowledge_objects
Create Date: 2026-08-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004_notifications_schema'
down_revision: Union[str, None] = '0003_add_source_module_to_knowledge_objects'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, default=False),
        sa.Column('meeting_id', sa.Uuid(), nullable=True),
        sa.Column('project_id', sa.Uuid(), nullable=True),
        sa.Column('resource_id', sa.String(length=255), nullable=True),
        sa.Column('correlation_id', sa.String(length=255), nullable=True),
        sa.Column('event_id', sa.String(length=255), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notifications_id', 'notifications', ['id'], unique=False)
    op.create_index('ix_notifications_tenant_id', 'notifications', ['tenant_id'], unique=False)
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'], unique=False)
    op.create_index('ix_notifications_event_type', 'notifications', ['event_type'], unique=False)
    op.create_index('ix_notifications_category', 'notifications', ['category'], unique=False)
    op.create_index('ix_notifications_severity', 'notifications', ['severity'], unique=False)
    op.create_index('ix_notifications_is_read', 'notifications', ['is_read'], unique=False)
    op.create_index('ix_notifications_meeting_id', 'notifications', ['meeting_id'], unique=False)
    op.create_index('ix_notifications_project_id', 'notifications', ['project_id'], unique=False)
    op.create_index('ix_notifications_correlation_id', 'notifications', ['correlation_id'], unique=False)
    op.create_index('ix_notifications_event_id', 'notifications', ['event_id'], unique=False)
    op.create_index('ix_notifications_tenant_user_read', 'notifications', ['tenant_id', 'user_id', 'is_read'], unique=False)
    op.create_index('ix_notifications_tenant_category_created', 'notifications', ['tenant_id', 'category', 'created_at'], unique=False)
    op.create_index('ix_notifications_event_id_unique', 'notifications', ['tenant_id', 'event_id'], unique=False)
    op.create_index('ix_notifications_retention_cleanup', 'notifications', ['tenant_id', 'is_read', 'category', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('notifications')
