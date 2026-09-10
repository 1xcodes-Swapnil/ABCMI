"""
Event-Driven ACE Orchestration Engine (Phase 4.11B)
Integrates ACE Core (Task Planner, Dependency Analyzer, Scheduler, Routing Engine,
Confidence Evaluator, Execution Monitor, Policy Manager) with Adaptive Blackboard,
Redis Event Bus, SKW Client Boundary, Failure Recovery, and Verification Flow.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus, get_event_bus
from app.orchestration.ace_boundary import ACEAdaptiveBlackboardAdapter, ACERequest
from app.orchestration.ace_core import (
    ACETask,
    AdaptiveTaskScheduler,
    ConfidenceEvaluator,
    DependencyAnalyzer,
    DynamicRoutingEngine,
    ExecutionMonitor,
    PolicyManager,
    TaskPlanner,
    TaskStatus,
)
from app.orchestration.blackboard_context import BlackboardContext
from app.orchestration.events import (
    ContextUpdatedEvent,
    ProcessingCompletedEvent,
    ProcessingRequestedEvent,
    RecoveryTriggeredEvent,
    RetryRequestedEvent,
    TaskActivatedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskPlannedEvent,
    TaskScheduledEvent,
    TaskStartedEvent,
)
from app.orchestration.module_runner import AIModuleRunner
from app.orchestration.recovery_manager import RecoveryManager

logger = get_logger("orchestration.ace_engine")


class ACEOrchestrator:
    """
    Event-driven Adaptive Collaboration Engine (ACE) Orchestrator.
    Manages end-to-end meeting intelligence pipeline execution:
    Request -> Context -> Planning -> Dependency Analysis -> Scheduling ->
    Blackboard Sync -> Event Activation -> Module Execution -> Confidence Evaluation ->
    Verification -> Recovery / Retry -> SKW Storage -> Completion.
    """

    def __init__(
        self,
        event_bus: Optional[RedisEventBus] = None,
        blackboard_adapter: Optional[ACEAdaptiveBlackboardAdapter] = None,
        module_runner: Optional[AIModuleRunner] = None,
        policy_manager: Optional[PolicyManager] = None,
    ) -> None:
        self.event_bus = event_bus or get_event_bus()
        self.blackboard_adapter = blackboard_adapter
        self.module_runner = module_runner or AIModuleRunner()
        self.policy_manager = policy_manager or PolicyManager()

        self.planner = TaskPlanner(policy_manager=self.policy_manager)
        self.dependency_analyzer = DependencyAnalyzer()
        self.scheduler = AdaptiveTaskScheduler(policy_manager=self.policy_manager)
        self.routing_engine = DynamicRoutingEngine()
        self.confidence_evaluator = ConfidenceEvaluator(policy_manager=self.policy_manager)
        self.execution_monitor = ExecutionMonitor(policy_manager=self.policy_manager)
        self.recovery_manager = RecoveryManager(policy_manager=self.policy_manager)

        self.blackboards: Dict[uuid.UUID, BlackboardContext] = {}

    def get_or_create_blackboard(self, meeting_id: uuid.UUID) -> BlackboardContext:
        """Obtain or initialize the in-memory Blackboard context for a meeting."""
        if meeting_id not in self.blackboards:
            self.blackboards[meeting_id] = BlackboardContext(meeting_id=meeting_id)
        return self.blackboards[meeting_id]

    async def _publish_event(self, channel: str, event: Any) -> None:
        """Helper to publish orchestration event to Redis bus safely."""
        try:
            await self.event_bus.publish(channel, event)
        except Exception as e:
            logger.warning(f"Failed to publish event {type(event).__name__} to channel {channel}: {e}")

    async def process_request(
        self,
        request: ACERequest,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> BlackboardContext:
        """
        Main entry point for meeting processing request execution.
        Executes pipeline: Request -> Context -> Plan -> Dependencies -> Schedule -> Modules -> Complete.
        """
        meeting_id = request.meeting_id
        request_id = request.request_id
        correlation_id = request.correlation_id or str(uuid.uuid4())

        blackboard = self.get_or_create_blackboard(meeting_id)
        blackboard.execution_state["status"] = "PROCESSING"
        blackboard.execution_state["request_id"] = str(request_id)
        blackboard.execution_state["start_time"] = datetime.utcnow().isoformat()

        channel = f"events:meetings:{meeting_id}:orchestration"

        # 1. Emit Processing Requested Event
        req_event = ProcessingRequestedEvent(
            request_id=request_id,
            meeting_id=meeting_id,
            correlation_id=correlation_id,
            enable_analytics=request.enable_analytics,
            enable_memory=request.enable_memory,
        )
        await self._publish_event(channel, req_event)

        # 2. Retrieve Context via Blackboard Adapter if available
        context_items = []
        if self.blackboard_adapter and auth_context:
            try:
                context_items = await self.blackboard_adapter.request_context(
                    meeting_id=meeting_id,
                    auth_context=auth_context,
                    correlation_id=correlation_id,
                )
                logger.info(f"Retrieved {len(context_items)} context items from SKW for meeting {meeting_id}")
                ctx_event = ContextUpdatedEvent(
                    request_id=request_id,
                    meeting_id=meeting_id,
                    correlation_id=correlation_id,
                    context_type="SKW_PREREQUISITE_KNOWLEDGE",
                    metadata={"item_count": len(context_items)},
                )
                await self._publish_event(channel, ctx_event)
            except Exception as ex:
                logger.warning(f"Failed to fetch prior SKW context for meeting {meeting_id}: {ex}")

        # 3. Task Planning
        plan = self.planner.plan_request(request)
        self.dependency_analyzer.validate_plan(plan)

        for task in plan.tasks:
            blackboard.upsert_task(task)

        plan_event = TaskPlannedEvent(
            request_id=request_id,
            meeting_id=meeting_id,
            correlation_id=correlation_id,
            total_tasks=len(plan.tasks),
            metadata={"planner_id": plan.planner_id},
        )
        await self._publish_event(channel, plan_event)

        # 4. Enter Event-Driven Scheduling Loop
        await self.run_scheduling_loop(
            meeting_id=meeting_id,
            request_id=request_id,
            correlation_id=correlation_id,
            auth_context=auth_context,
        )

        return blackboard

    async def run_scheduling_loop(
        self,
        meeting_id: uuid.UUID,
        request_id: uuid.UUID,
        correlation_id: str,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Continuously schedules and executes ready tasks until no further tasks can run.
        """
        blackboard = self.get_or_create_blackboard(meeting_id)
        channel = f"events:meetings:{meeting_id}:orchestration"

        while True:
            all_tasks = blackboard.list_tasks()
            ready_tasks = self.dependency_analyzer.get_ready_tasks(all_tasks)

            if not ready_tasks:
                # Check if pipeline is complete or stalled/failed
                pending_tasks = [t for t in all_tasks if t.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED, TaskStatus.RUNNING, TaskStatus.RETRYING)]
                failed_tasks = [t for t in all_tasks if t.status in (TaskStatus.FAILED, TaskStatus.RECOVERY_REQUIRED)]

                if not pending_tasks:
                    if failed_tasks:
                        blackboard.execution_state["status"] = "FAILED"
                    elif blackboard.execution_state.get("status") != "COMPLETED":
                        blackboard.execution_state["status"] = "COMPLETED"
                        blackboard.execution_state["completed_at"] = datetime.utcnow().isoformat()
                        
                        # Calculate total pipeline duration
                        start_time_str = blackboard.execution_state.get("start_time")
                        duration_sec = 0.0
                        if start_time_str:
                            try:
                                start_dt = datetime.fromisoformat(start_time_str)
                                duration_sec = (datetime.utcnow() - start_dt).total_seconds()
                            except Exception:
                                pass

                        comp_event = ProcessingCompletedEvent(
                            request_id=request_id,
                            meeting_id=meeting_id,
                            correlation_id=correlation_id,
                            completed_task_count=len(all_tasks),
                            duration_seconds=duration_sec,
                        )
                        await self._publish_event(channel, comp_event)
                        logger.info(f"Processing request {request_id} completed successfully for meeting {meeting_id}")
                break

            # Schedule tasks respecting concurrency limits
            scheduled = self.scheduler.schedule_tasks(ready_tasks, meeting_id=meeting_id)
            if not scheduled:
                break

            for task in scheduled:
                blackboard.record_task_scheduled(task.task_id)
                sched_event = TaskScheduledEvent(
                    request_id=request_id,
                    meeting_id=meeting_id,
                    task_id=task.task_id,
                    task_type=task.task_type,
                    required_capability=task.required_capability,
                    priority=task.priority,
                    correlation_id=correlation_id,
                )
                await self._publish_event(channel, sched_event)

                # Execute task asynchronously
                await self._execute_scheduled_task(
                    blackboard=blackboard,
                    task=task,
                    request_id=request_id,
                    correlation_id=correlation_id,
                    auth_context=auth_context,
                )

    async def _execute_scheduled_task(
        self,
        blackboard: BlackboardContext,
        task: ACETask,
        request_id: uuid.UUID,
        correlation_id: str,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Route capability, activate task, execute AI module, and handle output/failures.
        """
        meeting_id = blackboard.meeting_id
        channel = f"events:meetings:{meeting_id}:orchestration"

        # Resolve capability route
        target_capability = self.routing_engine.route_task(task)
        blackboard.record_task_activated(task.task_id)

        act_event = TaskActivatedEvent(
            request_id=request_id,
            meeting_id=meeting_id,
            task_id=task.task_id,
            task_type=task.task_type,
            required_capability=target_capability,
            correlation_id=correlation_id,
        )
        await self._publish_event(channel, act_event)

        start_event = TaskStartedEvent(
            request_id=request_id,
            meeting_id=meeting_id,
            task_id=task.task_id,
            task_type=task.task_type,
            required_capability=target_capability,
            correlation_id=correlation_id,
        )
        await self._publish_event(channel, start_event)

        self.execution_monitor.record_start(task.task_id, capability=target_capability)

        try:
            # Module execution call
            output = await self.module_runner.execute_task(
                capability=target_capability,
                task_id=task.task_id,
                meeting_id=meeting_id,
                request_id=request_id,
                input_data=task.input_data,
                correlation_id=correlation_id,
            )

            confidence_score = output.get("confidence_score", 0.90)
            result_data = output.get("result_data", {})

            # Confidence Evaluation & Verification Flow
            min_thresh = self.policy_manager.get_policy("min_confidence_threshold", 0.70)
            is_valid_confidence = self.confidence_evaluator.evaluate_task_confidence(
                task, confidence_score
            )

            if not is_valid_confidence:
                logger.warning(
                    f"Task {task.task_id} output confidence ({confidence_score}) below threshold ({min_thresh}). "
                    f"Triggering verification engine."
                )
                verif_output = await self.module_runner.execute_task(
                    capability="verification_engine",
                    task_id=uuid.uuid4(),
                    meeting_id=meeting_id,
                    request_id=request_id,
                    input_data={"target_task_id": str(task.task_id), "unverified_data": result_data},
                    correlation_id=correlation_id,
                )
                verif_passed = verif_output.get("result_data", {}).get("verification_passed", False)
                if not verif_passed:
                    raise ValueError(f"Verification engine rejected output for task {task.task_id}")
                logger.info(f"Verification passed for low-confidence task {task.task_id}")

            # Mark task completed
            blackboard.record_task_completed(task.task_id, result_data=result_data)
            self.execution_monitor.record_completion(
                task.task_id,
                confidence_score=confidence_score,
                metadata=result_data,
            )

            comp_event = TaskCompletedEvent(
                request_id=request_id,
                meeting_id=meeting_id,
                task_id=task.task_id,
                task_type=task.task_type,
                required_capability=target_capability,
                confidence_score=confidence_score,
                result_data=result_data,
                correlation_id=correlation_id,
            )
            await self._publish_event(channel, comp_event)

            # Store Knowledge Memory output to SKW if applicable
            if target_capability == "knowledge_memory" and self.blackboard_adapter and auth_context:
                try:
                    stored_obj = await self.blackboard_adapter.store_knowledge_object(
                        meeting_id=meeting_id,
                        object_type=result_data.get("object_type", "summary"),
                        content=str(result_data.get("canonical_stored", "Meeting processing result summary")),
                        source_module="ACEOrchestrator",
                        confidence_score=confidence_score,
                        auth_context=auth_context,
                        correlation_id=correlation_id,
                    )
                    logger.info(f"Stored final knowledge object {stored_obj.get('knowledge_id')} in SKW")
                except Exception as ex:
                    logger.warning(f"Failed to persist final Knowledge Object to SKW: {ex}")

        except Exception as ex:
            error_msg = str(ex)
            logger.error(f"Task {task.task_id} failed: {error_msg}")
            self.execution_monitor.record_failure(task.task_id, error_message=error_msg)

            decision = self.recovery_manager.evaluate_task_failure(
                task=task,
                error_message=error_msg,
                correlation_id=correlation_id,
            )

            if decision.action == "RETRY":
                blackboard.record_task_retrying(task.task_id, retry_count=decision.retry_count)
                retry_event = RetryRequestedEvent(
                    request_id=request_id,
                    meeting_id=meeting_id,
                    task_id=task.task_id,
                    task_type=task.task_type,
                    required_capability=target_capability,
                    retry_count=decision.retry_count,
                    max_retries=decision.max_retries,
                    correlation_id=correlation_id,
                    metadata=decision.error_details,
                )
                await self._publish_event(channel, retry_event)
            else:
                blackboard.record_task_failed(task.task_id, error_message=error_msg)
                blackboard.execution_state["status"] = "FAILED"

                fail_event = TaskFailedEvent(
                    request_id=request_id,
                    meeting_id=meeting_id,
                    task_id=task.task_id,
                    task_type=task.task_type,
                    required_capability=target_capability,
                    error_message=error_msg,
                    correlation_id=correlation_id,
                )
                await self._publish_event(channel, fail_event)

                rec_event = RecoveryTriggeredEvent(
                    request_id=request_id,
                    meeting_id=meeting_id,
                    task_id=task.task_id,
                    task_type=task.task_type,
                    required_capability=target_capability,
                    reason=decision.reason,
                    failure_details=decision.error_details,
                    correlation_id=correlation_id,
                )
                await self._publish_event(channel, rec_event)
