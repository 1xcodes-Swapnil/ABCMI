"""
Ask ABCI-MI Natural Language Query Interface Service (Phase 4.23)
Coordinates authorization, scope resolution, multi-modal knowledge retrieval (structured, semantic, hybrid),
grounded answer synthesis via provider-neutral AnswerProvider, source attribution, query persistence,
and Redis event emission.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional, Set
import uuid
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException, UnauthorizedException
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus
from app.models.knowledge_object import KnowledgeObject as DBKnowledgeObject
from app.models.meeting import Meeting
from app.models.project import Project, ProjectMeeting
from app.models.query_record import QueryRecord
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.project_repo import ProjectMeetingRepository, ProjectRepository
from app.repositories.query_repo import QueryRecordRepository
from app.schemas.query import (
    QueryAnswerStatus,
    QueryHistoryListResponse,
    QueryRequest,
    QueryResponse,
    QueryRetrievalMode,
    QuerySourceKnowledgeObject,
    QuerySourceMeeting,
    QuerySourceProject,
)
from app.services.answer_provider import (
    DeterministicQueryAnswerProvider,
    QueryAnswerProvider,
    QueryProviderRegistry,
    QuerySynthesisResult,
)
from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine

logger = get_logger("services.query_interface")


class QueryInterfaceService:
    """
    High-level query interface service orchestrating natural-language queries
    across meetings, projects, and tenant-scoped historical knowledge.
    """

    CONFIDENCE_THRESHOLD = 0.75

    def __init__(
        self,
        session: AsyncSession,
        answer_provider: Optional[QueryAnswerProvider] = None,
        event_bus: Optional[RedisEventBus] = None,
    ) -> None:
        self.session = session
        self.meeting_repo = MeetingRepository(session)
        self.project_repo = ProjectRepository(session)
        self.project_meeting_repo = ProjectMeetingRepository(session)
        self.ko_repo = KnowledgeObjectRepository(session)
        self.query_repo = QueryRecordRepository(session)
        self.query_engine = KnowledgeQueryEngine(session)
        self.answer_provider = answer_provider or QueryProviderRegistry.get()
        self.event_bus = event_bus or RedisEventBus()

    def _extract_tenant_id(self, auth_context: Dict[str, Any]) -> str:
        """Extracts tenant_id from auth context safely."""
        tenant_id = auth_context.get("tenant_id")
        if not tenant_id:
            tenant_id = auth_context.get("user_id") or "tenant-default"
        return str(tenant_id)

    def _extract_user_id(self, auth_context: Dict[str, Any]) -> Optional[uuid.UUID]:
        """Extracts user_id from auth context safely."""
        uid = auth_context.get("user_id")
        if uid:
            try:
                return uuid.UUID(str(uid))
            except (ValueError, TypeError):
                return None
        return None

    async def _safe_publish_event(self, channel: str, payload: Dict[str, Any]) -> None:
        """Publishes event to Redis event bus gracefully without blocking execution on error."""
        try:
            await self.event_bus.publish(channel, payload)
        except Exception as e:
            logger.warning(f"Failed to publish query event to {channel}: {e}")

    async def answer_query(
        self,
        request: QueryRequest,
        auth_context: Dict[str, Any],
    ) -> QueryResponse:
        """Alias for execute_query."""
        return await self.execute_query(request, auth_context)

    async def execute_query(
        self,
        request: QueryRequest,
        auth_context: Dict[str, Any],
    ) -> QueryResponse:
        """
        Executes a natural language query with strict scope authorization, multi-mode retrieval,
        grounded answer synthesis, source attribution, and persistence.
        """
        tenant_id = self._extract_tenant_id(auth_context)
        user_id = self._extract_user_id(auth_context)
        correlation_id = request.correlation_id or str(uuid.uuid4())
        request_id = request.request_id or correlation_id
        now = datetime.now(timezone.utc)

        # 0. Idempotency Check
        if request.correlation_id:
            existing_record = await self.query_repo.get_by_correlation_id(
                tenant_id=tenant_id,
                correlation_id=request.correlation_id,
            )
            if existing_record:
                logger.info(f"Returning cached query for correlation_id={request.correlation_id}")
                return self._record_to_response(existing_record)

        # 1. Input Validation
        cleaned_query = request.query.strip()
        if not cleaned_query:
            raise BadRequestException("Query text cannot be empty.", code="INVALID_QUERY")

        query_id = str(uuid.uuid4())

        # Emit QueryRequested event
        await self._safe_publish_event(
            "abci.query.requested",
            {
                "event_type": "QueryRequested",
                "query_id": query_id,
                "correlation_id": correlation_id,
                "request_id": request_id,
                "tenant_id": tenant_id,
                "user_id": str(user_id) if user_id else None,
                "query": cleaned_query,
                "scope": request.scope,
                "retrieval_mode": getattr(request.retrieval_mode, "value", str(request.retrieval_mode)),
                "meeting_id": str(request.meeting_id) if request.meeting_id else None,
                "project_id": str(request.project_id) if request.project_id else None,
                "timestamp": now.isoformat(),
            },
        )

        try:
            # 2. Scope Resolution & Authorization
            scoped_meeting_ids: Set[uuid.UUID] = set()
            referenced_meetings: Dict[str, QuerySourceMeeting] = {}
            referenced_projects: Dict[str, QuerySourceProject] = {}
            resolved_scope = request.scope or "cross_meeting"
            scope_description = "tenant workspace"

            # Scope: Meeting
            if request.meeting_id or resolved_scope == "meeting":
                if not request.meeting_id:
                    raise BadRequestException("meeting_id is required for meeting-scoped query.", code="MISSING_SCOPE_PARAM")

                meeting = await self.meeting_repo.get_by_id(request.meeting_id)
                if not meeting:
                    raise NotFoundException(f"Meeting '{request.meeting_id}' not found.", code="MEETING_NOT_FOUND")
                m_tenant = getattr(meeting, "tenant_id", None)
                if m_tenant and m_tenant != tenant_id:
                    raise ForbiddenException("Access to this meeting is forbidden.", code="TENANT_MISMATCH")

                scoped_meeting_ids.add(meeting.id)
                referenced_meetings[str(meeting.id)] = QuerySourceMeeting(
                    meeting_id=str(meeting.id),
                    title=meeting.title,
                    status=meeting.status,
                    start_time=meeting.actual_start or meeting.scheduled_start,
                )
                scope_description = f"meeting '{meeting.title}'"
                resolved_scope = "meeting"

            # Scope: Project
            elif request.project_id or resolved_scope == "project":
                if not request.project_id:
                    raise BadRequestException("project_id is required for project-scoped query.", code="MISSING_SCOPE_PARAM")

                project = await self.project_repo.get_by_id(request.project_id)
                if not project:
                    raise NotFoundException(f"Project '{request.project_id}' not found.", code="PROJECT_NOT_FOUND")
                p_tenant = getattr(project, "tenant_id", None)
                if p_tenant and p_tenant != tenant_id:
                    raise ForbiddenException("Access to this project is forbidden.", code="TENANT_MISMATCH")

                referenced_projects[str(project.id)] = QuerySourceProject(
                    project_id=str(project.id),
                    name=project.name,
                )
                assoc_res = await self.project_meeting_repo.list_by_project(request.project_id)
                associations = assoc_res[0] if isinstance(assoc_res, tuple) else assoc_res
                for assoc in associations:
                    scoped_meeting_ids.add(assoc.meeting_id)
                    if assoc.meeting:
                        referenced_meetings[str(assoc.meeting.id)] = QuerySourceMeeting(
                            meeting_id=str(assoc.meeting.id),
                            title=assoc.meeting.title,
                            status=assoc.meeting.status,
                            start_time=assoc.meeting.actual_start or assoc.meeting.scheduled_start,
                        )
                scope_description = f"project '{project.name}' ({len(scoped_meeting_ids)} meetings)"
                resolved_scope = "project"

            # Scope: Cross-meeting (Tenant Historical)
            else:
                resolved_scope = "cross_meeting"
                query_stmt = select(Meeting)
                if hasattr(Meeting, "tenant_id"):
                    query_stmt = query_stmt.where(Meeting.tenant_id == tenant_id)
                if request.date_from:
                    query_stmt = query_stmt.where(Meeting.scheduled_start >= request.date_from)
                if request.date_to:
                    query_stmt = query_stmt.where(Meeting.scheduled_start <= request.date_to)
                exec_res = await self.session.execute(query_stmt)
                tenant_meetings = list(exec_res.scalars().all())
                for m in tenant_meetings:
                    scoped_meeting_ids.add(m.id)
                    referenced_meetings[str(m.id)] = QuerySourceMeeting(
                        meeting_id=str(m.id),
                        title=m.title,
                        status=m.status,
                        start_time=m.actual_start or m.scheduled_start,
                    )
                scope_description = f"all {len(scoped_meeting_ids)} accessible tenant meetings"

            # 3. Knowledge Retrieval
            retrieved_items: List[Dict[str, Any]] = []

            if not scoped_meeting_ids and (request.meeting_id or request.project_id):
                # No meetings associated with scope
                response = QueryResponse(
                    query_id=query_id,
                    correlation_id=correlation_id,
                    request_id=request_id,
                    query=request.query,
                    scope=resolved_scope,
                    meeting_id=str(request.meeting_id) if request.meeting_id else None,
                    project_id=str(request.project_id) if request.project_id else None,
                    answer="No meetings or knowledge records are associated with this scope yet.",
                    status=QueryAnswerStatus.INSUFFICIENT_CONTEXT,
                    confidence=0.0,
                    retrieval_mode=getattr(request.retrieval_mode, "value", str(request.retrieval_mode)),
                    search_mode=getattr(request.retrieval_mode, "value", str(request.retrieval_mode)),
                    is_low_confidence=True,
                    requires_verification=True,
                    sources=[],
                    source_meetings=[],
                    source_projects=list(referenced_projects.values()),
                    provenance={"scope": "empty_scope"},
                    created_at=now,
                    updated_at=now,
                )
                await self._persist_query(response=response, tenant_id=tenant_id, user_id=user_id)
                await self._safe_publish_event(
                    "abci.query.insufficient_context",
                    {
                        "event_type": "QueryInsufficientContext",
                        "query_id": query_id,
                        "correlation_id": correlation_id,
                        "tenant_id": tenant_id,
                        "status": response.status.value,
                        "timestamp": now.isoformat(),
                    },
                )
                return response

            # Execute knowledge retrieval through chosen mode
            if request.retrieval_mode == QueryRetrievalMode.STRUCTURED:
                retrieved_items = await self._execute_structured_retrieval(
                    query=cleaned_query,
                    scoped_meeting_ids=list(scoped_meeting_ids),
                    knowledge_types=request.knowledge_types,
                    min_confidence=request.min_confidence,
                    limit=request.limit,
                )
            elif request.retrieval_mode == QueryRetrievalMode.SEMANTIC:
                retrieved_items = await self._execute_semantic_retrieval(
                    query=cleaned_query,
                    scoped_meeting_ids=list(scoped_meeting_ids),
                    knowledge_types=request.knowledge_types,
                    min_confidence=request.min_confidence,
                    limit=request.limit,
                )
            else:  # HYBRID (default)
                retrieved_items = await self._execute_hybrid_retrieval(
                    query=cleaned_query,
                    scoped_meeting_ids=list(scoped_meeting_ids),
                    knowledge_types=request.knowledge_types,
                    min_confidence=request.min_confidence,
                    limit=request.limit,
                )

            # 4. Filter and build source attribution
            sources: List[QuerySourceKnowledgeObject] = []
            for item in retrieved_items:
                m_id_str = str(item.get("meeting_id")) if item.get("meeting_id") else None
                m_title = referenced_meetings.get(m_id_str).title if (m_id_str and m_id_str in referenced_meetings) else None
                item["meeting_title"] = m_title

                src = QuerySourceKnowledgeObject(
                    knowledge_id=str(item.get("knowledge_id")),
                    source_id=str(item.get("knowledge_id")),
                    meeting_id=m_id_str,
                    meeting_title=m_title,
                    project_id=str(request.project_id) if request.project_id else None,
                    object_type=str(item.get("object_type", "knowledge")),
                    source_type=str(item.get("object_type", "knowledge")),
                    title=item.get("title"),
                    content=item.get("content"),
                    source_segments=item.get("payload", {}).get("source_segments") or item.get("payload", {}).get("segments"),
                    confidence=item.get("confidence_score") or item.get("confidence"),
                    relevance_score=item.get("relevance_score"),
                    version=item.get("version") or 1,
                    lifecycle_state=item.get("lifecycle_state") or item.get("status"),
                    provenance=item.get("provenance") or {},
                    payload=item.get("payload") or {},
                )
                sources.append(src)

            # 5. Synthesize Answer via Provider
            synthesis: QuerySynthesisResult = await self.answer_provider.synthesize_answer(
                query=cleaned_query,
                retrieved_objects=retrieved_items,
                context_metadata={"scope_description": scope_description},
            )

            # Apply request verification override if requested
            requires_verification = synthesis.requires_verification
            if request.require_verification is True:
                requires_verification = True
            is_low_confidence = synthesis.confidence < self.CONFIDENCE_THRESHOLD or synthesis.is_low_confidence

            # Filter source meetings to only those actually cited in sources
            cited_meeting_ids = {s.meeting_id for s in sources if s.meeting_id}
            active_source_meetings = [m for m in referenced_meetings.values() if m.meeting_id in cited_meeting_ids] or list(referenced_meetings.values())[:5]

            # 6. Publish appropriate Redis completion event
            event_channel = "abci.query.answered"
            event_type = "QueryAnswered"
            if synthesis.status == QueryAnswerStatus.INSUFFICIENT_CONTEXT:
                event_channel = "abci.query.insufficient_context"
                event_type = "QueryInsufficientContext"
            elif requires_verification:
                event_channel = "abci.query.verification_required"
                event_type = "QueryVerificationRequired"

            await self._safe_publish_event(
                event_channel,
                {
                    "event_type": event_type,
                    "query_id": query_id,
                    "correlation_id": correlation_id,
                    "request_id": request_id,
                    "tenant_id": tenant_id,
                    "user_id": str(user_id) if user_id else None,
                    "status": synthesis.status.value,
                    "confidence": synthesis.confidence,
                    "sources_count": len(sources),
                    "scope": resolved_scope,
                    "meeting_id": str(request.meeting_id) if request.meeting_id else None,
                    "project_id": str(request.project_id) if request.project_id else None,
                    "timestamp": now.isoformat(),
                },
            )

            response = QueryResponse(
                query_id=query_id,
                correlation_id=correlation_id,
                request_id=request_id,
                query=request.query,
                scope=resolved_scope,
                meeting_id=str(request.meeting_id) if request.meeting_id else None,
                project_id=str(request.project_id) if request.project_id else None,
                answer=synthesis.answer,
                status=synthesis.status,
                confidence=synthesis.confidence,
                retrieval_mode=getattr(request.retrieval_mode, "value", str(request.retrieval_mode)),
                search_mode=getattr(request.retrieval_mode, "value", str(request.retrieval_mode)),
                is_low_confidence=is_low_confidence,
                requires_verification=requires_verification,
                sources=sources,
                source_meetings=active_source_meetings,
                source_projects=list(referenced_projects.values()),
                provenance={
                    **synthesis.provenance,
                    "retrieval_mode": getattr(request.retrieval_mode, "value", str(request.retrieval_mode)),
                    "retrieved_total": len(retrieved_items),
                    "scoped_meetings_count": len(scoped_meeting_ids),
                },
                created_at=now,
                updated_at=now,
            )

            # Persist query execution
            await self._persist_query(response=response, tenant_id=tenant_id, user_id=user_id)
            return response

        except (BadRequestException, ForbiddenException, NotFoundException, UnauthorizedException):
            raise
        except Exception as e:
            logger.error(f"Unhandled error executing query '{query_id}': {e}", exc_info=True)
            await self._safe_publish_event(
                "abci.query.failed",
                {
                    "event_type": "QueryFailed",
                    "query_id": query_id,
                    "correlation_id": correlation_id,
                    "tenant_id": tenant_id,
                    "user_id": str(user_id) if user_id else None,
                    "error": "Query processing encountered an internal error.",
                    "timestamp": now.isoformat(),
                },
            )
            response = QueryResponse(
                query_id=query_id,
                correlation_id=correlation_id,
                request_id=request_id,
                query=request.query,
                scope=request.scope or "cross_meeting",
                meeting_id=str(request.meeting_id) if request.meeting_id else None,
                project_id=str(request.project_id) if request.project_id else None,
                answer="An error occurred while processing your question. Please try again.",
                status=QueryAnswerStatus.FAILED,
                confidence=0.0,
                retrieval_mode=getattr(request.retrieval_mode, "value", str(request.retrieval_mode)),
                search_mode=getattr(request.retrieval_mode, "value", str(request.retrieval_mode)),
                is_low_confidence=True,
                requires_verification=True,
                sources=[],
                source_meetings=[],
                source_projects=[],
                provenance={"error": "query_execution_error"},
                created_at=now,
                updated_at=now,
            )
            await self._persist_query(response=response, tenant_id=tenant_id, user_id=user_id)
            return response

    async def get_query_by_id(
        self,
        query_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> QueryResponse:
        """Retrieves a single historical query by ID with tenant isolation."""
        tenant_id = self._extract_tenant_id(auth_context)
        record = await self.query_repo.get_by_id(query_id)
        if not record:
            raise NotFoundException(f"Query '{query_id}' not found.", code="QUERY_NOT_FOUND")
        if record.tenant_id != tenant_id:
            raise ForbiddenException("Access to this query is forbidden.", code="TENANT_MISMATCH")

        return self._record_to_response(record)

    async def list_meeting_queries(
        self,
        meeting_id: uuid.UUID,
        auth_context: Dict[str, Any],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> QueryHistoryListResponse:
        """Lists historical queries executed within the scope of a meeting with optional date-range filtering."""
        if start_time and end_time and start_time > end_time:
            raise BadRequestException("start_time must be earlier than or equal to end_time.", code="INVALID_DATE_RANGE")

        tenant_id = self._extract_tenant_id(auth_context)
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(f"Meeting '{meeting_id}' not found.", code="MEETING_NOT_FOUND")
        if meeting.tenant_id != tenant_id:
            raise ForbiddenException("Access to this meeting is forbidden.", code="TENANT_MISMATCH")

        records, total = await self.query_repo.list_by_meeting(
            tenant_id=tenant_id,
            meeting_id=meeting_id,
            start_time=start_time,
            end_time=end_time,
            skip=skip,
            limit=limit,
        )

        items = [self._record_to_response(r) for r in records]
        return QueryHistoryListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=skip,
        )

    async def list_queries(
        self,
        auth_context: Dict[str, Any],
        meeting_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> QueryHistoryListResponse:
        """Lists historical queries across tenant scope with optional meeting, project, and date-range filters."""
        if start_time and end_time and start_time > end_time:
            raise BadRequestException("start_time must be earlier than or equal to end_time.", code="INVALID_DATE_RANGE")

        tenant_id = self._extract_tenant_id(auth_context)
        if meeting_id is not None:
            meeting = await self.meeting_repo.get_by_id(meeting_id)
            if not meeting:
                raise NotFoundException(f"Meeting '{meeting_id}' not found.", code="MEETING_NOT_FOUND")
            if meeting.tenant_id != tenant_id:
                raise ForbiddenException("Access to this meeting is forbidden.", code="TENANT_MISMATCH")

        records, total = await self.query_repo.list_queries(
            tenant_id=tenant_id,
            meeting_id=meeting_id,
            project_id=project_id,
            start_time=start_time,
            end_time=end_time,
            skip=skip,
            limit=limit,
        )

        items = [self._record_to_response(r) for r in records]
        return QueryHistoryListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=skip,
        )

    async def regenerate_query(
        self,
        query_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> QueryResponse:
        """Regenerates answer for an existing query with latest context."""
        tenant_id = self._extract_tenant_id(auth_context)
        record = await self.query_repo.get_by_id(query_id)
        if not record:
            raise NotFoundException(f"Query '{query_id}' not found.", code="QUERY_NOT_FOUND")
        if record.tenant_id != tenant_id:
            raise ForbiddenException("Access to this query is forbidden.", code="TENANT_MISMATCH")

        request = QueryRequest(
            query=record.query,
            scope=record.scope,
            meeting_id=record.meeting_id,
            project_id=record.project_id,
            search_mode=QueryRetrievalMode(record.search_mode),
        )
        return await self.execute_query(request=request, auth_context=auth_context)

    # -------------------------------------------------------------------------
    # Helper & Persistence Methods
    # -------------------------------------------------------------------------

    async def _persist_query(
        self,
        response: QueryResponse,
        tenant_id: str,
        user_id: Optional[uuid.UUID],
    ) -> None:
        """Persists query execution record in the database."""
        try:
            m_id = uuid.UUID(response.meeting_id) if response.meeting_id else None
            p_id = uuid.UUID(response.project_id) if response.project_id else None
            q_id = uuid.UUID(response.query_id) if response.query_id else uuid.uuid4()

            sources_json = [s.model_dump(mode="json") for s in response.sources]
            meetings_json = [m.model_dump(mode="json") for m in response.source_meetings]
            projects_json = [p.model_dump(mode="json") for p in response.source_projects]

            record = QueryRecord(
                id=q_id,
                tenant_id=tenant_id,
                user_id=user_id,
                query=response.query,
                scope=response.scope,
                meeting_id=m_id,
                project_id=p_id,
                answer=response.answer,
                status=getattr(response.status, "value", str(response.status)),
                confidence=response.confidence,
                is_low_confidence=response.is_low_confidence,
                requires_verification=response.requires_verification,
                search_mode=getattr(response.retrieval_mode, "value", str(response.retrieval_mode)),
                sources=sources_json,
                source_meetings=meetings_json,
                source_projects=projects_json,
                provenance=response.provenance,
                correlation_id=response.correlation_id,
                request_id=response.request_id,
            )
            await self.query_repo.create(record)
        except Exception as e:
            logger.warning(f"Failed to persist query record {response.query_id}: {e}")

    def _record_to_response(self, record: QueryRecord) -> QueryResponse:
        """Converts QueryRecord ORM model to QueryResponse schema."""
        sources = [QuerySourceKnowledgeObject(**s) for s in (record.sources or [])]
        source_meetings = [QuerySourceMeeting(**m) for m in (record.source_meetings or [])]
        source_projects = [QuerySourceProject(**p) for p in (record.source_projects or [])]

        return QueryResponse(
            query_id=str(record.id),
            correlation_id=record.correlation_id,
            request_id=record.request_id,
            query=record.query,
            scope=record.scope,
            meeting_id=str(record.meeting_id) if record.meeting_id else None,
            project_id=str(record.project_id) if record.project_id else None,
            answer=record.answer,
            status=QueryAnswerStatus(record.status),
            confidence=record.confidence,
            retrieval_mode=record.search_mode,
            search_mode=record.search_mode,
            is_low_confidence=record.is_low_confidence,
            requires_verification=record.requires_verification,
            sources=sources,
            source_meetings=source_meetings,
            source_projects=source_projects,
            provenance=record.provenance or {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    # -------------------------------------------------------------------------
    # Retrieval Mode Helpers
    # -------------------------------------------------------------------------

    async def _execute_structured_retrieval(
        self,
        query: str,
        scoped_meeting_ids: List[uuid.UUID],
        knowledge_types: Optional[List[str]] = None,
        min_confidence: Optional[float] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieves knowledge objects via SQL filtering and keyword match."""
        if not scoped_meeting_ids:
            return []

        conditions = [DBKnowledgeObject.meeting_id.in_(scoped_meeting_ids)]
        if knowledge_types:
            types_lower = [t.lower() for t in knowledge_types]
            conditions.append(DBKnowledgeObject.object_type.in_(types_lower))
        if min_confidence is not None:
            conditions.append(DBKnowledgeObject.confidence >= min_confidence)

        keywords = [
            w.lower()
            for w in query.split()
            if len(w) > 3
            and w.lower() not in {"what", "which", "where", "about", "show", "tell", "from", "with", "this", "that", "these", "those", "have", "been"}
        ]

        stmt = select(DBKnowledgeObject).where(and_(*conditions)).order_by(DBKnowledgeObject.created_at.desc()).limit(limit * 3)
        res = await self.session.execute(stmt)
        objs = list(res.scalars().all())

        scored: List[Dict[str, Any]] = []
        for o in objs:
            text = f"{o.title or ''} {o.content or ''} {str(o.payload)}".lower()
            match_count = sum(1 for kw in keywords if kw in text)
            relevance = round(min(1.0, 0.5 + (0.1 * min(match_count, 5))), 2)
            scored.append({
                "knowledge_id": str(o.id),
                "meeting_id": str(o.meeting_id),
                "object_type": o.object_type,
                "source_module": o.source_module,
                "title": o.title,
                "content": o.content,
                "confidence_score": o.confidence if o.confidence is not None else 0.8,
                "version": o.version,
                "lifecycle_state": o.status,
                "provenance": o.provenance if isinstance(o.provenance, dict) else {},
                "payload": o.payload if isinstance(o.payload, dict) else {},
                "relevance_score": relevance,
                "retrieval_source": "structured",
            })

        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored[:limit]

    async def _execute_semantic_retrieval(
        self,
        query: str,
        scoped_meeting_ids: List[uuid.UUID],
        knowledge_types: Optional[List[str]] = None,
        min_confidence: Optional[float] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieves knowledge via vector semantic indexer with graceful fallback."""
        if not scoped_meeting_ids:
            return []

        all_hits: List[Dict[str, Any]] = []
        try:
            for m_id in scoped_meeting_ids:
                hits = await self.query_engine.semantic_query(
                    query=query,
                    meeting_id=m_id,
                    object_type=knowledge_types[0] if (knowledge_types and len(knowledge_types) == 1) else None,
                    min_confidence=min_confidence,
                    limit=limit,
                )
                for h in hits:
                    all_hits.append({
                        "knowledge_id": str(h.get("knowledge_id")),
                        "meeting_id": str(h.get("meeting_id")),
                        "object_type": h.get("object_type"),
                        "source_module": h.get("source_module"),
                        "title": h.get("title"),
                        "content": h.get("content"),
                        "confidence_score": h.get("confidence") if h.get("confidence") is not None else 0.8,
                        "version": h.get("version", 1),
                        "lifecycle_state": h.get("lifecycle_state", "active"),
                        "provenance": h.get("payload", {}).get("provenance", {}),
                        "payload": h.get("payload", {}).get("payload", {}),
                        "relevance_score": round(float(h.get("score", 0.7)), 2),
                        "retrieval_source": "semantic",
                    })
        except Exception as e:
            logger.warning(f"Semantic search failed or degraded: {e}. Falling back to structured retrieval.")

        if not all_hits:
            return await self._execute_structured_retrieval(
                query=query,
                scoped_meeting_ids=scoped_meeting_ids,
                knowledge_types=knowledge_types,
                min_confidence=min_confidence,
                limit=limit,
            )

        all_hits.sort(key=lambda x: x["relevance_score"], reverse=True)
        return all_hits[:limit]

    async def _execute_hybrid_retrieval(
        self,
        query: str,
        scoped_meeting_ids: List[uuid.UUID],
        knowledge_types: Optional[List[str]] = None,
        min_confidence: Optional[float] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Combines structured keyword and semantic similarity retrieval."""
        if not scoped_meeting_ids:
            return []

        structured_results = await self._execute_structured_retrieval(
            query=query,
            scoped_meeting_ids=scoped_meeting_ids,
            knowledge_types=knowledge_types,
            min_confidence=min_confidence,
            limit=limit,
        )

        semantic_results = await self._execute_semantic_retrieval(
            query=query,
            scoped_meeting_ids=scoped_meeting_ids,
            knowledge_types=knowledge_types,
            min_confidence=min_confidence,
            limit=limit,
        )

        merged_map: Dict[str, Dict[str, Any]] = {}
        for r in semantic_results:
            kid = r["knowledge_id"]
            merged_map[kid] = r

        for r in structured_results:
            kid = r["knowledge_id"]
            if kid in merged_map:
                merged_map[kid]["relevance_score"] = min(1.0, round(merged_map[kid]["relevance_score"] + 0.2, 2))
                merged_map[kid]["retrieval_source"] = "hybrid_fused"
            else:
                merged_map[kid] = r

        final_list = list(merged_map.values())
        final_list.sort(key=lambda x: x["relevance_score"], reverse=True)
        return final_list[:limit]
