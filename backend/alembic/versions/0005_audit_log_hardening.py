"""Alembic migration for Phase 4.25 Audit Log hardening

Revision ID: 0005_audit_log_hardening
Revises: 0004_notifications_schema
Create Date: 2026-08-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_audit_log_hardening'
down_revision: Union[str, None] = '0004_notifications_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check and add columns to audit_logs table
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.String(length=100), nullable=False, server_default='tenant-default'))
        batch_op.add_column(sa.Column('event_type', sa.String(length=100), nullable=False, server_default='audit.event'))
        batch_op.add_column(sa.Column('category', sa.String(length=50), nullable=False, server_default='system'))
        batch_op.add_column(sa.Column('severity', sa.String(length=20), nullable=False, server_default='info'))
        batch_op.add_column(sa.Column('outcome', sa.String(length=50), nullable=False, server_default='success'))
        batch_op.add_column(sa.Column('project_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('correlation_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('request_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('event_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('metadata_json', sa.JSON(), nullable=True))
        
        batch_op.create_foreign_key('fk_audit_logs_project_id', 'projects', ['project_id'], ['id'], ondelete='SET NULL')

        # Additional indexes for compliance & performant multi-tenant filtering
        batch_op.create_index('ix_audit_logs_tenant_id', ['tenant_id'], unique=False)
        batch_op.create_index('ix_audit_logs_event_type', ['event_type'], unique=False)
        batch_op.create_index('ix_audit_logs_category', ['category'], unique=False)
        batch_op.create_index('ix_audit_logs_severity', ['severity'], unique=False)
        batch_op.create_index('ix_audit_logs_outcome', ['outcome'], unique=False)
        batch_op.create_index('ix_audit_logs_resource_id', ['resource_id'], unique=False)
        batch_op.create_index('ix_audit_logs_project_id', ['project_id'], unique=False)
        batch_op.create_index('ix_audit_logs_correlation_id', ['correlation_id'], unique=False)
        batch_op.create_index('ix_audit_logs_request_id', ['request_id'], unique=False)
        batch_op.create_index('ix_audit_logs_event_id', ['event_id'], unique=False)

        batch_op.create_index('ix_audit_logs_tenant_created', ['tenant_id', 'created_at'], unique=False)
        batch_op.create_index('ix_audit_logs_tenant_event_created', ['tenant_id', 'event_type', 'created_at'], unique=False)
        batch_op.create_index('ix_audit_logs_tenant_user_created', ['tenant_id', 'user_id', 'created_at'], unique=False)
        batch_op.create_index('ix_audit_logs_tenant_resource_created', ['tenant_id', 'resource_id', 'created_at'], unique=False)
        batch_op.create_index('ix_audit_logs_tenant_severity_created', ['tenant_id', 'severity', 'created_at'], unique=False)
        batch_op.create_index('ix_audit_logs_tenant_category_created', ['tenant_id', 'category', 'created_at'], unique=False)
        batch_op.create_index('ix_audit_logs_tenant_event_id', ['tenant_id', 'event_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.drop_index('ix_audit_logs_tenant_event_id')
        batch_op.drop_index('ix_audit_logs_tenant_category_created')
        batch_op.drop_index('ix_audit_logs_tenant_severity_created')
        batch_op.drop_index('ix_audit_logs_tenant_resource_created')
        batch_op.drop_index('ix_audit_logs_tenant_user_created')
        batch_op.drop_index('ix_audit_logs_tenant_event_created')
        batch_op.drop_index('ix_audit_logs_tenant_created')
        batch_op.drop_index('ix_audit_logs_event_id')
        batch_op.drop_index('ix_audit_logs_request_id')
        batch_op.drop_index('ix_audit_logs_correlation_id')
        batch_op.drop_index('ix_audit_logs_project_id')
        batch_op.drop_index('ix_audit_logs_resource_id')
        batch_op.drop_index('ix_audit_logs_outcome')
        batch_op.drop_index('ix_audit_logs_severity')
        batch_op.drop_index('ix_audit_logs_category')
        batch_op.drop_index('ix_audit_logs_event_type')
        batch_op.drop_index('ix_audit_logs_tenant_id')
        batch_op.drop_constraint('fk_audit_logs_project_id', type_='foreignkey')
        batch_op.drop_column('metadata_json')
        batch_op.drop_column('event_id')
        batch_op.drop_column('request_id')
        batch_op.drop_column('correlation_id')
        batch_op.drop_column('project_id')
        batch_op.drop_column('outcome')
        batch_op.drop_column('severity')
        batch_op.drop_column('category')
        batch_op.drop_column('event_type')
        batch_op.drop_column('tenant_id')
