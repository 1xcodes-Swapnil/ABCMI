"""Alembic migration for Phase 4.23 Query History schema

Revision ID: 0006_query_history_schema
Revises: 0005_audit_log_hardening
Create Date: 2026-08-15 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_query_history_schema'
down_revision: Union[str, None] = '0005_audit_log_hardening'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'query_records',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('scope', sa.String(length=50), nullable=False, server_default='meeting'),
        sa.Column('meeting_id', sa.Uuid(), nullable=True),
        sa.Column('project_id', sa.Uuid(), nullable=True),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='answered'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0.8'),
        sa.Column('is_low_confidence', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('requires_verification', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('search_mode', sa.String(length=50), nullable=False, server_default='hybrid'),
        sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('source_meetings', sa.JSON(), nullable=False),
        sa.Column('source_projects', sa.JSON(), nullable=False),
        sa.Column('provenance', sa.JSON(), nullable=False),
        sa.Column('correlation_id', sa.String(length=255), nullable=True),
        sa.Column('request_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('ix_query_records_tenant_id', 'query_records', ['tenant_id'], unique=False)
    op.create_index('ix_query_records_user_id', 'query_records', ['user_id'], unique=False)
    op.create_index('ix_query_records_scope', 'query_records', ['scope'], unique=False)
    op.create_index('ix_query_records_meeting_id', 'query_records', ['meeting_id'], unique=False)
    op.create_index('ix_query_records_project_id', 'query_records', ['project_id'], unique=False)
    op.create_index('ix_query_records_status', 'query_records', ['status'], unique=False)
    op.create_index('ix_query_records_correlation_id', 'query_records', ['correlation_id'], unique=False)
    op.create_index('ix_query_records_request_id', 'query_records', ['request_id'], unique=False)

    op.create_index('ix_query_records_tenant_created', 'query_records', ['tenant_id', 'created_at'], unique=False)
    op.create_index('ix_query_records_meeting_created', 'query_records', ['meeting_id', 'created_at'], unique=False)
    op.create_index('ix_query_records_project_created', 'query_records', ['project_id', 'created_at'], unique=False)
    op.create_index('ix_query_records_user_created', 'query_records', ['user_id', 'created_at'], unique=False)
    op.create_index('ix_query_records_tenant_correlation', 'query_records', ['tenant_id', 'correlation_id'], unique=False)


def downgrade() -> None:
    op.drop_table('query_records')
