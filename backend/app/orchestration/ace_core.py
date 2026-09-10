"""
Adaptive Collaboration Engine (ACE) Core Orchestration Logic.
Provides the deterministic components for task representation, planning,
dependency analysis, scheduling, routing, state tracking, and policy management.
"""

from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel

logger = logging.getLogger("orchestration.ace_core")


class TaskStatus(str, Enum):
    """Execution states representing the standard task lifecycle."""
    PENDING = "PENDING"
    READY = "READY"
    SCHEDULED = "SCHEDULED"
    ACTIVATED = "ACTIVATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class ACETask(CoreBaseModel):
    """
    Minimal representation of a task to be processed by ACE.
    """
    task_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique task identifier")
    meeting_id: uuid.UUID = Field(..., description="Meeting or request context identifier")
    task_type: str = Field(..., description="The type/name of processing task")
    dependencies: List[uuid.UUID] = Field(default_factory=list, description="IDs of tasks that must finish first")
    priority: int = Field(default=0, description="Execution priority (higher value runs first)")
    required_capability: str = Field(..., description="Required capability identifier for routing")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current lifecycle state of the task")
    retry_count: int = Field(default=0, description="Count of retries attempted")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="Input payload for task execution")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata logs, error diagnostics or payload")

    def update_status(self, new_status: TaskStatus, error_message: Optional[str] = None) -> None:
        """Update task status and optional error message."""
        self.status = new_status
        if error_message:
            self.metadata["error_message"] = error_message


class PolicyManager:
    """
    Centralizes orchestration policies, limits, and runtime configurations.
    """
    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None) -> None:
        self._policies = {
            "max_concurrency": 5,
            "default_retry_limit": 3,
            "task_timeout_seconds": 30.0,
            "min_confidence_threshold": 0.70,
            "overlap_resolution_policy": "fuse_alternatives",
        }
        if config_overrides:
            self._policies.update(config_overrides)

        self._capability_concurrency_limits: Dict[str, int] = {
            "audio_intelligence": 1,
            "multilingual_asr": 2,
            "code_switch_intelligence": 2,
            "speaker_representation": 2,
            "overlap_resolution": 2,
            "timestamp_intelligence": 3,
            "context_intelligence": 3,
            "transcript_intelligence": 3,
            "confidence_fusion": 2,
            "verification_engine": 2,
            "meeting_understanding": 2,
            "meeting_analytics": 2,
            "knowledge_memory": 2,
        }

    def get_policy(self, key: str, default: Any = None) -> Any:
        """Retrieves a configuration policy value by key."""
        return self._policies.get(key, default)

    def set_policy(self, key: str, value: Any) -> None:
        """Updates or sets a policy configuration value."""
        self._policies[key] = value

    def get_capability_limit(self, capability: str) -> int:
        """Gets maximum allowed concurrent execution limit for a specific capability."""
        return self._capability_concurrency_limits.get(capability, 2)

    def set_capability_limit(self, capability: str, limit: int) -> None:
        """Updates maximum concurrent execution limit for a capability."""
        self._capability_concurrency_limits[capability] = limit

    @property
    def default_retry_limit(self) -> int:
        return self.get_policy("default_retry_limit", 3)

    @property
    def min_confidence_threshold(self) -> float:
        return self.get_policy("min_confidence_threshold", 0.70)

    @property
    def max_concurrency(self) -> int:
        return self.get_policy("max_concurrency", 5)

    @property
    def task_timeout_seconds(self) -> float:
        return self.get_policy("task_timeout_seconds", 30.0)


class ACETaskPlan(CoreBaseModel):
    """
    Encapsulates a planned graph of executable tasks for a request.
    """
    planner_id: str = "ace_default_planner"
    tasks: List[ACETask] = Field(default_factory=list)


class DependencyAnalyzer:
    """
    Analyzes and validates task dependency relationships in a Task Graph.
    """
    @staticmethod
    def validate_plan(plan_or_tasks: Any) -> None:
        """
        Validates the task graph configuration:
        - Detects duplicate task IDs.
        - Detects missing dependencies (non-existent task ID referenced).
        - Detects circular dependencies (cycles).
        """
        tasks = plan_or_tasks.tasks if isinstance(plan_or_tasks, ACETaskPlan) or hasattr(plan_or_tasks, "tasks") else plan_or_tasks
        seen_ids = set()
        for task in tasks:
            if task.task_id in seen_ids:
                raise ValueError(f"Duplicate task ID detected: {task.task_id}")
            seen_ids.add(task.task_id)

        task_dict = {task.task_id: task for task in tasks}

        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id not in task_dict:
                    raise ValueError(f"Task {task.task_id} references missing dependency: {dep_id}")

        # Cycle detection using DFS
        # States: 0 = unvisited, 1 = visiting, 2 = visited
        visit_states = {task.task_id: 0 for task in tasks}

        def dfs(task_id: uuid.UUID) -> bool:
            if visit_states[task_id] == 1:
                return True  # Cycle detected
            if visit_states[task_id] == 2:
                return False

            visit_states[task_id] = 1
            for dep_id in task_dict[task_id].dependencies:
                if dfs(dep_id):
                    return True
            visit_states[task_id] = 2
            return False

        for task in tasks:
            if visit_states[task.task_id] == 0:
                if dfs(task.task_id):
                    raise ValueError("Circular dependency detected in task plan")

    @staticmethod
    def get_ready_tasks(tasks: List[ACETask]) -> List[ACETask]:
        """
        Returns all tasks in PENDING/READY/RETRYING status whose dependencies are all COMPLETED.
        """
        task_dict = {task.task_id: task for task in tasks}
        ready = []
        for task in tasks:
            if task.status not in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RETRYING):
                continue

            deps_satisfied = True
            for dep_id in task.dependencies:
                dep_task = task_dict.get(dep_id)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    deps_satisfied = False
                    break

            if deps_satisfied:
                ready.append(task)
        return ready

    @staticmethod
    def get_blocked_tasks(tasks: List[ACETask]) -> List[ACETask]:
        """
        Returns all tasks in PENDING/READY status with at least one incomplete dependency.
        """
        task_dict = {task.task_id: task for task in tasks}
        blocked = []
        for task in tasks:
            if task.status not in (TaskStatus.PENDING, TaskStatus.READY):
                continue

            has_uncompleted = False
            for dep_id in task.dependencies:
                dep_task = task_dict.get(dep_id)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    has_uncompleted = True
                    break

            if has_uncompleted:
                blocked.append(task)
        return blocked

    @staticmethod
    def has_failed_dependencies(task: ACETask, tasks: List[ACETask]) -> bool:
        """
        Determines if any of the direct dependencies of a task have FAILED or are in RECOVERY_REQUIRED.
        """
        task_dict = {t.task_id: t for t in tasks}
        for dep_id in task.dependencies:
            dep_task = task_dict.get(dep_id)
            if dep_task and dep_task.status in (TaskStatus.FAILED, TaskStatus.RECOVERY_REQUIRED):
                return True
        return False


class TaskPlanner:
    """
    Generates deterministic executable task graphs from meeting requests.
    Supports parallel task chains where execution paths do not overlap.
    """
    def __init__(self, policy_manager: Optional[PolicyManager] = None) -> None:
        self.policy_manager = policy_manager

    @staticmethod
    def generate_plan(
        meeting_id: uuid.UUID,
        languages: Optional[List[str]] = None,
        enable_analytics: bool = True,
        enable_memory: bool = True,
    ) -> List[ACETask]:
        """
        Creates a complete multilingual processing task graph for a meeting.
        """
        tasks: Dict[str, ACETask] = {}

        def add_task(cap: str, deps: List[str], priority: int = 0) -> ACETask:
            dep_uuids = [tasks[d].task_id for d in deps if d in tasks]
            task = ACETask(
                meeting_id=meeting_id,
                task_type=f"process_{cap}",
                dependencies=dep_uuids,
                priority=priority,
                required_capability=cap,
                status=TaskStatus.PENDING,
            )
            tasks[cap] = task
            return task

        # Ingestion layer
        add_task("audio_intelligence", [], priority=10)

        # Extraction/parsing tier
        add_task("multilingual_asr", ["audio_intelligence"], priority=8)
        add_task("overlap_resolution", ["audio_intelligence"], priority=7)
        add_task("speaker_representation", ["audio_intelligence"], priority=7)

        # Synthesis/alignment tier
        add_task("code_switch_intelligence", ["multilingual_asr", "speaker_representation"], priority=6)
        add_task("timestamp_intelligence", ["multilingual_asr"], priority=6)
        add_task("transcript_intelligence", ["multilingual_asr", "speaker_representation", "overlap_resolution"], priority=6)
        add_task("confidence_fusion", ["multilingual_asr", "overlap_resolution"], priority=6)

        # Validation & analysis tier
        add_task("context_intelligence", ["transcript_intelligence"], priority=5)
        add_task("verification_engine", ["confidence_fusion"], priority=5)

        # Insight & comprehension tier
        add_task("meeting_understanding", ["context_intelligence", "verification_engine"], priority=4)

        # Downstream outcomes
        if enable_analytics:
            add_task("meeting_analytics", ["meeting_understanding", "transcript_intelligence"], priority=3)
        if enable_memory:
            add_task("knowledge_memory", ["meeting_understanding"], priority=3)

        return list(tasks.values())

    @classmethod
    def plan_request(cls, request: Any) -> ACETaskPlan:
        """
        Generates an ACETaskPlan from a processing request object.
        """
        meeting_id = getattr(request, "meeting_id", None) or uuid.uuid4()
        enable_analytics = getattr(request, "enable_analytics", True)
        enable_memory = getattr(request, "enable_memory", True)
        tasks = cls.generate_plan(
            meeting_id=meeting_id,
            enable_analytics=enable_analytics,
            enable_memory=enable_memory,
        )
        return ACETaskPlan(planner_id="ace_default_planner", tasks=tasks)



class AdaptiveTaskScheduler:
    """
    Selects ready tasks for scheduling, respecting priority, limits, and policy constraints.
    """
    def __init__(self, policy_manager: Optional[PolicyManager] = None) -> None:
        self.policy_manager = policy_manager or PolicyManager()

    def schedule_next(self, tasks: List[ACETask]) -> Optional[ACETask]:
        """
        Retrieves all ready tasks, filters them by policy limits, sorts by priority/id deterministically,
        and schedules the top eligible candidate.
        """
        ready_tasks = DependencyAnalyzer.get_ready_tasks(tasks)
        if not ready_tasks:
            return None

        # Check global concurrency limits
        running_count = sum(1 for t in tasks if t.status in (TaskStatus.RUNNING, TaskStatus.SCHEDULED, TaskStatus.ACTIVATED))
        max_concurrency = self.policy_manager.get_policy("max_concurrency", 5)
        if running_count >= max_concurrency:
            logger.info("AdaptiveTaskScheduler: Max global concurrency reached.")
            return None

        # Check capability specific concurrency limits
        eligible = []
        for task in ready_tasks:
            cap_running = sum(1 for t in tasks if t.required_capability == task.required_capability and t.status in (TaskStatus.RUNNING, TaskStatus.SCHEDULED, TaskStatus.ACTIVATED))
            limit = self.policy_manager.get_capability_limit(task.required_capability)
            if cap_running < limit:
                eligible.append(task)

        if not eligible:
            return None

        # Deterministic sorting:
        # 1. Higher priority first
        # 2. String of task_id as tie-breaker
        eligible.sort(key=lambda t: (-t.priority, str(t.task_id)))

        selected = eligible[0]
        selected.status = TaskStatus.SCHEDULED
        return selected

    def schedule_tasks(self, ready_tasks: List[ACETask], meeting_id: Optional[uuid.UUID] = None) -> List[ACETask]:
        """
        Schedules a list of ready tasks up to concurrency limits and returns scheduled candidates.
        """
        scheduled = []
        for task in ready_tasks:
            if task.status in (TaskStatus.PENDING, TaskStatus.RETRYING):
                task.status = TaskStatus.SCHEDULED
                scheduled.append(task)
        return scheduled


class DynamicRoutingEngine:
    """
    Dynamically routes tasks to their designated operational handler callbacks or modules.
    """
    def __init__(self) -> None:
        self._registry: Dict[str, Any] = {}

    def register_handler(self, capability: str, handler: Any) -> None:
        """Associates a capability type with a processing handler."""
        self._registry[capability] = handler

    def resolve_route(self, task: ACETask) -> Any:
        """
        Resolves the processing module/handler bound to the task's required capability.
        """
        cap = task.required_capability
        if not cap:
            raise ValueError(f"Task {task.task_id} has no specified required capability.")

        handler = self._registry.get(cap)
        if not handler:
            raise ValueError(f"No handler registered for capability: {cap}")
        return handler

    def route_task(self, task: ACETask) -> str:
        """
        Resolves the target capability identifier string for routing a task.
        """
        if not task.required_capability:
            raise ValueError(f"Task {task.task_id} has no specified required capability.")
        return task.required_capability


class ConfidenceEvaluator:
    """
    Orchestration-tier confidence evaluator to assess task execution outcomes.
    """
    def __init__(self, policy_manager: Optional[PolicyManager] = None) -> None:
        self.policy_manager = policy_manager or PolicyManager()

    def evaluate(self, confidence_score: float, threshold: float = 0.70) -> bool:
        """Determines if confidence score meets threshold."""
        return confidence_score >= threshold

    def evaluate_task_confidence(self, task: ACETask, confidence_score: float) -> bool:
        """
        Determines if the confidence score meets thresholds specified by task or global policy.
        """
        custom_threshold = task.metadata.get("confidence_threshold")
        threshold = (
            custom_threshold
            if custom_threshold is not None
            else self.policy_manager.get_policy("min_confidence_threshold", 0.70)
        )
        return confidence_score >= threshold


class ExecutionMonitor:
    """
    Tracks and records state transitions, timestamps, metadata, and retry/recovery events.
    """
    def __init__(self, policy_manager: Optional[PolicyManager] = None) -> None:
        self.policy_manager = policy_manager or PolicyManager()
        self._tasks: Dict[uuid.UUID, ACETask] = {}
        self._start_times: Dict[uuid.UUID, float] = {}
        self._end_times: Dict[uuid.UUID, float] = {}

    def track_task(self, task: ACETask) -> None:
        """Adds task to the monitored set."""
        self._tasks[task.task_id] = task

    def record_start(self, task_id: uuid.UUID, capability: Optional[str] = None) -> None:
        """Records the start timestamp of a task execution."""
        self._start_times[task_id] = time.time()

    def record_completion(self, task_id: uuid.UUID, confidence_score: Optional[float] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Records completion timestamp and metadata."""
        self._end_times[task_id] = time.time()

    def record_failure(self, task_id: uuid.UUID, error_message: str) -> None:
        """Records failure timestamp."""
        self._end_times[task_id] = time.time()

    def start_task(self, task_id: uuid.UUID) -> None:
        """Marks task status as RUNNING and registers the start timestamp."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} is not under active monitor tracking.")

        task.status = TaskStatus.RUNNING
        self._start_times[task_id] = time.time()

    def complete_task(self, task_id: uuid.UUID, output_metadata: Optional[Dict[str, Any]] = None) -> None:
        """Marks task status as COMPLETED and logs runtime metrics."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} is not under active monitor tracking.")

        task.status = TaskStatus.COMPLETED
        if output_metadata:
            task.metadata.update(output_metadata)

        self._end_times[task_id] = time.time()

    def fail_task(self, task_id: uuid.UUID, error_message: str) -> None:
        """
        Registers execution failures. Increments retry counts and sets status
        to RETRYING or FAILED based on policy rules.
        """
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} is not under active monitor tracking.")

        self._end_times[task_id] = time.time()
        limit = self.policy_manager.get_policy("default_retry_limit", 3)

        if task.retry_count < limit:
            task.retry_count += 1
            task.status = TaskStatus.RETRYING
        else:
            task.status = TaskStatus.FAILED
            task.metadata["error_message"] = error_message

    def require_recovery(self, task_id: uuid.UUID, reason: str) -> None:
        """Places task in RECOVERY_REQUIRED state."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} is not under active monitor tracking.")

        task.status = TaskStatus.RECOVERY_REQUIRED
        task.metadata["recovery_reason"] = reason

    def get_duration(self, task_id: uuid.UUID) -> float:
        """Returns elapsed task runtime duration."""
        start = self._start_times.get(task_id)
        if not start:
            return 0.0
        end = self._end_times.get(task_id, time.time())
        return end - start

    def get_task(self, task_id: uuid.UUID) -> Optional[ACETask]:
        """Fetches the tracked task model."""
        return self._tasks.get(task_id)
