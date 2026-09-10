"""
ACE Failure & Recovery Manager (Phase 4.11B)
Provides policy-driven failure assessment, bounded retry management, and recovery escalation.
Prevents infinite loops and preserves diagnostic context on task failures.
"""

from typing import Any, Dict, Optional
import uuid
from pydantic import Field

from app.core.logging import get_logger
from app.orchestration.ace_core import ACETask, PolicyManager, TaskStatus
from app.schemas.base import CoreBaseModel

logger = get_logger("orchestration.recovery_manager")


class RecoveryDecision(CoreBaseModel):
    """Encapsulates recovery assessment outcome for a failed task."""

    action: str = Field(
        ...,
        description="Target recovery action ('RETRY' or 'RECOVERY_REQUIRED')",
    )
    task_id: uuid.UUID
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    delay_seconds: float = Field(default=0.0)
    reason: str
    error_details: Dict[str, Any] = Field(default_factory=dict)


class RecoveryManager:
    """
    Manages task execution failure isolation, bounded retry count enforcement,
    and escalation when retry budgets are exhausted.
    """

    def __init__(self, policy_manager: Optional[PolicyManager] = None) -> None:
        self.policy_manager = policy_manager or PolicyManager()

    def evaluate_task_failure(
        self,
        task: ACETask,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> RecoveryDecision:
        """
        Evaluate a task execution failure against policy retry limits.
        Enforces strict upper bounds on retries to prevent infinite loops.
        """
        max_retries = self.policy_manager.get_policy("default_retry_limit", 3)

        next_retry_count = task.retry_count + 1

        details = error_details or {}
        details.update({
            "task_id": str(task.task_id),
            "task_type": task.task_type,
            "capability": task.required_capability,
            "error_message": error_message,
            "correlation_id": correlation_id,
        })

        if next_retry_count <= max_retries:
            logger.info(
                f"Task {task.task_id} ({task.task_type}) failed. "
                f"Granting retry attempt {next_retry_count}/{max_retries}. "
                f"correlation_id={correlation_id}"
            )
            return RecoveryDecision(
                action="RETRY",
                task_id=task.task_id,
                retry_count=next_retry_count,
                max_retries=max_retries,
                delay_seconds=1.0 * next_retry_count,  # Exponential backoff suggestion
                reason=f"Failure within retry budget ({next_retry_count}/{max_retries})",
                error_details=details,
            )

        logger.error(
            f"Task {task.task_id} ({task.task_type}) exceeded retry limit ({max_retries}). "
            f"Triggering recovery escalation. correlation_id={correlation_id}"
        )
        return RecoveryDecision(
            action="RECOVERY_REQUIRED",
            task_id=task.task_id,
            retry_count=task.retry_count,
            max_retries=max_retries,
            delay_seconds=0.0,
            reason=f"Retry budget exhausted ({task.retry_count}/{max_retries}): {error_message}",
            error_details=details,
        )
