"""
ACE Orchestration Domain Events & Contracts (Phase 4.11B)
Defines strongly typed event schemas for event-driven orchestration across the task lifecycle.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel


class ACEOrchestrationEventType(str, Enum):
    """Authoritative event type identifiers for ACE orchestration lifecycle."""

    PROCESSING_REQUESTED = "orchestration.processing_requested"
    TASK_PLANNED = "orchestration.task_planned"
    TASK_SCHEDULED = "orchestration.task_scheduled"
    TASK_ACTIVATED = "orchestration.task_activated"
    TASK_STARTED = "orchestration.task_started"
    TASK_COMPLETED = "orchestration.task_completed"
    TASK_FAILED = "orchestration.task_failed"
    RETRY_REQUESTED = "orchestration.retry_requested"
    RECOVERY_TRIGGERED = "orchestration.recovery_triggered"
    CONTEXT_UPDATED = "orchestration.context_updated"
    PROCESSING_COMPLETED = "orchestration.processing_completed"


class ACEBaseOrchestrationEvent(CoreBaseModel):
    """Base orchestration event model with tracking and correlation properties."""

    event_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique event message identifier",
    )
    event_type: ACEOrchestrationEventType = Field(
        ...,
        description="Authoritative event type classifier",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC event timestamp",
    )
    request_id: uuid.UUID = Field(
        ...,
        description="Global processing request identifier",
    )
    meeting_id: uuid.UUID = Field(
        ...,
        description="Meeting context identifier",
    )
    task_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Task identifier if applicable",
    )
    task_type: Optional[str] = Field(
        default=None,
        description="Task type classification",
    )
    required_capability: Optional[str] = Field(
        default=None,
        description="Target AI processing capability",
    )
    status: Optional[str] = Field(
        default=None,
        description="Current task or request lifecycle status",
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Tracing correlation identifier",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic or result metadata payload",
    )


class ProcessingRequestedEvent(ACEBaseOrchestrationEvent):
    """Emitted when a new meeting processing request arrives."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.PROCESSING_REQUESTED)
    enable_analytics: bool = Field(default=True)
    enable_memory: bool = Field(default=True)


class TaskPlannedEvent(ACEBaseOrchestrationEvent):
    """Emitted when task graph planning completes."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.TASK_PLANNED)
    total_tasks: int = Field(..., ge=1)


class TaskScheduledEvent(ACEBaseOrchestrationEvent):
    """Emitted when a ready task is scheduled for execution."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.TASK_SCHEDULED)
    priority: int = Field(default=0)


class TaskActivatedEvent(ACEBaseOrchestrationEvent):
    """Emitted when a scheduled task activates a processing capability."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.TASK_ACTIVATED)


class TaskStartedEvent(ACEBaseOrchestrationEvent):
    """Emitted when an AI processing module starts execution."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.TASK_STARTED)


class TaskCompletedEvent(ACEBaseOrchestrationEvent):
    """Emitted when an AI processing capability completes execution successfully."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.TASK_COMPLETED)
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    result_data: Dict[str, Any] = Field(default_factory=dict)


class TaskFailedEvent(ACEBaseOrchestrationEvent):
    """Emitted when an AI processing capability or dependency fails."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.TASK_FAILED)
    error_code: str = Field(default="EXECUTION_FAILED")
    error_message: str = Field(...)


class RetryRequestedEvent(ACEBaseOrchestrationEvent):
    """Emitted when a failed task is granted a retry attempt."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.RETRY_REQUESTED)
    retry_count: int = Field(..., ge=1)
    max_retries: int = Field(default=3)


class RecoveryTriggeredEvent(ACEBaseOrchestrationEvent):
    """Emitted when task failures exceed retry limits or require manual escalation."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.RECOVERY_TRIGGERED)
    reason: str = Field(...)
    failure_details: Dict[str, Any] = Field(default_factory=dict)


class ContextUpdatedEvent(ACEBaseOrchestrationEvent):
    """Emitted when task progress updates meeting Blackboard context."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.CONTEXT_UPDATED)
    context_type: str = Field(...)


class ProcessingCompletedEvent(ACEBaseOrchestrationEvent):
    """Emitted when all tasks in a processing graph reach completion."""

    event_type: ACEOrchestrationEventType = Field(default=ACEOrchestrationEventType.PROCESSING_COMPLETED)
    completed_task_count: int = Field(...)
    duration_seconds: float = Field(...)
