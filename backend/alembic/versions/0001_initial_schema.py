"""Initial schema migration

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('preferences', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index('ix_users_id', 'users', ['id'], unique=False)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_status', 'users', ['status'], unique=False)

    # 2. Meetings table
    op.create_table(
        'meetings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('secondary_languages', sa.JSON(), nullable=True),
        sa.Column('host_id', sa.Uuid(), nullable=True),
        sa.Column('scheduled_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('settings', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_meetings_id', 'meetings', ['id'], unique=False)
    op.create_index('ix_meetings_status', 'meetings', ['status'], unique=False)
    op.create_index('ix_meetings_host_id', 'meetings', ['host_id'], unique=False)
    op.create_index('ix_meetings_status_created_at', 'meetings', ['status', 'created_at'], unique=False)
    op.create_index('ix_meetings_host_created_at', 'meetings', ['host_id', 'created_at'], unique=False)

    # 3. Participants table
    op.create_table(
        'participants',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('meeting_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('speaker_label', sa.String(length=50), nullable=True),
        sa.Column('voiceprint_id', sa.String(length=255), nullable=True),
        sa.Column('speaking_duration', sa.Float(), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_participants_id', 'participants', ['id'], unique=False)
    op.create_index('ix_participants_meeting_id', 'participants', ['meeting_id'], unique=False)
    op.create_index('ix_participants_user_id', 'participants', ['user_id'], unique=False)
    op.create_index('ix_participants_meeting_speaker', 'participants', ['meeting_id', 'speaker_label'], unique=False)
    op.create_index('ix_participants_meeting_user', 'participants', ['meeting_id', 'user_id'], unique=False)

    # 4. Audio recordings table
    op.create_table(
        'audio_recordings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('meeting_id', sa.Uuid(), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('format', sa.String(length=50), nullable=False),
        sa.Column('sample_rate', sa.Integer(), nullable=False),
        sa.Column('channels', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('meta_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audio_recordings_id', 'audio_recordings', ['id'], unique=False)
    op.create_index('ix_audio_recordings_meeting_id', 'audio_recordings', ['meeting_id'], unique=False)
    op.create_index('ix_audio_recordings_status', 'audio_recordings', ['status'], unique=False)

    # 5. Transcript segments table
    op.create_table(
        'transcript_segments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('meeting_id', sa.Uuid(), nullable=False),
        sa.Column('participant_id', sa.Uuid(), nullable=True),
        sa.Column('speaker_label', sa.String(length=50), nullable=True),
        sa.Column('start_time_ms', sa.BigInteger(), nullable=False),
        sa.Column('end_time_ms', sa.BigInteger(), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('original_text', sa.Text(), nullable=False),
        sa.Column('translated_text', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('is_final', sa.Boolean(), nullable=False),
        sa.Column('sequence_number', sa.Integer(), nullable=False),
        sa.Column('words_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('end_time_ms >= start_time_ms', name='ck_transcript_segments_time_range'),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_transcript_segments_id', 'transcript_segments', ['id'], unique=False)
    op.create_index('ix_transcript_segments_meeting_id', 'transcript_segments', ['meeting_id'], unique=False)
    op.create_index('ix_transcript_segments_participant_id', 'transcript_segments', ['participant_id'], unique=False)
    op.create_index('ix_transcript_segments_sequence_number', 'transcript_segments', ['sequence_number'], unique=False)
    op.create_index('ix_transcript_segments_meeting_seq', 'transcript_segments', ['meeting_id', 'sequence_number'], unique=False)
    op.create_index('ix_transcript_segments_meeting_time', 'transcript_segments', ['meeting_id', 'start_time_ms'], unique=False)

    # 6. Canonical transcripts table
    op.create_table(
        'transcripts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('meeting_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('full_text', sa.Text(), nullable=False),
        sa.Column('is_final', sa.Boolean(), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=False),
        sa.Column('provenance', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_transcripts_id', 'transcripts', ['id'], unique=False)
    op.create_index('ix_transcripts_meeting_id', 'transcripts', ['meeting_id'], unique=False)
    op.create_index('ix_transcripts_meeting_version', 'transcripts', ['meeting_id', 'version'], unique=False)

    # 7. Meeting analytics table
    op.create_table(
        'meeting_analytics',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('meeting_id', sa.Uuid(), nullable=False),
        sa.Column('speaking_time_distribution', sa.JSON(), nullable=False),
        sa.Column('collaboration_score', sa.Float(), nullable=True),
        sa.Column('participation_index', sa.Float(), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('productivity_score', sa.Float(), nullable=True),
        sa.Column('sentiment_distribution', sa.JSON(), nullable=True),
        sa.Column('engagement_score', sa.Float(), nullable=True),
        sa.Column('pace_wpm', sa.Float(), nullable=True),
        sa.Column('turn_taking_metrics', sa.JSON(), nullable=True),
        sa.Column('topic_keywords', sa.JSON(), nullable=True),
        sa.Column('summary_metrics', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('meeting_id')
    )
    op.create_index('ix_meeting_analytics_id', 'meeting_analytics', ['id'], unique=False)
    op.create_index('ix_meeting_analytics_meeting_id', 'meeting_analytics', ['meeting_id'], unique=True)

    # 8. Audit logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('meeting_id', sa.Uuid(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.String(length=255), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_logs_id', 'audit_logs', ['id'], unique=False)
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'], unique=False)
    op.create_index('ix_audit_logs_meeting_id', 'audit_logs', ['meeting_id'], unique=False)
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'], unique=False)
    op.create_index('ix_audit_logs_action_created', 'audit_logs', ['action', 'created_at'], unique=False)
    op.create_index('ix_audit_logs_meeting_created', 'audit_logs', ['meeting_id', 'created_at'], unique=False)

    # 9. System configurations table
    op.create_table(
        'system_configurations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('is_secret', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )
    op.create_index('ix_system_configurations_id', 'system_configurations', ['id'], unique=False)
    op.create_index('ix_system_configurations_key', 'system_configurations', ['key'], unique=True)
    op.create_index('ix_system_configurations_category', 'system_configurations', ['category'], unique=False)

    # 10. Knowledge objects table
    op.create_table(
        'knowledge_objects',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('meeting_id', sa.Uuid(), nullable=False),
        sa.Column('object_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.Uuid(), nullable=True),
        sa.Column('provenance', sa.JSON(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('qdrant_point_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_id'], ['knowledge_objects.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_knowledge_objects_id', 'knowledge_objects', ['id'], unique=False)
    op.create_index('ix_knowledge_objects_meeting_id', 'knowledge_objects', ['meeting_id'], unique=False)
    op.create_index('ix_knowledge_objects_object_type', 'knowledge_objects', ['object_type'], unique=False)
    op.create_index('ix_knowledge_objects_status', 'knowledge_objects', ['status'], unique=False)
    op.create_index('ix_knowledge_objects_parent_id', 'knowledge_objects', ['parent_id'], unique=False)
    op.create_index('ix_knowledge_objects_meeting_type', 'knowledge_objects', ['meeting_id', 'object_type'], unique=False)


def downgrade() -> None:
    op.drop_table('knowledge_objects')
    op.drop_table('system_configurations')
    op.drop_table('audit_logs')
    op.drop_table('meeting_analytics')
    op.drop_table('transcripts')
    op.drop_table('transcript_segments')
    op.drop_table('audio_recordings')
    op.drop_table('participants')
    op.drop_table('meetings')
    op.drop_table('users')
