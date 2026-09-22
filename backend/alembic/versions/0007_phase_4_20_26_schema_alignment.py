"""Align phase 4.20-4.26 ORM tables with the production schema.

Revision ID: 0007_phase_4_20_26_schema_alignment
Revises: 0006_query_history_schema
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_phase_4_20_26_schema_alignment"
down_revision: Union[str, None] = "0006_query_history_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("duration_minutes", sa.Integer(), nullable=True))
    op.add_column("meetings", sa.Column("tenant_id", sa.String(length=100), nullable=True))
    op.create_index("ix_meetings_tenant_id", "meetings", ["tenant_id"], unique=False)

    op.create_table(
        "platform_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="connected"),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connection_metadata", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_connections_user_id", "platform_connections", ["user_id"], unique=False)
    op.create_index("ix_platform_connections_provider", "platform_connections", ["provider"], unique=False)
    op.create_index("ix_platform_connections_status", "platform_connections", ["status"], unique=False)

    op.create_table(
        "external_meeting_references",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=255), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("external_metadata", sa.JSON(), nullable=True),
        sa.Column("sync_status", sa.String(length=50), nullable=False, server_default="synced"),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["platform_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_external_meeting_references_connection_id", "external_meeting_references", ["connection_id"], unique=False)
    op.create_index("ix_external_meeting_references_meeting_id", "external_meeting_references", ["meeting_id"], unique=False)
    op.create_index("ix_external_meeting_references_external_meeting_id", "external_meeting_references", ["external_meeting_id"], unique=False)
    op.create_index("ix_external_meeting_references_external_event_id", "external_meeting_references", ["external_event_id"], unique=False)

    op.create_table(
        "meeting_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("report_type", sa.String(length=100), nullable=False, server_default="comprehensive"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="generated"),
        sa.Column("format", sa.String(length=20), nullable=False, server_default="json"),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("generated_by", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meeting_reports_meeting_id", "meeting_reports", ["meeting_id"], unique=False)
    op.create_index("ix_meeting_reports_tenant_id", "meeting_reports", ["tenant_id"], unique=False)
    op.create_index("ix_meeting_reports_status", "meeting_reports", ["status"], unique=False)

    op.create_table(
        "derived_translations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("source_object_id", sa.Uuid(), nullable=True),
        sa.Column("source_segment_id", sa.Uuid(), nullable=True),
        sa.Column("representation_type", sa.String(length=50), nullable=False),
        sa.Column("source_language", sa.String(length=10), nullable=False),
        sa.Column("target_language", sa.String(length=10), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("is_low_confidence", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("requires_verification", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("speaker_label", sa.String(length=50), nullable=True),
        sa.Column("start_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("end_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_object_id"], ["knowledge_objects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_segment_id"], ["transcript_segments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_derived_translations_meeting_id", "derived_translations", ["meeting_id"], unique=False)
    op.create_index("ix_derived_translations_tenant_id", "derived_translations", ["tenant_id"], unique=False)
    op.create_index("ix_derived_translations_source_object_id", "derived_translations", ["source_object_id"], unique=False)
    op.create_index("ix_derived_translations_source_segment_id", "derived_translations", ["source_segment_id"], unique=False)
    op.create_index("ix_derived_translations_representation_type", "derived_translations", ["representation_type"], unique=False)
    op.create_index("ix_derived_translations_target_language", "derived_translations", ["target_language"], unique=False)
    op.create_index("ix_derived_translations_status", "derived_translations", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("derived_translations")
    op.drop_table("meeting_reports")
    op.drop_table("external_meeting_references")
    op.drop_table("platform_connections")
    op.drop_index("ix_meetings_tenant_id", table_name="meetings")
    op.drop_column("meetings", "tenant_id")
    op.drop_column("meetings", "duration_minutes")
