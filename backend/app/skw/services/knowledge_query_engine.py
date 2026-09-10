"""
SKW Knowledge Query Engine & Result Fusion Service
Implements KnowledgeQueryEngine protocol, combining PostgreSQL structured queries,
Qdrant semantic search, multi-attribute filtering, version filtering, confidence thresholds,
result fusion/ranking, and Redis caching.
"""

import json
import uuid
from typing import Any, Dict, List, Optional, Union
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.skw.models.knowledge_object import SKWLifecycleState
from app.models.knowledge_object import KnowledgeObject as DBKnowledgeObject
from app.skw.indexing.semantic_indexer import SemanticIndexer
from app.infrastructure.redis import get_redis_client


class KnowledgeQueryEngine:
    """
    Advanced query engine supporting semantic search, structured filters, meeting-specific retrieval,
    confidence filtering, version filtering, and hybrid result fusion.
    """

    def __init__(
        self,
        session: AsyncSession,
        semantic_indexer: Optional[SemanticIndexer] = None,
    ) -> None:
        self.session = session
        self.semantic_indexer = semantic_indexer or SemanticIndexer()

    async def _get_cache(self, cache_key: str) -> Optional[Any]:
        try:
            redis = await get_redis_client()
            if redis:
                val = await redis.get(cache_key)
                if val:
                    return json.loads(val)
        except Exception:
            pass
        return None

    async def _set_cache(self, cache_key: str, data: Any, ttl_seconds: int = 300) -> None:
        try:
            redis = await get_redis_client()
            if redis:
                await redis.set(cache_key, json.dumps(data, default=str), ex=ttl_seconds)
        except Exception:
            pass

    async def structured_query(
        self,
        meeting_id: Optional[uuid.UUID] = None,
        object_type: Optional[str] = None,
        source_module: Optional[str] = None,
        min_confidence: Optional[float] = None,
        version: Optional[int] = None,
        lifecycle_state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[DBKnowledgeObject]:
        """Execute structured queries against PostgreSQL with filtering."""
        stmt = select(DBKnowledgeObject)
        conditions = []

        if meeting_id:
            conditions.append(DBKnowledgeObject.meeting_id == meeting_id)
        if object_type:
            conditions.append(DBKnowledgeObject.object_type == object_type.lower())
        if source_module:
            conditions.append(DBKnowledgeObject.source_module == source_module)
        if min_confidence is not None:
            conditions.append(DBKnowledgeObject.confidence >= min_confidence)
        if version is not None:
            conditions.append(DBKnowledgeObject.version == version)
        if lifecycle_state:
            conditions.append(DBKnowledgeObject.status == lifecycle_state.lower())

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.order_by(DBKnowledgeObject.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def semantic_query(
        self,
        query: str,
        meeting_id: Optional[uuid.UUID] = None,
        object_type: Optional[str] = None,
        source_module: Optional[str] = None,
        min_confidence: Optional[float] = None,
        version: Optional[int] = None,
        lifecycle_state: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Execute semantic search query via Qdrant with attribute filtering."""
        return await self.semantic_indexer.semantic_search(
            query=query,
            meeting_id=meeting_id,
            object_type=object_type,
            source_module=source_module,
            min_confidence=min_confidence,
            version=version,
            lifecycle_state=lifecycle_state,
            limit=limit,
        )

    async def hybrid_query(
        self,
        query: str,
        meeting_id: Optional[uuid.UUID] = None,
        object_type: Optional[str] = None,
        source_module: Optional[str] = None,
        min_confidence: Optional[float] = None,
        version: Optional[int] = None,
        lifecycle_state: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid result fusion:
        1. Interpret and execute structured query constraints in PostgreSQL.
        2. Perform semantic retrieval in Qdrant.
        3. Combine results, normalize/score, deduplicate, rank by semantic similarity + confidence, and filter.
        4. Return enriched Knowledge Object dictionaries (never raw Qdrant records).
        """
        cache_key = f"hybrid_query:{hash(query)}:{meeting_id}:{object_type}:{source_module}:{min_confidence}:{version}:{lifecycle_state}:{limit}"
        cached = await self._get_cache(cache_key)
        if cached is not None:
            return cached

        # 1. Semantic retrieval hits
        semantic_hits = await self.semantic_query(
            query=query,
            meeting_id=meeting_id,
            object_type=object_type,
            source_module=source_module,
            min_confidence=min_confidence,
            version=version,
            lifecycle_state=lifecycle_state,
            limit=limit * 2,
        )

        # 2. Structured retrieval hits
        structured_objs = await self.structured_query(
            meeting_id=meeting_id,
            object_type=object_type,
            source_module=source_module,
            min_confidence=min_confidence,
            version=version,
            lifecycle_state=lifecycle_state,
            limit=limit * 2,
        )
        structured_map = {str(obj.id): obj for obj in structured_objs}

        # 3. Fusion & Ranking
        fused_map: Dict[str, Dict[str, Any]] = {}

        # Process semantic hits
        for hit in semantic_hits:
            kid = str(hit.get("knowledge_id"))
            score = hit.get("score", 0.0)
            confidence = hit.get("confidence") or 0.5
            # Combined ranking formula: 70% semantic score + 30% confidence score
            combined_score = (0.7 * score) + (0.3 * confidence)

            fused_map[kid] = {
                "knowledge_id": kid,
                "meeting_id": hit.get("meeting_id"),
                "object_type": hit.get("object_type"),
                "source_module": hit.get("source_module"),
                "title": hit.get("title"),
                "content": hit.get("content"),
                "confidence_score": confidence,
                "version": hit.get("version"),
                "lifecycle_state": hit.get("lifecycle_state"),
                "provenance": hit.get("payload", {}).get("provenance", {}),
                "metadata": hit.get("payload", {}).get("metadata", {}),
                "payload": hit.get("payload", {}).get("payload", {}),
                "relevance_score": combined_score,
                "retrieval_source": "hybrid_semantic",
            }

        # Process structured hits not in semantic
        for kid, obj in structured_map.items():
            if kid not in fused_map:
                confidence = obj.confidence or 0.5
                fused_map[kid] = {
                    "knowledge_id": str(obj.id),
                    "meeting_id": str(obj.meeting_id),
                    "object_type": obj.object_type,
                    "source_module": obj.source_module,
                    "title": obj.title,
                    "content": obj.content,
                    "confidence_score": confidence,
                    "version": obj.version,
                    "lifecycle_state": obj.status,
                    "provenance": obj.provenance if isinstance(obj.provenance, dict) else {},
                    "metadata": obj.payload.get("metadata", {}) if (obj.payload and isinstance(obj.payload, dict)) else {},
                    "payload": obj.payload if isinstance(obj.payload, dict) else {},
                    "relevance_score": 0.5 * confidence, # base score for structured-only match
                    "retrieval_source": "hybrid_structured",
                }

        # Sort by relevance score descending
        fused_results = list(fused_map.values())
        fused_results.sort(key=lambda x: x["relevance_score"], reverse=True)
        final_results = fused_results[:limit]

        await self._set_cache(cache_key, final_results, ttl_seconds=120)
        return final_results
