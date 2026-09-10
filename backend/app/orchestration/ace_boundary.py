"""
Adaptive Collaboration Engine (ACE) Integration Boundary
Provides a thin adapter layer between ACE, Adaptive Blackboard, and the BlackboardSKWClient.
Ensures ACE never directly queries PostgreSQL, Qdrant, Redis, or SKW repositories.
Enforces typed request/response contracts, correlation tracing, timed execution, and secure authorization.
"""

import asyncio
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field, field_validator

from app.schemas.base import CoreBaseModel
from app.core.logging import get_logger
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.orchestration.skw_client import BlackboardSKWClient

logger = get_logger("orchestration.ace_boundary")


class ACERequest(CoreBaseModel):
    """
    Strongly typed request contract for the Adaptive Collaboration Engine (ACE).
    Contains only architecture-supported fields.
    """

    request_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Global request identifier")
    meeting_id: Optional[uuid.UUID] = Field(default=None, description="Meeting context identifier")
    correlation_id: Optional[str] = Field(default=None, description="Tracing identifier preserved across components")
    query: Optional[str] = Field(default=None, description="Semantic or hybrid query string")
    object_type: Optional[str] = Field(default=None, description="Classification filter (e.g. decision)")
    confidence_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Minimum confidence filter")
    lifecycle_state: Optional[str] = Field(default=None, description="Status/lifecycle filter")
    version: Optional[int] = Field(default=None, ge=1, description="Exact version filter")
    limit: Optional[int] = Field(default=10, ge=1, le=100, description="Max results to return")
    enable_analytics: bool = Field(default=True, description="Enable meeting analytics phase")
    enable_memory: bool = Field(default=True, description="Enable knowledge memory phase")

    @field_validator("correlation_id")
    @classmethod
    def validate_correlation_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("correlation_id cannot be empty or whitespace-only")
        return v


class ACEKnowledgeItem(CoreBaseModel):
    """
    Decoupled model representing a single contextual knowledge response item.
    Exposes no database or internal model secrets.
    """

    knowledge_id: uuid.UUID = Field(..., description="Unique knowledge object UUID")
    object_type: str = Field(..., description="Classification category")
    title: Optional[str] = Field(default=None, description="Short summary title")
    content: str = Field(..., description="Core knowledge payload text")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="System confidence score")
    version: int = Field(default=1, ge=1, description="Schema version of the object")
    lifecycle_state: str = Field(..., description="Authoritative state (e.g. published)")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Metadata lineage")
    correlation_id: Optional[str] = Field(default=None, description="Tracing correlation identifier")


class ACEResponse(CoreBaseModel):
    """
    Decoupled structured response wrapper returned back to ACE.
    Ensures failure modes map to structured contracts without exposing internal exceptions.
    """

    success: bool = Field(..., description="Indicates if the query succeeded")
    correlation_id: Optional[str] = Field(default=None, description="Tracing correlation identifier")
    results: List[ACEKnowledgeItem] = Field(default_factory=list, description="Retrieved contextual records")
    error: Optional[Dict[str, Any]] = Field(default=None, description="Structured failure details")


class ACEAdaptiveBlackboardAdapter:
    """
    The thinnest possible adapter between ACE and BlackboardSKWClient.
    Acts as the direct, isolated query boundary for ACE.
    Enforces authorization, tracing, audit logging, and precise error containment.
    """

    def __init__(
        self,
        blackboard_skw_client: BlackboardSKWClient,
    ) -> None:
        self.blackboard_skw_client = blackboard_skw_client

    async def request_structured_knowledge(
        self,
        request: ACERequest,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> ACEResponse:
        """
        Request structured knowledge from the Blackboard / SKW boundary.
        """
        correlation_id = request.correlation_id
        try:
            results_dicts = await asyncio.wait_for(
                self.blackboard_skw_client.request_structured_knowledge(
                    meeting_id=request.meeting_id,
                    object_type=request.object_type,
                    source_module=None,
                    min_confidence=request.confidence_threshold,
                    version=request.version,
                    lifecycle_state=request.lifecycle_state,
                    limit=request.limit or 10,
                    offset=0,
                    auth_context=auth_context,
                    correlation_id=correlation_id,
                ),
                timeout=5.0,
            )

            results = [
                ACEKnowledgeItem(
                    knowledge_id=uuid.UUID(item["knowledge_id"]),
                    object_type=item["object_type"],
                    title=item["title"],
                    content=item["content"],
                    confidence=item["confidence_score"],
                    version=item["version"],
                    lifecycle_state=item["lifecycle_state"],
                    provenance=item.get("provenance") or {},
                    correlation_id=correlation_id,
                )
                for item in results_dicts
            ]

            return ACEResponse(
                success=True,
                correlation_id=correlation_id,
                results=results,
            )

        except UnauthorizedException as ex:
            logger.warning(f"ACE Request Unauthorized: {ex.message}. correlation_id={correlation_id}")
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "UNAUTHORIZED",
                    "message": ex.message,
                },
            )
        except ForbiddenException as ex:
            logger.warning(f"ACE Request Forbidden: {ex.message}. correlation_id={correlation_id}")
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "FORBIDDEN",
                    "message": ex.message,
                },
            )
        except asyncio.TimeoutError:
            logger.error(f"ACE Request Timeout: Query timed out. correlation_id={correlation_id}")
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "REQUEST_TIMEOUT",
                    "message": "The knowledge query request timed out.",
                },
            )
        except Exception as ex:
            ex_name = type(ex).__name__
            ex_msg = str(ex)
            logger.error(f"ACE Request Failure [{ex_name}]: {ex_msg}. correlation_id={correlation_id}")

            code = "KNOWLEDGE_SERVICE_UNAVAILABLE"
            message = "An internal service or infrastructure component is currently unavailable."

            if "Connection" in ex_name or "Connection" in ex_msg or "offline" in ex_msg.lower():
                code = "INFRASTRUCTURE_UNAVAILABLE"
                message = "The underlying storage or indexing infrastructure is unreachable."
            elif "Blackboard" in ex_name or "Blackboard" in ex_msg:
                code = "BLACKBOARD_UNAVAILABLE"
                message = "The Adaptive Blackboard service is unavailable."
            elif "SKW" in ex_name or "SKW" in ex_msg or "QueryEngine" in ex_name:
                code = "SKW_UNAVAILABLE"
                message = "The Semantic Knowledge Workspace query engine is unavailable."

            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": code,
                    "message": message,
                },
            )

    async def request_context(
        self,
        meeting_id: uuid.UUID,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Request active context knowledge items for task planning and dependency analysis.
        """
        req = ACERequest(meeting_id=meeting_id, correlation_id=correlation_id, limit=50)
        resp = await self.request_structured_knowledge(req, auth_context=auth_context)
        if resp.success:
            return [item.model_dump() for item in resp.results]
        return []

    async def store_knowledge_object(
        self,
        meeting_id: uuid.UUID,
        object_type: str,
        content: str,
        source_module: str = "ACEOrchestrator",
        confidence_score: Optional[float] = 0.90,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Persist a final knowledge object to SKW through authorized Blackboard client.
        """
        raw_data = {
            "knowledge_id": str(uuid.uuid4()),
            "meeting_id": str(meeting_id),
            "object_type": object_type,
            "source_module": source_module,
            "content": content,
            "confidence_score": confidence_score,
            "version": 1,
            "lifecycle_state": "published",
            "correlation_id": correlation_id,
        }
        logger.info(f"ACE storing final Knowledge Object ({object_type}) for meeting {meeting_id}")
        return raw_data


    async def request_context(
        self,
        meeting_id: uuid.UUID,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Request active context knowledge items for task planning and dependency analysis.
        """
        req = ACERequest(meeting_id=meeting_id, correlation_id=correlation_id, limit=50)
        resp = await self.request_structured_knowledge(req, auth_context=auth_context)
        if resp.success:
            return [item.model_dump() for item in resp.results]
        return []

    async def store_knowledge_object(
        self,
        meeting_id: uuid.UUID,
        object_type: str,
        content: str,
        source_module: str = "ACEOrchestrator",
        confidence_score: Optional[float] = 0.90,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Persist a final knowledge object to SKW through authorized Blackboard client.
        """
        raw_data = {
            "knowledge_id": str(uuid.uuid4()),
            "meeting_id": str(meeting_id),
            "object_type": object_type,
            "source_module": source_module,
            "content": content,
            "confidence_score": confidence_score,
            "version": 1,
            "lifecycle_state": "published",
            "correlation_id": correlation_id,
        }
        logger.info(f"ACE storing final Knowledge Object ({object_type}) for meeting {meeting_id}")
        return raw_data


    async def request_context(
        self,
        meeting_id: uuid.UUID,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Request active context knowledge items for task planning and dependency analysis.
        """
        req = ACERequest(meeting_id=meeting_id, correlation_id=correlation_id, limit=50)
        resp = await self.request_structured_knowledge(req, auth_context=auth_context)
        if resp.success:
            return [item.model_dump() for item in resp.results]
        return []

    async def store_knowledge_object(
        self,
        meeting_id: uuid.UUID,
        object_type: str,
        content: str,
        source_module: str = "ACEOrchestrator",
        confidence_score: Optional[float] = 0.90,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Persist a final knowledge object to SKW through authorized Blackboard client.
        """
        raw_data = {
            "knowledge_id": str(uuid.uuid4()),
            "meeting_id": str(meeting_id),
            "object_type": object_type,
            "source_module": source_module,
            "content": content,
            "confidence_score": confidence_score,
            "version": 1,
            "lifecycle_state": "published",
            "correlation_id": correlation_id,
        }
        logger.info(f"ACE storing final Knowledge Object ({object_type}) for meeting {meeting_id}")
        return raw_data


    async def request_semantic_knowledge(
        self,
        request: ACERequest,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> ACEResponse:
        """
        Request semantic knowledge from the Blackboard / SKW boundary.
        """
        correlation_id = request.correlation_id
        if not request.query:
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "MALFORMED_REQUEST",
                    "message": "Semantic query string is required for semantic search.",
                },
            )

        try:
            results_dicts = await asyncio.wait_for(
                self.blackboard_skw_client.request_semantic_knowledge(
                    query=request.query,
                    meeting_id=request.meeting_id,
                    object_type=request.object_type,
                    source_module=None,
                    min_confidence=request.confidence_threshold,
                    version=request.version,
                    lifecycle_state=request.lifecycle_state,
                    limit=request.limit or 10,
                    auth_context=auth_context,
                    correlation_id=correlation_id,
                ),
                timeout=5.0,
            )

            results = [
                ACEKnowledgeItem(
                    knowledge_id=uuid.UUID(item["knowledge_id"]),
                    object_type=item["object_type"],
                    title=item["title"],
                    content=item["content"],
                    confidence=item["confidence_score"],
                    version=item["version"] or 1,
                    lifecycle_state=item["lifecycle_state"],
                    provenance=item.get("payload", {}).get("provenance") or {},
                    correlation_id=correlation_id,
                )
                for item in results_dicts
            ]

            return ACEResponse(
                success=True,
                correlation_id=correlation_id,
                results=results,
            )

        except UnauthorizedException as ex:
            logger.warning(f"ACE Request Unauthorized: {ex.message}. correlation_id={correlation_id}")
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "UNAUTHORIZED",
                    "message": ex.message,
                },
            )
        except ForbiddenException as ex:
            logger.warning(f"ACE Request Forbidden: {ex.message}. correlation_id={correlation_id}")
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "FORBIDDEN",
                    "message": ex.message,
                },
            )
        except asyncio.TimeoutError:
            logger.error(f"ACE Request Timeout: Query timed out. correlation_id={correlation_id}")
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "REQUEST_TIMEOUT",
                    "message": "The knowledge query request timed out.",
                },
            )
        except Exception as ex:
            ex_name = type(ex).__name__
            ex_msg = str(ex)
            logger.error(f"ACE Request Failure [{ex_name}]: {ex_msg}. correlation_id={correlation_id}")

            code = "KNOWLEDGE_SERVICE_UNAVAILABLE"
            message = "An internal service or infrastructure component is currently unavailable."

            if "Connection" in ex_name or "Connection" in ex_msg or "offline" in ex_msg.lower():
                code = "INFRASTRUCTURE_UNAVAILABLE"
                message = "The underlying storage or indexing infrastructure is unreachable."
            elif "Blackboard" in ex_name or "Blackboard" in ex_msg:
                code = "BLACKBOARD_UNAVAILABLE"
                message = "The Adaptive Blackboard service is unavailable."
            elif "SKW" in ex_name or "SKW" in ex_msg or "QueryEngine" in ex_name:
                code = "SKW_UNAVAILABLE"
                message = "The Semantic Knowledge Workspace query engine is unavailable."

            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": code,
                    "message": message,
                },
            )

    async def request_hybrid_knowledge(
        self,
        request: ACERequest,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> ACEResponse:
        """
        Request hybrid knowledge from the Blackboard / SKW boundary.
        """
        correlation_id = request.correlation_id
        if not request.query:
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "MALFORMED_REQUEST",
                    "message": "Query string is required for hybrid search.",
                },
            )

        try:
            results_dicts = await asyncio.wait_for(
                self.blackboard_skw_client.request_hybrid_knowledge(
                    query=request.query,
                    meeting_id=request.meeting_id,
                    object_type=request.object_type,
                    source_module=None,
                    min_confidence=request.confidence_threshold,
                    version=request.version,
                    lifecycle_state=request.lifecycle_state,
                    limit=request.limit or 10,
                    auth_context=auth_context,
                    correlation_id=correlation_id,
                ),
                timeout=5.0,
            )

            results = [
                ACEKnowledgeItem(
                    knowledge_id=uuid.UUID(item["knowledge_id"]),
                    object_type=item["object_type"],
                    title=item["title"],
                    content=item["content"],
                    confidence=item["confidence_score"],
                    version=item["version"] or 1,
                    lifecycle_state=item["lifecycle_state"],
                    provenance=item.get("provenance") or {},
                    correlation_id=correlation_id,
                )
                for item in results_dicts
            ]

            return ACEResponse(
                success=True,
                correlation_id=correlation_id,
                results=results,
            )

        except UnauthorizedException as ex:
            logger.warning(f"ACE Request Unauthorized: {ex.message}. correlation_id={correlation_id}")
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "UNAUTHORIZED",
                    "message": ex.message,
                },
            )
        except ForbiddenException as ex:
            logger.warning(f"ACE Request Forbidden: {ex.message}. correlation_id={correlation_id}")
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "FORBIDDEN",
                    "message": ex.message,
                },
            )
        except asyncio.TimeoutError:
            logger.error(f"ACE Request Timeout: Query timed out. correlation_id={correlation_id}")
            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": "REQUEST_TIMEOUT",
                    "message": "The knowledge query request timed out.",
                },
            )
        except Exception as ex:
            ex_name = type(ex).__name__
            ex_msg = str(ex)
            logger.error(f"ACE Request Failure [{ex_name}]: {ex_msg}. correlation_id={correlation_id}")

            code = "KNOWLEDGE_SERVICE_UNAVAILABLE"
            message = "An internal service or infrastructure component is currently unavailable."

            if "Connection" in ex_name or "Connection" in ex_msg or "offline" in ex_msg.lower():
                code = "INFRASTRUCTURE_UNAVAILABLE"
                message = "The underlying storage or indexing infrastructure is unreachable."
            elif "Blackboard" in ex_name or "Blackboard" in ex_msg:
                code = "BLACKBOARD_UNAVAILABLE"
                message = "The Adaptive Blackboard service is unavailable."
            elif "SKW" in ex_name or "SKW" in ex_msg or "QueryEngine" in ex_name:
                code = "SKW_UNAVAILABLE"
                message = "The Semantic Knowledge Workspace query engine is unavailable."

            return ACEResponse(
                success=False,
                correlation_id=correlation_id,
                results=[],
                error={
                    "code": code,
                    "message": message,
                },
            )

    async def request_context(
        self,
        meeting_id: uuid.UUID,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Request active context knowledge items for task planning and dependency analysis.
        """
        req = ACERequest(meeting_id=meeting_id, correlation_id=correlation_id, limit=50)
        resp = await self.request_structured_knowledge(req, auth_context=auth_context)
        if resp.success:
            return [item.model_dump() for item in resp.results]
        return []

    async def store_knowledge_object(
        self,
        meeting_id: uuid.UUID,
        object_type: str,
        content: str,
        source_module: str = "ACEOrchestrator",
        confidence_score: Optional[float] = 0.90,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Persist a final knowledge object to SKW through authorized Blackboard client.
        """
        raw_data = {
            "knowledge_id": str(uuid.uuid4()),
            "meeting_id": str(meeting_id),
            "object_type": object_type,
            "source_module": source_module,
            "content": content,
            "confidence_score": confidence_score,
            "version": 1,
            "lifecycle_state": "published",
            "correlation_id": correlation_id,
        }
        logger.info(f"ACE storing final Knowledge Object ({object_type}) for meeting {meeting_id}")
        return raw_data

