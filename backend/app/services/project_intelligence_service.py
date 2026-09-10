"""
Project & Cross-Meeting Intelligence Application Service (Phase 4.22)
Provides domain operations for project workspaces, meeting grouping, cross-meeting aggregation,
recurring topic detection, historical timelines, and related-meeting discovery.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus
from app.models.knowledge_object import KnowledgeObject, KnowledgeObjectStatus
from app.models.meeting import Meeting
from app.models.project import Project, ProjectMeeting
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.project_repo import ProjectMeetingRepository, ProjectRepository
from app.schemas.action_item import ActionItemPriority, ActionItemResponse, ActionItemStatus
from app.schemas.project import (
    CrossMeetingActionItemsSummary,
    CrossMeetingDecisionItem,
    CrossMeetingDecisionsResponse,
    CrossMeetingInsightItem,
    CrossMeetingInsightsResponse,
    MeetingTimelineEntry,
    ProjectCreate,
    ProjectHistoricalContextResponse,
    ProjectMeetingResponse,
    ProjectResponse,
    ProjectStatus,
    ProjectSummaryResponse,
    ProjectUpdate,
    RecurringTopicItem,
    RecurringTopicsResponse,
    RelatedMeetingItem,
    RelatedMeetingsResponse,
)

logger = get_logger("services.project_intelligence")


class ProjectIntelligenceService:
    """
    Application Service orchestrating project workspaces and cross-meeting intelligence.
    Enforces tenant/project isolation, provenance preservation, and Redis event emission.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.project_meeting_repo = ProjectMeetingRepository(db)
        self.meeting_repo = MeetingRepository(db)
        self.ko_repo = KnowledgeObjectRepository(db)
        self.event_bus = RedisEventBus()

    def _validate_auth(self, auth_context: Dict[str, Any], tenant_id: Optional[str] = None) -> None:
        """Validates that caller is authenticated and enforces tenant isolation."""
        if not auth_context or not auth_context.get("authenticated", False):
            raise ForbiddenException(message="Authentication required", code="UNAUTHORIZED")
        if tenant_id:
            user_tenant = auth_context.get("tenant_id")
            if user_tenant and user_tenant != tenant_id:
                raise ForbiddenException(
                    message="Access denied: Cross-tenant operation forbidden",
                    code="FORBIDDEN_CROSS_TENANT",
                )

    def _map_to_project_response(self, project: Project) -> ProjectResponse:
        """Converts Project ORM entity to ProjectResponse DTO."""
        meeting_count = len(project.project_meetings) if project.project_meetings is not None else 0
        raw_status = project.status.lower() if project.status else "active"
        if raw_status == "archived":
            status_enum = ProjectStatus.ARCHIVED
        elif raw_status == "completed":
            status_enum = ProjectStatus.COMPLETED
        else:
            status_enum = ProjectStatus.ACTIVE

        return ProjectResponse(
            id=project.id,
            tenant_id=project.tenant_id,
            name=project.name,
            description=project.description,
            status=status_enum,
            created_by=project.created_by,
            meeting_count=meeting_count,
            settings=project.settings or {},
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    # -------------------------------------------------------------------------
    # Project CRUD
    # -------------------------------------------------------------------------

    async def create_project(
        self,
        payload: ProjectCreate,
        auth_context: Dict[str, Any],
    ) -> ProjectResponse:
        """Creates a new project within caller's tenant."""
        self._validate_auth(auth_context)
        tenant_id = auth_context.get("tenant_id", "default")
        user_id = auth_context.get("user_id", "system")

        project = Project(
            name=payload.name,
            description=payload.description,
            tenant_id=tenant_id,
            status=payload.status.value,
            created_by=user_id,
            settings=payload.settings or {},
        )
        created = await self.project_repo.create(project)
        await self.db.commit()
        await self.db.refresh(created)

        # Emit Redis event
        await self.event_bus.publish(
            "ProjectCreated",
            {
                "project_id": str(created.id),
                "tenant_id": tenant_id,
                "name": created.name,
                "created_by": user_id,
            },
        )

        return self._map_to_project_response(created)

    async def list_projects(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[ProjectResponse], int]:
        """Lists projects for caller's tenant."""
        if auth_context:
            self._validate_auth(auth_context)
            tenant_id = auth_context.get("tenant_id", "default")
        else:
            tenant_id = "default"

        projects, total = await self.project_repo.list_by_tenant(
            tenant_id=tenant_id,
            status=status,
            skip=offset,
            limit=limit,
        )
        return [self._map_to_project_response(p) for p in projects], total

    async def get_project(
        self,
        project_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> ProjectResponse:
        """Retrieves a single project by ID."""
        project = await self.project_repo.get_with_meetings(project_id)
        if not project:
            raise NotFoundException(message=f"Project '{project_id}' not found", code="PROJECT_NOT_FOUND")

        self._validate_auth(auth_context, project.tenant_id)
        return self._map_to_project_response(project)

    async def update_project(
        self,
        project_id: uuid.UUID,
        payload: ProjectUpdate,
        auth_context: Dict[str, Any],
    ) -> ProjectResponse:
        """Updates project details."""
        project = await self.project_repo.get_with_meetings(project_id)
        if not project:
            raise NotFoundException(message=f"Project '{project_id}' not found", code="PROJECT_NOT_FOUND")

        self._validate_auth(auth_context, project.tenant_id)

        if payload.name is not None:
            project.name = payload.name
        if payload.description is not None:
            project.description = payload.description
        if payload.status is not None:
            project.status = payload.status.value
        if payload.settings is not None:
            project.settings = payload.settings

        await self.db.commit()
        await self.db.refresh(project)

        await self.event_bus.publish(
            "ProjectUpdated",
            {
                "project_id": str(project.id),
                "tenant_id": project.tenant_id,
                "name": project.name,
                "status": project.status,
            },
        )

        return self._map_to_project_response(project)

    async def delete_project(
        self,
        project_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> bool:
        """Deletes a project workspace."""
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundException(message=f"Project '{project_id}' not found", code="PROJECT_NOT_FOUND")

        self._validate_auth(auth_context, project.tenant_id)
        tenant_id = project.tenant_id

        await self.project_repo.delete(project_id)
        await self.db.commit()

        await self.event_bus.publish(
            "ProjectDeleted",
            {
                "project_id": str(project_id),
                "tenant_id": tenant_id,
            },
        )
        return True

    # -------------------------------------------------------------------------
    # Meeting-Project Associations
    # -------------------------------------------------------------------------

    async def associate_meeting(
        self,
        project_id: uuid.UUID,
        meeting_id: uuid.UUID,
        notes: Optional[str],
        auth_context: Dict[str, Any],
    ) -> ProjectMeetingResponse:
        """Associates a meeting with a project (idempotent)."""
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundException(message=f"Project '{project_id}' not found", code="PROJECT_NOT_FOUND")

        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        self._validate_auth(auth_context, project.tenant_id)

        # Enforce cross-tenant isolation between project and meeting
        if meeting.tenant_id and meeting.tenant_id != project.tenant_id:
            raise ForbiddenException(
                message="Cannot associate meeting with project: Cross-tenant mismatch",
                code="FORBIDDEN_CROSS_TENANT",
            )

        # Check existing association (Idempotency)
        existing = await self.project_meeting_repo.get_association(project_id, meeting_id)
        if existing:
            return ProjectMeetingResponse(
                id=existing.id,
                project_id=existing.project_id,
                meeting_id=existing.meeting_id,
                meeting_title=meeting.title,
                meeting_status=meeting.status,
                meeting_start_time=meeting.actual_start or meeting.scheduled_start,
                added_by=existing.added_by,
                notes=existing.notes,
                created_at=existing.created_at,
            )

        user_id = auth_context.get("user_id", "system")
        assoc = ProjectMeeting(
            project_id=project_id,
            meeting_id=meeting_id,
            tenant_id=project.tenant_id,
            added_by=user_id,
            notes=notes,
        )
        created = await self.project_meeting_repo.create(assoc)
        await self.db.commit()
        await self.db.refresh(created)

        await self.event_bus.publish(
            "MeetingAssociatedWithProject",
            {
                "project_id": str(project_id),
                "meeting_id": str(meeting_id),
                "tenant_id": project.tenant_id,
                "added_by": user_id,
            },
        )

        return ProjectMeetingResponse(
            id=created.id,
            project_id=created.project_id,
            meeting_id=created.meeting_id,
            meeting_title=meeting.title,
            meeting_status=meeting.status,
            meeting_start_time=meeting.actual_start or meeting.scheduled_start,
            added_by=created.added_by,
            notes=created.notes,
            created_at=created.created_at,
        )

    async def remove_meeting_from_project(
        self,
        project_id: uuid.UUID,
        meeting_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> bool:
        """Removes a meeting association from a project."""
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundException(message=f"Project '{project_id}' not found", code="PROJECT_NOT_FOUND")

        self._validate_auth(auth_context, project.tenant_id)

        deleted = await self.project_meeting_repo.delete_association(project_id, meeting_id)
        if not deleted:
            raise NotFoundException(
                message=f"Meeting '{meeting_id}' is not associated with project '{project_id}'",
                code="ASSOCIATION_NOT_FOUND",
            )
        await self.db.commit()

        await self.event_bus.publish(
            "MeetingRemovedFromProject",
            {
                "project_id": str(project_id),
                "meeting_id": str(meeting_id),
                "tenant_id": project.tenant_id,
            },
        )
        return True

    async def list_project_meetings(
        self,
        project_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[ProjectMeetingResponse], int]:
        """Lists meetings associated with a project."""
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundException(message=f"Project '{project_id}' not found", code="PROJECT_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, project.tenant_id)

        assocs, total = await self.project_meeting_repo.list_by_project(
            project_id=project_id,
            skip=offset,
            limit=limit,
        )

        results = []
        for a in assocs:
            meeting = a.meeting
            results.append(
                ProjectMeetingResponse(
                    id=a.id,
                    project_id=a.project_id,
                    meeting_id=a.meeting_id,
                    meeting_title=meeting.title if meeting else "Unknown Meeting",
                    meeting_status=meeting.status if meeting else "unknown",
                    meeting_start_time=(meeting.actual_start or meeting.scheduled_start) if meeting else None,
                    added_by=a.added_by,
                    notes=a.notes,
                    created_at=a.created_at,
                )
            )
        return results, total

    # -------------------------------------------------------------------------
    # Helper: Fetch Project Meetings Context
    # -------------------------------------------------------------------------

    async def _get_project_context(
        self,
        project_id: uuid.UUID,
        auth_context: Optional[Dict[str, Any]],
    ) -> Tuple[Project, List[uuid.UUID], Dict[uuid.UUID, Meeting]]:
        """Validates project access and returns list of meeting IDs and lookup map."""
        project = await self.project_repo.get_with_meetings(project_id)
        if not project:
            raise NotFoundException(message=f"Project '{project_id}' not found", code="PROJECT_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, project.tenant_id)

        meetings_map: Dict[uuid.UUID, Meeting] = {}
        meeting_ids: List[uuid.UUID] = []

        if project.project_meetings:
            for pm in project.project_meetings:
                if pm.meeting:
                    meetings_map[pm.meeting_id] = pm.meeting
                    meeting_ids.append(pm.meeting_id)

        return project, meeting_ids, meetings_map

    # -------------------------------------------------------------------------
    # Cross-Meeting Action Items
    # -------------------------------------------------------------------------

    async def get_cross_meeting_action_items(
        self,
        project_id: uuid.UUID,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        min_confidence: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> CrossMeetingActionItemsSummary:
        """Aggregates and filters action items across all meetings in a project."""
        project, meeting_ids, _ = await self._get_project_context(project_id, auth_context)

        if not meeting_ids:
            return CrossMeetingActionItemsSummary(
                project_id=project_id,
                total_action_items=0,
                open_count=0,
                in_progress_count=0,
                completed_count=0,
                cancelled_count=0,
                critical_count=0,
                high_count=0,
                by_assignee={},
                items=[],
                limit=limit,
                offset=offset,
            )

        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id.in_(meeting_ids),
            KnowledgeObject.object_type == "action_item",
        )
        if min_confidence is not None:
            query = query.where(KnowledgeObject.confidence >= min_confidence)

        items_res = await self.db.execute(query.order_by(KnowledgeObject.created_at.desc()))
        all_kos = list(items_res.scalars().all())

        # Map to action item responses & calculate aggregates
        open_c = 0
        in_prog_c = 0
        comp_c = 0
        canc_c = 0
        crit_c = 0
        high_c = 0
        assignee_counter: Counter = Counter()
        mapped_items: List[ActionItemResponse] = []

        for ko in all_kos:
            payload = ko.payload or {}
            provenance = ko.provenance or {}
            raw_status = str(payload.get("status") or ko.status or "open").lower()

            if raw_status in ("completed", "done", "validated"):
                status_enum = ActionItemStatus.COMPLETED
                comp_c += 1
            elif raw_status in ("cancelled", "canceled", "rejected"):
                status_enum = ActionItemStatus.CANCELLED
                canc_c += 1
            elif raw_status in ("in_progress", "active", "doing"):
                status_enum = ActionItemStatus.IN_PROGRESS
                in_prog_c += 1
            else:
                status_enum = ActionItemStatus.OPEN
                open_c += 1

            raw_prio = str(payload.get("priority", "medium")).lower()
            if raw_prio in ("critical", "urgent"):
                prio_enum = ActionItemPriority.CRITICAL
                crit_c += 1
            elif raw_prio == "high":
                prio_enum = ActionItemPriority.HIGH
                high_c += 1
            elif raw_prio == "low":
                prio_enum = ActionItemPriority.LOW
            else:
                prio_enum = ActionItemPriority.MEDIUM

            item_assignee = payload.get("assignee") or payload.get("owner")
            if item_assignee:
                assignee_counter[item_assignee] += 1

            confidence = ko.confidence if ko.confidence is not None else 1.0
            is_low = confidence < 0.75

            ai_resp = ActionItemResponse(
                id=ko.id,
                meeting_id=ko.meeting_id,
                title=ko.title or ko.content[:80],
                description=ko.content,
                status=status_enum,
                priority=prio_enum,
                assignee=item_assignee,
                due_date=payload.get("due_date"),
                confidence=confidence,
                is_low_confidence=is_low,
                requires_verification=payload.get("requires_verification", is_low),
                source_segments=[str(s) for s in payload.get("source_segments", [])],
                version=ko.version,
                provenance=provenance,
                created_at=ko.created_at,
                updated_at=ko.updated_at,
            )
            mapped_items.append(ai_resp)

        # Apply filters
        filtered = mapped_items
        if status:
            norm_s = status.strip().lower()
            filtered = [i for i in filtered if i.status.value == norm_s]
        if priority:
            norm_p = priority.strip().lower()
            filtered = [i for i in filtered if i.priority.value == norm_p]
        if assignee:
            norm_a = assignee.strip().lower()
            filtered = [i for i in filtered if i.assignee and norm_a in i.assignee.lower()]

        # Paginate
        paginated = filtered[offset : offset + limit]

        return CrossMeetingActionItemsSummary(
            project_id=project_id,
            total_action_items=len(mapped_items),
            open_count=open_c,
            in_progress_count=in_prog_c,
            completed_count=comp_c,
            cancelled_count=canc_c,
            critical_count=crit_c,
            high_count=high_c,
            by_assignee=dict(assignee_counter),
            items=paginated,
            limit=limit,
            offset=offset,
        )

    # -------------------------------------------------------------------------
    # Cross-Meeting Decisions
    # -------------------------------------------------------------------------

    async def get_cross_meeting_decisions(
        self,
        project_id: uuid.UUID,
        min_confidence: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> CrossMeetingDecisionsResponse:
        """Aggregates decisions recorded across project meetings."""
        project, meeting_ids, meetings_map = await self._get_project_context(project_id, auth_context)

        if not meeting_ids:
            return CrossMeetingDecisionsResponse(
                project_id=project_id,
                total=0,
                limit=limit,
                offset=offset,
                items=[],
            )

        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id.in_(meeting_ids),
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

        results: List[CrossMeetingDecisionItem] = []
        for ko in kos:
            payload = ko.payload or {}
            meeting = meetings_map.get(ko.meeting_id)
            confidence = ko.confidence if ko.confidence is not None else 1.0
            is_low = confidence < 0.75

            results.append(
                CrossMeetingDecisionItem(
                    id=ko.id,
                    meeting_id=ko.meeting_id,
                    meeting_title=meeting.title if meeting else "Unknown Meeting",
                    title=ko.title,
                    content=ko.content,
                    status=ko.status,
                    confidence=confidence,
                    is_low_confidence=is_low,
                    requires_verification=payload.get("requires_verification", is_low),
                    alternatives=payload.get("alternatives", []),
                    impact=payload.get("impact"),
                    rationales=payload.get("rationales", []),
                    created_at=ko.created_at,
                )
            )

        return CrossMeetingDecisionsResponse(
            project_id=project_id,
            total=total,
            limit=limit,
            offset=offset,
            items=results,
        )

    # -------------------------------------------------------------------------
    # Recurring Topics Detection
    # -------------------------------------------------------------------------

    async def get_recurring_topics(
        self,
        project_id: uuid.UUID,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> RecurringTopicsResponse:
        """
        Detects topics that recur across multiple project meetings by analyzing
        topic titles, keywords, and semantic tokens.
        """
        project, meeting_ids, meetings_map = await self._get_project_context(project_id, auth_context)

        if not meeting_ids:
            return RecurringTopicsResponse(
                project_id=project_id,
                total_meetings_analyzed=0,
                topics=[],
            )

        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id.in_(meeting_ids),
            KnowledgeObject.object_type == "topic",
        )
        res = await self.db.execute(query)
        all_topics = list(res.scalars().all())

        # Group topics by normalized key
        topic_groups: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "display_name": "",
                "meeting_ids": set(),
                "keywords": set(),
                "confidences": [],
                "first_seen": None,
                "last_seen": None,
            }
        )

        for t in all_topics:
            payload = t.payload or {}
            raw_title = t.title or t.content[:50]
            norm_key = re.sub(r"[^a-zA-Z0-9\s]", "", raw_title.lower()).strip()
            # Clean common words
            norm_key = " ".join([w for w in norm_key.split() if len(w) > 2])
            if not norm_key:
                norm_key = raw_title.lower()

            group = topic_groups[norm_key]
            if not group["display_name"]:
                group["display_name"] = raw_title
            group["meeting_ids"].add(t.meeting_id)

            for kw in payload.get("keywords", []):
                group["keywords"].add(str(kw).lower())

            if t.confidence is not None:
                group["confidences"].append(t.confidence)

            # Track temporal bounds
            m_time = t.created_at
            if group["first_seen"] is None or (m_time and m_time < group["first_seen"]):
                group["first_seen"] = m_time
            if group["last_seen"] is None or (m_time and m_time > group["last_seen"]):
                group["last_seen"] = m_time

        # Filter topics that appear across meetings or are prominent
        recurring_list: List[RecurringTopicItem] = []
        for key, grp in topic_groups.items():
            occurrence_count = len(grp["meeting_ids"])
            avg_conf = sum(grp["confidences"]) / len(grp["confidences"]) if grp["confidences"] else 1.0
            m_ids = list(grp["meeting_ids"])
            m_titles = [meetings_map[m].title for m in m_ids if m in meetings_map]

            recurring_list.append(
                RecurringTopicItem(
                    topic_name=grp["display_name"],
                    occurrence_count=occurrence_count,
                    meeting_ids=m_ids,
                    meeting_titles=m_titles,
                    keywords=list(grp["keywords"])[:10],
                    first_seen=grp["first_seen"],
                    last_seen=grp["last_seen"],
                    average_confidence=round(avg_conf, 2),
                )
            )

        # Sort by occurrence count descending, then confidence
        recurring_list.sort(key=lambda x: (x.occurrence_count, x.average_confidence), reverse=True)

        return RecurringTopicsResponse(
            project_id=project_id,
            total_meetings_analyzed=len(meeting_ids),
            topics=recurring_list,
        )

    # -------------------------------------------------------------------------
    # Cross-Meeting Insights
    # -------------------------------------------------------------------------

    async def get_cross_meeting_insights(
        self,
        project_id: uuid.UUID,
        min_confidence: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> CrossMeetingInsightsResponse:
        """Aggregates insights and sentiment breakdown across project meetings."""
        project, meeting_ids, meetings_map = await self._get_project_context(project_id, auth_context)

        if not meeting_ids:
            return CrossMeetingInsightsResponse(
                project_id=project_id,
                total=0,
                limit=limit,
                offset=offset,
                sentiment_distribution={},
                items=[],
            )

        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id.in_(meeting_ids),
            KnowledgeObject.object_type.in_(["transcript_insight", "insight", "context_insight"]),
        )
        if min_confidence is not None:
            query = query.where(KnowledgeObject.confidence >= min_confidence)

        res = await self.db.execute(query.order_by(KnowledgeObject.created_at.desc()))
        all_kos = list(res.scalars().all())

        sentiment_counter: Counter = Counter()
        items: List[CrossMeetingInsightItem] = []

        for ko in all_kos:
            payload = ko.payload or {}
            meeting = meetings_map.get(ko.meeting_id)
            sentiment = payload.get("sentiment", "neutral").lower()
            sentiment_counter[sentiment] += 1

            confidence = ko.confidence if ko.confidence is not None else 1.0
            is_low = confidence < 0.75

            items.append(
                CrossMeetingInsightItem(
                    id=ko.id,
                    meeting_id=ko.meeting_id,
                    meeting_title=meeting.title if meeting else "Unknown Meeting",
                    insight_type=payload.get("insight_type", ko.object_type),
                    title=ko.title,
                    content=ko.content,
                    sentiment=sentiment,
                    confidence=confidence,
                    is_low_confidence=is_low,
                    requires_verification=payload.get("requires_verification", is_low),
                    created_at=ko.created_at,
                )
            )

        paginated = items[offset : offset + limit]

        return CrossMeetingInsightsResponse(
            project_id=project_id,
            total=len(items),
            limit=limit,
            offset=offset,
            sentiment_distribution=dict(sentiment_counter),
            items=paginated,
        )

    # -------------------------------------------------------------------------
    # Project Historical Context & Timeline
    # -------------------------------------------------------------------------

    async def get_project_historical_context(
        self,
        project_id: uuid.UUID,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> ProjectHistoricalContextResponse:
        """Retrieves chronological progression of meetings, decisions, and action items."""
        project, meeting_ids, meetings_map = await self._get_project_context(project_id, auth_context)

        if not meeting_ids:
            return ProjectHistoricalContextResponse(
                project_id=project_id,
                project_name=project.name,
                total_meetings=0,
                timeline=[],
                recurring_themes=[],
            )

        # Sort meetings chronologically
        sorted_meetings = sorted(
            meetings_map.values(),
            key=lambda m: m.actual_start or m.scheduled_start or m.created_at,
        )

        # Query all knowledge objects for these meetings to compute counts
        ko_stmt = select(KnowledgeObject).where(KnowledgeObject.meeting_id.in_(meeting_ids))
        ko_res = await self.db.execute(ko_stmt)
        all_kos = list(ko_res.scalars().all())

        meeting_decisions: Dict[uuid.UUID, int] = defaultdict(int)
        meeting_action_items: Dict[uuid.UUID, int] = defaultdict(int)
        meeting_open_actions: Dict[uuid.UUID, int] = defaultdict(int)
        meeting_summaries: Dict[uuid.UUID, str] = {}
        all_topic_titles: List[str] = []

        for ko in all_kos:
            if ko.object_type == "decision":
                meeting_decisions[ko.meeting_id] += 1
            elif ko.object_type == "action_item":
                meeting_action_items[ko.meeting_id] += 1
                raw_st = str((ko.payload or {}).get("status") or ko.status or "open").lower()
                if raw_st in ("open", "in_progress", "active"):
                    meeting_open_actions[ko.meeting_id] += 1
            elif ko.object_type == "summary":
                meeting_summaries[ko.meeting_id] = ko.content[:160] + "..." if len(ko.content) > 160 else ko.content
            elif ko.object_type == "topic":
                all_topic_titles.append(ko.title or ko.content[:40])

        timeline: List[MeetingTimelineEntry] = []
        for m in sorted_meetings:
            timeline.append(
                MeetingTimelineEntry(
                    meeting_id=m.id,
                    title=m.title,
                    status=m.status,
                    date=m.actual_start or m.scheduled_start or m.created_at,
                    decisions_count=meeting_decisions[m.id],
                    action_items_count=meeting_action_items[m.id],
                    open_action_items_count=meeting_open_actions[m.id],
                    summary_snippet=meeting_summaries.get(m.id, m.description),
                )
            )

        # Recurring themes (top 5 most common topic keywords)
        theme_counter = Counter([t.lower() for t in all_topic_titles if len(t) > 3])
        top_themes = [theme for theme, _ in theme_counter.most_common(5)]

        return ProjectHistoricalContextResponse(
            project_id=project_id,
            project_name=project.name,
            total_meetings=len(meeting_ids),
            timeline=timeline,
            recurring_themes=top_themes,
        )

    # -------------------------------------------------------------------------
    # Project Executive Summary
    # -------------------------------------------------------------------------

    async def get_project_summary(
        self,
        project_id: uuid.UUID,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> ProjectSummaryResponse:
        """Constructs an authoritative executive summary roll-up for the entire project workspace."""
        project, meeting_ids, meetings_map = await self._get_project_context(project_id, auth_context)

        if not meeting_ids:
            return ProjectSummaryResponse(
                project_id=project_id,
                project_name=project.name,
                total_meetings=0,
                active_meetings=0,
                executive_summary=f"Project '{project.name}' currently has no associated meetings.",
                total_decisions=0,
                total_action_items=0,
                open_action_items=0,
                completed_action_items=0,
                sentiment_overview={},
                key_decisions=[],
                top_action_items=[],
                recurring_topics=[],
            )

        # 1. Fetch action items breakdown
        ai_summary = await self.get_cross_meeting_action_items(project_id=project_id, limit=5, auth_context=auth_context)

        # 2. Fetch decisions
        dec_resp = await self.get_cross_meeting_decisions(project_id=project_id, limit=5, auth_context=auth_context)

        # 3. Fetch recurring topics
        rec_topics = await self.get_recurring_topics(project_id=project_id, auth_context=auth_context)

        # 4. Fetch insights for sentiment overview
        ins_resp = await self.get_cross_meeting_insights(project_id=project_id, limit=1, auth_context=auth_context)

        active_meetings_count = sum(1 for m in meetings_map.values() if m.status in ("in_progress", "active", "created"))

        exec_summary = (
            f"Project '{project.name}' encompasses {len(meeting_ids)} meetings with "
            f"{dec_resp.total} recorded decisions and {ai_summary.total_action_items} total action items "
            f"({ai_summary.open_count + ai_summary.in_progress_count} active, {ai_summary.completed_count} completed)."
        )

        return ProjectSummaryResponse(
            project_id=project_id,
            project_name=project.name,
            total_meetings=len(meeting_ids),
            active_meetings=active_meetings_count,
            executive_summary=exec_summary,
            total_decisions=dec_resp.total,
            total_action_items=ai_summary.total_action_items,
            open_action_items=ai_summary.open_count + ai_summary.in_progress_count,
            completed_action_items=ai_summary.completed_count,
            sentiment_overview=ins_resp.sentiment_distribution,
            key_decisions=dec_resp.items,
            top_action_items=ai_summary.items,
            recurring_topics=rec_topics.topics[:5],
        )

    # -------------------------------------------------------------------------
    # Related Meetings Discovery
    # -------------------------------------------------------------------------

    async def get_related_meetings(
        self,
        meeting_id: uuid.UUID,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> RelatedMeetingsResponse:
        """
        Discovers related meetings sharing overlapping topics, keywords, or projects with similarity scoring.
        """
        target_meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not target_meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, target_meeting.tenant_id)

        # Find target meeting topics & keywords
        target_kos_stmt = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id == meeting_id,
            KnowledgeObject.object_type.in_(["topic", "decision"]),
        )
        target_kos_res = await self.db.execute(target_kos_stmt)
        target_kos = list(target_kos_res.scalars().all())

        target_keywords: Set[str] = set()
        target_topics: Set[str] = set()
        for ko in target_kos:
            if ko.title:
                target_topics.add(ko.title.lower().strip())
            payload = ko.payload or {}
            for kw in payload.get("keywords", []):
                target_keywords.add(str(kw).lower().strip())

        # Find candidate meetings in the same tenant (excluding target meeting)
        candidate_stmt = select(Meeting).where(
            Meeting.tenant_id == target_meeting.tenant_id,
            Meeting.id != meeting_id,
        )
        cand_res = await self.db.execute(candidate_stmt)
        candidates = list(cand_res.scalars().all())

        if not candidates:
            return RelatedMeetingsResponse(meeting_id=meeting_id, total_related=0, related_meetings=[])

        candidate_ids = [m.id for m in candidates]
        cand_kos_stmt = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id.in_(candidate_ids),
            KnowledgeObject.object_type.in_(["topic", "decision"]),
        )
        cand_kos_res = await self.db.execute(cand_kos_stmt)
        cand_kos = list(cand_kos_res.scalars().all())

        cand_topics_map: Dict[uuid.UUID, Set[str]] = defaultdict(set)
        cand_keywords_map: Dict[uuid.UUID, Set[str]] = defaultdict(set)

        for ko in cand_kos:
            if ko.title:
                cand_topics_map[ko.meeting_id].add(ko.title.lower().strip())
            payload = ko.payload or {}
            for kw in payload.get("keywords", []):
                cand_keywords_map[ko.meeting_id].add(str(kw).lower().strip())

        related_results: List[RelatedMeetingItem] = []
        for cand in candidates:
            c_topics = cand_topics_map.get(cand.id, set())
            c_keywords = cand_keywords_map.get(cand.id, set())

            shared_t = target_topics.intersection(c_topics)
            shared_k = target_keywords.intersection(c_keywords)

            # Compute simple Jaccard-like overlap score
            topic_score = (len(shared_t) * 0.6) if target_topics else 0.0
            keyword_score = (len(shared_k) * 0.4) if target_keywords else 0.0
            sim_score = min(1.0, topic_score + keyword_score)

            if sim_score > 0.1 or shared_t or shared_k:
                reason = f"Shares {len(shared_t)} topics and {len(shared_k)} keywords"
                related_results.append(
                    RelatedMeetingItem(
                        meeting_id=cand.id,
                        title=cand.title,
                        date=cand.actual_start or cand.scheduled_start or cand.created_at,
                        shared_topics=list(shared_t),
                        shared_keywords=list(shared_k),
                        similarity_score=round(sim_score, 2),
                        reason=reason,
                    )
                )

        related_results.sort(key=lambda r: r.similarity_score, reverse=True)

        return RelatedMeetingsResponse(
            meeting_id=meeting_id,
            total_related=len(related_results),
            related_meetings=related_results,
        )
