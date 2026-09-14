"""
ABCI-MI Domain & Operational SQLAlchemy ORM Models
"""

from app.models.base import BaseModel, TableNameMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.user import User
from app.models.meeting import Meeting
from app.models.participant import Participant
from app.models.audio import Audio
from app.models.transcript import Transcript, TranscriptSegment
from app.models.analytics import MeetingAnalytics
from app.models.audit_log import AuditLog
from app.models.configuration import SystemConfiguration
from app.models.knowledge_object import KnowledgeObject
from app.models.live_session import LiveSession, LiveAudioChunk

__all__ = [
    "BaseModel",
    "TableNameMixin",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "User",
    "Meeting",
    "Participant",
    "Audio",
    "Transcript",
    "TranscriptSegment",
    "MeetingAnalytics",
    "AuditLog",
    "SystemConfiguration",
    "KnowledgeObject",
    "LiveSession",
    "LiveAudioChunk",
    "PlatformConnection",
    "ExternalMeetingReference",
    "MeetingReport",
    "DerivedTranslation",
]

from app.models.platform_integration import PlatformConnection, ExternalMeetingReference
from app.models.report import MeetingReport
from app.models.translation import DerivedTranslation
from app.models.project import Project, ProjectMeeting
from app.models.notification import Notification
from app.models.query_record import QueryRecord

__all__ = [
    "BaseModel",
    "TableNameMixin",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "User",
    "Meeting",
    "Participant",
    "Audio",
    "Transcript",
    "TranscriptSegment",
    "MeetingAnalytics",
    "AuditLog",
    "SystemConfiguration",
    "KnowledgeObject",
    "LiveSession",
    "LiveAudioChunk",
    "PlatformConnection",
    "ExternalMeetingReference",
    "MeetingReport",
    "DerivedTranslation",
    "Project",
    "ProjectMeeting",
    "Notification",
    "QueryRecord",
]
