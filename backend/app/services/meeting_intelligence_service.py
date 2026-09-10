"""
Meeting Intelligence & Action Items Application Service (Phase 4.21)
Provides secure domain operations for retrieving and updating meeting action items,
decisions, topics, insights, summaries, facts, and hypotheses from authoritative SKW storage.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus
from app.models.knowledge_object import KnowledgeObject, KnowledgeObjectStatus
from app.models.meeting import Meeting
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.action_item import (
    ActionItemCreate,
    ActionItemPriority,
    ActionItemResponse,
    ActionItemStatus,
    ActionItemUpdate,
)
from app.schemas.meeting_intelligence import (
    DecisionResponse,
    FactResponse,
    HypothesisResponse,
    InsightResponse,
    SummaryResponse,
    SummarySection,
    TopicResponse,
)

logger = get_logger("services.meeting_intelligence")


class MeetingIntelligenceService:
    """
    Application Service orchestrating access to meeting intelligence and action items.
    Enforces tenant isolation, provenance preservation, lifecycle validation, and Redis event emission.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.meeting_repo = MeetingRepository(db)
        self.ko_repo = KnowledgeObjectRepository(db)
        self.event_bus = RedisEventBus()

    def _validate_auth(self, auth_context: Dict[str, Any], meeting: Optional[Meeting] = None) -> None:
        """Enforces authentication and tenant isolation."""
        if not auth_context or not auth_context.get("authenticated", False):
            raise ForbiddenException(message="Authentication required", code="UNAUTHORIZED")
        meeting_tenant = getattr(meeting, "tenant_id", None) if meeting else None
        if meeting_tenant:
            user_tenant = auth_context.get("tenant_id")
            if user_tenant and user_tenant != meeting_tenant:
                raise ForbiddenException(
                    message="Access denied: Cross-tenant operation forbidden",
                    code="FORBIDDEN_CROSS_TENANT",
                )

    def _map_to_action_item_response(self, ko: KnowledgeObject) -> ActionItemResponse:
        """Converts KnowledgeObject entity into ActionItemResponse DTO."""
        payload = ko.payload or {}
        provenance = ko.provenance or {}
        raw_status = payload.get("status") or ko.status or "open"
        raw_status_lower = str(raw_status).lower()

        # Map to valid ActionItemStatus
        if raw_status_lower in ("completed", "done", "validated"):
            status_enum = ActionItemStatus.COMPLETED
        elif raw_status_lower in ("cancelled", "canceled", "rejected", "deprecated"):
            status_enum = ActionItemStatus.CANCELLED
        elif raw_status_lower in ("in_progress", "active", "doing"):
            status_enum = ActionItemStatus.IN_PROGRESS
        else:
            status_enum = ActionItemStatus.OPEN

        raw_priority = payload.get("priority", "medium").lower()
        if raw_priority in ("critical", "urgent"):
            priority_enum = ActionItemPriority.CRITICAL
        elif raw_priority == "high":
            priority_enum = ActionItemPriority.HIGH
        elif raw_priority == "low":
            priority_enum = ActionItemPriority.LOW
        else:
            priority_enum = ActionItemPriority.MEDIUM

        confidence = ko.confidence if ko.confidence is not None else 1.0
        is_low_conf = confidence < 0.75
        requires_verification = payload.get("requires_verification", is_low_conf)

        source_segments = payload.get("source_segments") or provenance.get("source_segments") or []
        source_segments = [str(s) for s in source_segments]

        return ActionItemResponse(
            id=ko.id,
            meeting_id=ko.meeting_id,
            title=ko.title or ko.content[:80],
            description=ko.content,
            status=status_enum,
            priority=priority_enum,
            assignee=payload.get("assignee") or payload.get("owner"),
            due_date=payload.get("due_date"),
            confidence=confidence,
            is_low_confidence=is_low_conf,
            requires_verification=requires_verification,
            source_segments=source_segments,
            version=ko.version,
            provenance=provenance,
            created_at=ko.created_at,
            updated_at=ko.updated_at,
        )

    # -------------------------------------------------------------------------
    # Action Items
    # -------------------------------------------------------------------------

    async def list_action_items(
        self,
        meeting_id: uuid.UUID,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        min_confidence: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[ActionItemResponse], int]:
        """Lists action items for a meeting with filtering and pagination."""
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, meeting)

        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id == meeting_id,
            KnowledgeObject.object_type == "action_item",
        )

        if min_confidence is not None:
            query = query.where(KnowledgeObject.confidence >= min_confidence)

        # Count total
        count_stmt = select(func.count()).select_from(query.subquery())
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar() or 0

        # Execute pagination
        query = query.order_by(KnowledgeObject.created_at.desc()).offset(offset).limit(limit)
        items_res = await self.db.execute(query)
        kos = list(items_res.scalars().all())

        results = [self._map_to_action_item_response(ko) for ko in kos]

        # Apply in-memory payload filters if specified
        if status:
            norm_status = status.strip().lower()
            results = [r for r in results if r.status.value == norm_status]
        if priority:
            norm_priority = priority.strip().lower()
            results = [r for r in results if r.priority.value == norm_priority]
        if assignee:
            norm_assignee = assignee.strip().lower()
            results = [r for r in results if r.assignee and norm_assignee in r.assignee.lower()]

        return results, total

    async def get_action_item(
        self,
        action_item_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> ActionItemResponse:
        """Retrieves a single action item by ID."""
        ko = await self.ko_repo.get_by_id(action_item_id)
        if not ko or ko.object_type != "action_item":
            raise NotFoundException(
                message=f"Action item '{action_item_id}' not found",
                code="ACTION_ITEM_NOT_FOUND",
            )

        meeting = await self.meeting_repo.get_by_id(ko.meeting_id)
        self._validate_auth(auth_context, meeting)

        return self._map_to_action_item_response(ko)

    async def create_action_item(
        self,
        meeting_id: uuid.UUID,
        payload: ActionItemCreate,
        auth_context: Dict[str, Any],
    ) -> ActionItemResponse:
        """Creates a new user-confirmed action item in SKW."""
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        self._validate_auth(auth_context, meeting)

        user_id = auth_context.get("user_id", "system")
        correlation_id = payload.correlation_id or str(uuid.uuid4())

        item_payload = {
            "status": payload.status.value,
            "priority": payload.priority.value,
            "assignee": payload.assignee,
            "due_date": payload.due_date,
            "source_segments": payload.source_segment_ids or [],
        }

        provenance = {
            "producing_module": "ActionItemService",
            "source": "user_creation",
            "created_by": user_id,
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        ko = KnowledgeObject(
            meeting_id=meeting_id,
            object_type="action_item",
            source_module="ActionItemService",
            title=payload.title,
            content=payload.description or payload.title,
            confidence=1.0,
            status=KnowledgeObjectStatus.ACTIVE.value,
            version=1,
            payload=item_payload,
            provenance=provenance,
        )

        created_ko = await self.ko_repo.create(ko)
        await self.db.commit()
        await self.db.refresh(created_ko)

        # Emit Redis event
        await self.event_bus.publish(
            "ActionItemUpdated",
            {
                "action_item_id": str(created_ko.id),
                "meeting_id": str(meeting_id),
                "tenant_id": meeting.tenant_id,
                "status": payload.status.value,
                "correlation_id": correlation_id,
            },
        )

        return self._map_to_action_item_response(created_ko)

    async def update_action_item(
        self,
        action_item_id: uuid.UUID,
        payload: ActionItemUpdate,
        auth_context: Dict[str, Any],
    ) -> ActionItemResponse:
        """Updates an action item with version incrementing and provenance preservation."""
        ko = await self.ko_repo.get_by_id(action_item_id)
        if not ko or ko.object_type != "action_item":
            raise NotFoundException(
                message=f"Action item '{action_item_id}' not found",
                code="ACTION_ITEM_NOT_FOUND",
            )

        meeting = await self.meeting_repo.get_by_id(ko.meeting_id)
        self._validate_auth(auth_context, meeting)

        user_id = auth_context.get("user_id", "system")
        current_payload = dict(ko.payload or {})
        current_prov = dict(ko.provenance or {})

        # Apply updates
        if payload.title is not None:
            ko.title = payload.title
        if payload.description is not None:
            ko.content = payload.description
        if payload.status is not None:
            current_payload["status"] = payload.status.value
            if payload.status == ActionItemStatus.COMPLETED:
                ko.status = KnowledgeObjectStatus.VALIDATED.value
            elif payload.status == ActionItemStatus.CANCELLED:
                ko.status = KnowledgeObjectStatus.REJECTED.value
            else:
                ko.status = KnowledgeObjectStatus.ACTIVE.value
        if payload.priority is not None:
            current_payload["priority"] = payload.priority.value
        if payload.assignee is not None:
            current_payload["assignee"] = payload.assignee
        if payload.due_date is not None:
            current_payload["due_date"] = payload.due_date
        if payload.confidence is not None:
            ko.confidence = payload.confidence

        # Increment version & update audit lineage
        ko.version += 1
        current_prov["last_modified_by"] = user_id
        current_prov["last_modified_at"] = datetime.now(timezone.utc).isoformat()
        current_prov["correlation_id"] = payload.correlation_id or current_prov.get("correlation_id")

        ko.payload = current_payload
        ko.provenance = current_prov

        await self.db.commit()
        await self.db.refresh(ko)

        # Emit Redis event
        await self.event_bus.publish(
            "ActionItemUpdated",
            {
                "action_item_id": str(ko.id),
                "meeting_id": str(ko.meeting_id),
                "tenant_id": meeting.tenant_id if meeting else None,
                "status": current_payload.get("status"),
                "version": ko.version,
                "correlation_id": payload.correlation_id,
            },
        )

        if ko.confidence is not None and ko.confidence < 0.75:
            await self.event_bus.publish(
                "ActionItemVerificationRequired",
                {
                    "action_item_id": str(ko.id),
                    "meeting_id": str(ko.meeting_id),
                    "confidence": ko.confidence,
                    "correlation_id": payload.correlation_id,
                },
            )

        return self._map_to_action_item_response(ko)

    async def complete_action_item(
        self,
        action_item_id: uuid.UUID,
        auth_context: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> ActionItemResponse:
        """Idempotently marks an action item as completed."""
        ko = await self.ko_repo.get_by_id(action_item_id)
        if not ko or ko.object_type != "action_item":
            raise NotFoundException(
                message=f"Action item '{action_item_id}' not found",
                code="ACTION_ITEM_NOT_FOUND",
            )

        meeting = await self.meeting_repo.get_by_id(ko.meeting_id)
        self._validate_auth(auth_context, meeting)

        current_payload = dict(ko.payload or {})
        if current_payload.get("status") == ActionItemStatus.COMPLETED.value:
            # Already completed (idempotent)
            return self._map_to_action_item_response(ko)

        current_payload["status"] = ActionItemStatus.COMPLETED.value
        current_payload["completed_at"] = datetime.now(timezone.utc).isoformat()
        ko.payload = current_payload
        ko.status = KnowledgeObjectStatus.VALIDATED.value
        ko.version += 1

        await self.db.commit()
        await self.db.refresh(ko)

        await self.event_bus.publish(
            "ActionItemCompleted",
            {
                "action_item_id": str(ko.id),
                "meeting_id": str(ko.meeting_id),
                "tenant_id": meeting.tenant_id if meeting else None,
                "version": ko.version,
                "correlation_id": correlation_id,
            },
        )

        return self._map_to_action_item_response(ko)

    async def cancel_action_item(
        self,
        action_item_id: uuid.UUID,
        auth_context: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> ActionItemResponse:
        """Idempotently marks an action item as cancelled."""
        ko = await self.ko_repo.get_by_id(action_item_id)
        if not ko or ko.object_type != "action_item":
            raise NotFoundException(
                message=f"Action item '{action_item_id}' not found",
                code="ACTION_ITEM_NOT_FOUND",
            )

        meeting = await self.meeting_repo.get_by_id(ko.meeting_id)
        self._validate_auth(auth_context, meeting)

        current_payload = dict(ko.payload or {})
        if current_payload.get("status") == ActionItemStatus.CANCELLED.value:
            # Already cancelled (idempotent)
            return self._map_to_action_item_response(ko)

        current_payload["status"] = ActionItemStatus.CANCELLED.value
        current_payload["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        ko.payload = current_payload
        ko.status = KnowledgeObjectStatus.REJECTED.value
        ko.version += 1

        await self.db.commit()
        await self.db.refresh(ko)

        await self.event_bus.publish(
            "ActionItemCancelled",
            {
                "action_item_id": str(ko.id),
                "meeting_id": str(ko.meeting_id),
                "tenant_id": meeting.tenant_id if meeting else None,
                "version": ko.version,
                "correlation_id": correlation_id,
            },
        )

        return self._map_to_action_item_response(ko)

    # -------------------------------------------------------------------------
    # Meeting Intelligence: Decisions, Topics, Insights, Summaries, Facts, Hypotheses
    # -------------------------------------------------------------------------

    async def list_decisions(
        self,
        meeting_id: uuid.UUID,
        min_confidence: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[DecisionResponse], int]:
        """Lists recorded meeting decisions."""
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, meeting)

        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id == meeting_id,
            KnowledgeObject.object_type == "decision",
        )
        if min_confidence is not None:
            query = query.where(KnowledgeObject.confidence >= min_confidence)

        count_stmt = select(func.count()).select_from(query.subquery())
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar() or 0

        query = query.order_by(KnowledgeObject.created_at.desc()).offset(offset).limit(limit)
        items_res = await self.db.execute(query)
        kos = list(items_res.scalars().all())

        results = []
        for ko in kos:
            payload = ko.payload or {}
            confidence = ko.confidence if ko.confidence is not None else 1.0
            is_low = confidence < 0.75
            results.append(
                DecisionResponse(
                    id=ko.id,
                    meeting_id=ko.meeting_id,
                    title=ko.title,
                    content=ko.content,
                    status=ko.status,
                    confidence=confidence,
                    is_low_confidence=is_low,
                    requires_verification=payload.get("requires_verification", is_low),
                    alternatives=payload.get("alternatives", []),
                    impact=payload.get("impact"),
                    rationales=payload.get("rationales", []),
                    version=ko.version,
                    provenance=ko.provenance,
                    created_at=ko.created_at,
                    updated_at=ko.updated_at,
                )
            )
        return results, total

    async def list_topics(
        self,
        meeting_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[TopicResponse], int]:
        """Lists extracted meeting topics."""
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, meeting)

        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id == meeting_id,
            KnowledgeObject.object_type == "topic",
        )

        count_stmt = select(func.count()).select_from(query.subquery())
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar() or 0

        query = query.order_by(KnowledgeObject.created_at.desc()).offset(offset).limit(limit)
        items_res = await self.db.execute(query)
        kos = list(items_res.scalars().all())

        results = []
        for ko in kos:
            payload = ko.payload or {}
            results.append(
                TopicResponse(
                    id=ko.id,
                    meeting_id=ko.meeting_id,
                    title=ko.title or ko.content[:60],
                    description=ko.content,
                    keywords=payload.get("keywords", []),
                    start_time_ms=payload.get("start_time_ms"),
                    end_time_ms=payload.get("end_time_ms"),
                    confidence=ko.confidence,
                    version=ko.version,
                    provenance=ko.provenance,
                    created_at=ko.created_at,
                    updated_at=ko.updated_at,
                )
            )
        return results, total

    async def list_insights(
        self,
        meeting_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[InsightResponse], int]:
        """Lists transcript and conversation insights for a meeting."""
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, meeting)

        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id == meeting_id,
            KnowledgeObject.object_type.in_(["transcript_insight", "insight", "context_insight"]),
        )

        count_stmt = select(func.count()).select_from(query.subquery())
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar() or 0

        query = query.order_by(KnowledgeObject.created_at.desc()).offset(offset).limit(limit)
        items_res = await self.db.execute(query)
        kos = list(items_res.scalars().all())

        results = []
        for ko in kos:
            payload = ko.payload or {}
            confidence = ko.confidence if ko.confidence is not None else 1.0
            is_low = confidence < 0.75
            results.append(
                InsightResponse(
                    id=ko.id,
                    meeting_id=ko.meeting_id,
                    insight_type=payload.get("insight_type", ko.object_type),
                    title=ko.title,
                    content=ko.content,
                    sentiment=payload.get("sentiment"),
                    confidence=confidence,
                    is_low_confidence=is_low,
                    requires_verification=payload.get("requires_verification", is_low),
                    version=ko.version,
                    provenance=ko.provenance,
                    created_at=ko.created_at,
                    updated_at=ko.updated_at,
                )
            )
        return results, total

    async def get_meeting_summary(
        self,
        meeting_id: uuid.UUID,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> SummaryResponse:
        """Retrieves authoritative structured executive summary for a meeting."""
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, meeting)

        stmt = (
            select(KnowledgeObject)
            .where(
                KnowledgeObject.meeting_id == meeting_id,
                KnowledgeObject.object_type == "summary",
            )
            .order_by(KnowledgeObject.created_at.desc())
        )
        res = await self.db.execute(stmt)
        ko = res.scalars().first()

        if not ko:
            # Fallback placeholder if summary is not yet synthesized
            return SummaryResponse(
                id=uuid.uuid4(),
                meeting_id=meeting_id,
                title="Executive Summary",
                content=meeting.description or "Meeting summary is pending generation.",
                sections=[],
                key_takeaways=[],
                confidence=1.0,
                version=1,
                provenance={"producing_module": "MeetingSummaryFallback"},
                created_at=meeting.created_at or datetime.now(timezone.utc),
                updated_at=meeting.updated_at,
            )

        payload = ko.payload or {}
        raw_sections = payload.get("sections", [])
        sections = [
            SummarySection(
                heading=s.get("heading", "Section"),
                content=s.get("content", ""),
                key_points=s.get("key_points", []),
            )
            for s in raw_sections
            if isinstance(s, dict)
        ]

        return SummaryResponse(
            id=ko.id,
            meeting_id=ko.meeting_id,
            title=ko.title or "Executive Summary",
            content=ko.content,
            sections=sections,
            key_takeaways=payload.get("key_takeaways", []),
            confidence=ko.confidence,
            version=ko.version,
            provenance=ko.provenance,
            created_at=ko.created_at,
            updated_at=ko.updated_at,
        )

    async def list_facts(
        self,
        meeting_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[FactResponse], int]:
        """Lists extracted or verified facts for a meeting."""
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, meeting)

        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id == meeting_id,
            KnowledgeObject.object_type == "fact",
        )

        count_stmt = select(func.count()).select_from(query.subquery())
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar() or 0

        query = query.order_by(KnowledgeObject.created_at.desc()).offset(offset).limit(limit)
        items_res = await self.db.execute(query)
        kos = list(items_res.scalars().all())

        results = []
        for ko in kos:
            payload = ko.payload or {}
            results.append(
                FactResponse(
                    id=ko.id,
                    meeting_id=ko.meeting_id,
                    statement=ko.content,
                    category=payload.get("category"),
                    confidence=ko.confidence,
                    is_verified=payload.get("is_verified", False) or ko.status == KnowledgeObjectStatus.VALIDATED.value,
                    version=ko.version,
                    provenance=ko.provenance,
                    created_at=ko.created_at,
                    updated_at=ko.updated_at,
                )
            )
        return results, total

    async def list_hypotheses(
        self,
        meeting_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[HypothesisResponse], int]:
        """Lists working hypotheses and assumptions for a meeting."""
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, meeting)

        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id == meeting_id,
            KnowledgeObject.object_type == "hypothesis",
        )

        count_stmt = select(func.count()).select_from(query.subquery())
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar() or 0

        query = query.order_by(KnowledgeObject.created_at.desc()).offset(offset).limit(limit)
        items_res = await self.db.execute(query)
        kos = list(items_res.scalars().all())

        results = []
        for ko in kos:
            payload = ko.payload or {}
            results.append(
                HypothesisResponse(
                    id=ko.id,
                    meeting_id=ko.meeting_id,
                    statement=ko.content,
                    supporting_evidence=payload.get("supporting_evidence", []),
                    confidence=ko.confidence,
                    status=ko.status,
                    version=ko.version,
                    provenance=ko.provenance,
                    created_at=ko.created_at,
                    updated_at=ko.updated_at,
                )
            )
        return results, total
