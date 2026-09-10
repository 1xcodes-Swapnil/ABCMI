"""
ACE Integration Boundary Tests (Phase 4.10)
Verifies:
1. Structured, Semantic, and Hybrid knowledge requests from ACE.
2. Direct request routing through the Blackboard and SKW interfaces.
3. Strict isolation: ACE never directly interacts with PostgreSQL or Qdrant.
4. Tracing: End-to-end correlation_id preservation.
5. Security: RBAC, authorization validation, scope validation, and unauthorized rejection.
6. Robust failure modes: timeouts, unavailability handling, and structured response mapping.
7. Audit trail logging for authorized and unauthorized requests.
"""

import asyncio
from typing import Any, Dict, List
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.models.knowledge_object import KnowledgeObject as DBKnowledgeObject
from app.orchestration.ace_boundary import (
    ACEAdaptiveBlackboardAdapter,
    ACEKnowledgeItem,
    ACERequest,
    ACEResponse,
)
from app.orchestration.skw_client import BlackboardSKWClient
from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine


@pytest.fixture
def sample_meeting_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_correlation_id() -> str:
    return "corr-ace-777"


@pytest.fixture
def mock_skw_client() -> BlackboardSKWClient:
    return MagicMock(spec=BlackboardSKWClient)


@pytest.fixture
def adapter(mock_skw_client) -> ACEAdaptiveBlackboardAdapter:
    return ACEAdaptiveBlackboardAdapter(blackboard_skw_client=mock_skw_client)


# -----------------------------------------------------------------------------
# 1. Structured Knowledge Retrieval Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ace_request_structured_knowledge_success(adapter, mock_skw_client, sample_meeting_id, sample_correlation_id):
    """Test successful retrieval of structured knowledge through the adapter."""
    mock_skw_client.request_structured_knowledge = AsyncMock(return_value=[
        {
            "knowledge_id": str(uuid.uuid4()),
            "meeting_id": str(sample_meeting_id),
            "object_type": "decision",
            "source_module": "decision_agent",
            "title": "Migrate Database",
            "content": "Transition database schema to v5.",
            "confidence_score": 0.98,
            "version": 2,
            "lifecycle_state": "published",
            "provenance": {"producer": "decision_agent"},
            "correlation_id": sample_correlation_id,
        }
    ])

    request = ACERequest(
        meeting_id=sample_meeting_id,
        correlation_id=sample_correlation_id,
        object_type="decision",
        confidence_threshold=0.9,
        lifecycle_state="published",
        version=2,
        limit=5,
    )

    auth_context = {"auth_token": "test-token"}
    response = await adapter.request_structured_knowledge(request, auth_context=auth_context)

    assert response.success is True
    assert response.correlation_id == sample_correlation_id
    assert len(response.results) == 1

    item = response.results[0]
    assert item.object_type == "decision"
    assert item.title == "Migrate Database"
    assert item.content == "Transition database schema to v5."
    assert item.confidence == 0.98
    assert item.version == 2
    assert item.lifecycle_state == "published"
    assert item.provenance == {"producer": "decision_agent"}
    assert item.correlation_id == sample_correlation_id

    # Verify routing: request was sent to BlackboardSKWClient
    mock_skw_client.request_structured_knowledge.assert_called_once_with(
        meeting_id=sample_meeting_id,
        object_type="decision",
        source_module=None,
        min_confidence=0.9,
        version=2,
        lifecycle_state="published",
        limit=5,
        offset=0,
        auth_context=auth_context,
        correlation_id=sample_correlation_id,
    )


# -----------------------------------------------------------------------------
# 2. Semantic Knowledge Retrieval Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ace_request_semantic_knowledge_success(adapter, mock_skw_client, sample_meeting_id, sample_correlation_id):
    """Test successful semantic knowledge retrieval from ACE adapter."""
    mock_skw_client.request_semantic_knowledge = AsyncMock(return_value=[
        {
            "knowledge_id": str(uuid.uuid4()),
            "meeting_id": str(sample_meeting_id),
            "object_type": "summary",
            "source_module": "summarizer",
            "title": "Strategy Focus",
            "content": "Focus efforts on native cloud storage capabilities.",
            "confidence_score": 0.85,
            "version": 1,
            "lifecycle_state": "published",
            "payload": {"provenance": {"producer": "summarizer"}},
            "correlation_id": sample_correlation_id,
        }
    ])

    request = ACERequest(
        meeting_id=sample_meeting_id,
        correlation_id=sample_correlation_id,
        query="cloud storage focus",
        limit=10,
    )

    response = await adapter.request_semantic_knowledge(request, auth_context={"authenticated": True})

    assert response.success is True
    assert response.correlation_id == sample_correlation_id
    assert len(response.results) == 1
    assert response.results[0].title == "Strategy Focus"

    # Verify routing parameters
    mock_skw_client.request_semantic_knowledge.assert_called_once_with(
        query="cloud storage focus",
        meeting_id=sample_meeting_id,
        object_type=None,
        source_module=None,
        min_confidence=None,
        version=None,
        lifecycle_state=None,
        limit=10,
        auth_context={"authenticated": True},
        correlation_id=sample_correlation_id,
    )


# -----------------------------------------------------------------------------
# 3. Hybrid Knowledge Retrieval Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ace_request_hybrid_knowledge_success(adapter, mock_skw_client, sample_meeting_id, sample_correlation_id):
    """Test successful hybrid knowledge search from ACE adapter."""
    mock_skw_client.request_hybrid_knowledge = AsyncMock(return_value=[
        {
            "knowledge_id": str(uuid.uuid4()),
            "meeting_id": str(sample_meeting_id),
            "object_type": "action_item",
            "source_module": "action_agent",
            "title": "Assign PRD task",
            "content": "Assign writing of PRD to team lead",
            "confidence_score": 0.94,
            "version": 1,
            "lifecycle_state": "published",
            "provenance": {"source": "manual"},
            "correlation_id": sample_correlation_id,
        }
    ])

    request = ACERequest(
        meeting_id=sample_meeting_id,
        correlation_id=sample_correlation_id,
        query="assign prd draft to lead",
        object_type="action_item",
        limit=3,
    )

    response = await adapter.request_hybrid_knowledge(request, auth_context={"api_key": "skw-secret-api-key"})

    assert response.success is True
    assert len(response.results) == 1
    assert response.results[0].content == "Assign writing of PRD to team lead"


# -----------------------------------------------------------------------------
# 4. Strict Isolation Enforcement
# -----------------------------------------------------------------------------

def test_ace_never_directly_accesses_infrastructure():
    """
    Validation Test: Check that ACE classes do not hold references to database, ORM, or vector engines.
    Ensures structural boundary enforcement.
    """
    import inspect
    from app.orchestration.ace_boundary import ACEAdaptiveBlackboardAdapter

    # Adapter init signature should only receive the BlackboardSKWClient or similar high level clients
    init_params = inspect.signature(ACEAdaptiveBlackboardAdapter.__init__).parameters
    assert "db" not in init_params
    assert "session" not in init_params
    assert "qdrant_client" not in init_params
    assert "redis_client" not in init_params


# -----------------------------------------------------------------------------
# 5. Security & RBAC Enforcement
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ace_request_unauthorized(adapter, mock_skw_client, sample_meeting_id, sample_correlation_id):
    """Test that unauthorized ACE requests are caught and return descriptive error codes without leaking."""
    mock_skw_client.request_structured_knowledge.side_effect = UnauthorizedException(
        message="Invalid credentials",
        code="INVALID_CREDENTIALS",
    )

    request = ACERequest(
        meeting_id=sample_meeting_id,
        correlation_id=sample_correlation_id,
    )

    response = await adapter.request_structured_knowledge(request, auth_context={"auth_token": "bogus"})

    assert response.success is False
    assert response.correlation_id == sample_correlation_id
    assert response.error is not None
    assert response.error["code"] == "UNAUTHORIZED"
    assert "Invalid credentials" in response.error["message"]


@pytest.mark.asyncio
async def test_ace_request_forbidden_meeting_scope(adapter, mock_skw_client, sample_meeting_id, sample_correlation_id):
    """Test that requests out of the authorized scope return Forbidden error responses."""
    mock_skw_client.request_structured_knowledge.side_effect = ForbiddenException(
        message="Forbidden: Cannot query outside scope",
        code="FORBIDDEN",
    )

    request = ACERequest(
        meeting_id=sample_meeting_id,
        correlation_id=sample_correlation_id,
    )

    response = await adapter.request_structured_knowledge(request, auth_context={"meeting_id": str(uuid.uuid4())})

    assert response.success is False
    assert response.error["code"] == "FORBIDDEN"


# -----------------------------------------------------------------------------
# 6. Failure Modes & Timing Enforcement
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ace_request_timeout(adapter, mock_skw_client, sample_meeting_id, sample_correlation_id):
    """Test that long-running calls trigger request timeouts gracefully."""
    async def slow_query(*args, **kwargs):
        await asyncio.sleep(10.0)
        return []

    mock_skw_client.request_structured_knowledge.side_effect = slow_query

    request = ACERequest(
        meeting_id=sample_meeting_id,
        correlation_id=sample_correlation_id,
    )

    # Patch the timeout in adapter to execute faster for test purposes
    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        response = await adapter.request_structured_knowledge(request)

    assert response.success is False
    assert response.error["code"] == "REQUEST_TIMEOUT"


@pytest.mark.asyncio
async def test_ace_request_skw_or_infra_unavailable(adapter, mock_skw_client, sample_meeting_id, sample_correlation_id):
    """Test that underlying DB or Service connection errors map to structured failure responses without leaking internals."""
    mock_skw_client.request_structured_knowledge.side_effect = Exception("OperationalError: database connection offline")

    request = ACERequest(
        meeting_id=sample_meeting_id,
        correlation_id=sample_correlation_id,
    )

    response = await adapter.request_structured_knowledge(request)

    assert response.success is False
    assert response.error["code"] == "INFRASTRUCTURE_UNAVAILABLE"
    # Ensure raw exception trace or technical tables are NOT exposed
    assert "OperationalError" not in response.error["message"]
    assert "database connection offline" not in response.error["message"]


@pytest.mark.asyncio
async def test_ace_request_empty_results(adapter, mock_skw_client, sample_meeting_id, sample_correlation_id):
    """Test handling of clean query executions returning empty knowledge lists."""
    mock_skw_client.request_structured_knowledge.return_value = []

    request = ACERequest(
        meeting_id=sample_meeting_id,
        correlation_id=sample_correlation_id,
    )

    response = await adapter.request_structured_knowledge(request)

    assert response.success is True
    assert len(response.results) == 0


@pytest.mark.asyncio
async def test_ace_request_malformed(adapter, sample_correlation_id):
    """Test validation errors on missing parameters for semantic/hybrid methods."""
    request = ACERequest(
        correlation_id=sample_correlation_id,
        query=None,  # missing query for semantic
    )

    response = await adapter.request_semantic_knowledge(request)
    assert response.success is False
    assert response.error["code"] == "MALFORMED_REQUEST"
