"""
Adaptive Blackboard Context & Minimal Knowledge State
Defines the Blackboard contextual state model and knowledge item references.
Blackboard context coordinates real-time meeting context without duplicating SKW lifecycle logic.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel
from app.orchestration.ace_core import ACETask, TaskStatus


class BlackboardKnowledgeItem(CoreBaseModel):

    """
    Reference model for knowledge items held in Blackboard context.
    Represents consumer-side view of a Knowledge Object.
    SKW remains the sole authoritative source of truth.
    """

    knowledge_id: uuid.UUID = Field(..., description="Unique knowledge object identifier")
    meeting_id: uuid.UUID = Field(..., description="Meeting context identifier")
    object_type: str = Field(..., description="Classification (decision, action_item, summary, etc.)")
    source_module: str = Field(..., description="Original producing module/agent")
    title: Optional[str] = Field(default=None, description="Knowledge item title")
    content: str = Field(..., description="Knowledge item content")
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    version: int = Field(default=1, ge=1)
    lifecycle_state: str = Field(default="published", description="Lifecycle state reported by SKW")
    correlation_id: Optional[str] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    payload: Dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BlackboardContext:
    """
    Meeting-specific in-memory Blackboard context.
    Manages active knowledge items, seen event IDs for idempotency, and failure diagnostics.
    """

    def __init__(self, meeting_id: uuid.UUID) -> None:
        self.meeting_id: uuid.UUID = meeting_id
        self.items: Dict[uuid.UUID, BlackboardKnowledgeItem] = {}
        self.tasks: Dict[uuid.UUID, ACETask] = {}
        self.activation_queue: List[uuid.UUID] = []
        self.execution_state: Dict[str, Any] = {
            "status": "IDLE",
            "active_tasks": [],
            "completed_tasks": [],
            "failed_tasks": [],
            "retrying_tasks": [],
        }
        self.seen_event_ids: Set[uuid.UUID] = set()
        self.failed_events: List[Dict[str, Any]] = []
        self.created_at: datetime = datetime.utcnow()
        self.updated_at: datetime = datetime.utcnow()

    # Task tracking & lifecycle on Blackboard
    def upsert_task(self, task: ACETask) -> None:
        """Insert or update an orchestration task in Blackboard context."""
        self.tasks[task.task_id] = task
        self.updated_at = datetime.utcnow()

    def get_task(self, task_id: uuid.UUID) -> Optional[ACETask]:
        """Retrieve a task by ID."""
        return self.tasks.get(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[ACETask]:
        """List tasks registered on the Blackboard with optional status filter."""
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def get_tasks_by_capability(self, capability: str) -> List[ACETask]:
        """Retrieve tasks matching a specific required capability."""
        return [t for t in self.tasks.values() if t.required_capability == capability]

    def record_task_scheduled(self, task_id: uuid.UUID) -> Optional[ACETask]:
        """Record task scheduled state transition on Blackboard."""
        task = self.get_task(task_id)
        if task:
            task.update_status(TaskStatus.SCHEDULED)
            self.updated_at = datetime.utcnow()
        return task

    def record_task_activated(self, task_id: uuid.UUID) -> Optional[ACETask]:
        """Record task activated / running state transition on Blackboard."""
        task = self.get_task(task_id)
        if task:
            task.update_status(TaskStatus.RUNNING)
            if task_id not in self.execution_state["active_tasks"]:
                self.execution_state["active_tasks"].append(task_id)
            self.updated_at = datetime.utcnow()
        return task

    def record_task_completed(self, task_id: uuid.UUID, result_data: Optional[Dict[str, Any]] = None) -> Optional[ACETask]:
        """Record task completed state transition on Blackboard."""
        task = self.get_task(task_id)
        if task:
            task.update_status(TaskStatus.COMPLETED)
            if result_data:
                task.metadata.update(result_data)
            if task_id in self.execution_state["active_tasks"]:
                self.execution_state["active_tasks"].remove(task_id)
            if task_id not in self.execution_state["completed_tasks"]:
                self.execution_state["completed_tasks"].append(task_id)
            self.updated_at = datetime.utcnow()
        return task

    def record_task_failed(self, task_id: uuid.UUID, error_message: str) -> Optional[ACETask]:
        """Record task failed state transition on Blackboard."""
        task = self.get_task(task_id)
        if task:
            task.update_status(TaskStatus.FAILED, error_message=error_message)
            if task_id in self.execution_state["active_tasks"]:
                self.execution_state["active_tasks"].remove(task_id)
            if task_id not in self.execution_state["failed_tasks"]:
                self.execution_state["failed_tasks"].append(task_id)
            self.updated_at = datetime.utcnow()
        return task

    def record_task_retrying(self, task_id: uuid.UUID, retry_count: int) -> Optional[ACETask]:
        """Record task retrying state transition on Blackboard."""
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.RETRYING
            task.retry_count = retry_count
            if task_id in self.execution_state["active_tasks"]:
                self.execution_state["active_tasks"].remove(task_id)
            if task_id not in self.execution_state["retrying_tasks"]:
                self.execution_state["retrying_tasks"].append(task_id)
            self.updated_at = datetime.utcnow()
        return task

    def is_event_seen(self, event_id: uuid.UUID) -> bool:
        """Check if an event ID has already been processed (idempotency check)."""
        return event_id in self.seen_event_ids

    def mark_event_seen(self, event_id: uuid.UUID) -> None:
        """Mark an event ID as processed."""
        self.seen_event_ids.add(event_id)
        self.updated_at = datetime.utcnow()

    def upsert_item(self, item: BlackboardKnowledgeItem) -> None:
        """Insert or update a knowledge item in Blackboard context."""
        self.items[item.knowledge_id] = item
        self.updated_at = datetime.utcnow()

    def get_item(self, knowledge_id: uuid.UUID) -> Optional[BlackboardKnowledgeItem]:
        """Retrieve an active knowledge item by ID."""
        return self.items.get(knowledge_id)

    def archive_item(self, knowledge_id: uuid.UUID, reason: Optional[str] = None) -> Optional[BlackboardKnowledgeItem]:
        """Mark a knowledge item as archived in Blackboard context."""
        item = self.items.get(knowledge_id)
        if item:
            item.lifecycle_state = "archived"
            item.updated_at = datetime.utcnow()
            if reason:
                item.metadata["archive_reason"] = reason
            self.updated_at = datetime.utcnow()
        return item

    def remove_item(self, knowledge_id: uuid.UUID) -> Optional[BlackboardKnowledgeItem]:
        """Remove a knowledge item from active Blackboard context."""
        item = self.items.pop(knowledge_id, None)
        if item:
            self.updated_at = datetime.utcnow()
        return item

    def record_failure(self, failure_info: Dict[str, Any]) -> None:
        """Record diagnostic information for failed or rejected knowledge events."""
        self.failed_events.append(failure_info)
        self.updated_at = datetime.utcnow()

    def list_items(
        self,
        object_type: Optional[str] = None,
        lifecycle_state: Optional[str] = None,
    ) -> List[BlackboardKnowledgeItem]:
        """List active knowledge items with optional type and state filtering."""
        result = list(self.items.values())
        if object_type:
            result = [i for i in result if i.object_type.lower() == object_type.lower()]
        if lifecycle_state:
            result = [i for i in result if i.lifecycle_state.lower() == lifecycle_state.lower()]
        return result
