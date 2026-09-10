"""
Knowledge Object Repository
PostgreSQL async implementation for KnowledgeObject persistence foundation.
Provides basic CRUD access without implementing domain/business logic.
"""

from typing import Optional, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_object import KnowledgeObject
from app.repositories.base import BaseRepository


class KnowledgeObjectRepository(BaseRepository[KnowledgeObject]):
    """Repository handling basic persistence operations for KnowledgeObject entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(KnowledgeObject, session)

    async def list_by_meeting(
        self,
        meeting_id: uuid.UUID,
        object_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[KnowledgeObject]:
        """List knowledge objects for a meeting with optional type filtering."""
        query = select(KnowledgeObject).where(KnowledgeObject.meeting_id == meeting_id)
        if object_type:
            query = query.where(KnowledgeObject.object_type == object_type)
        query = query.order_by(KnowledgeObject.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def list_by_parent(
        self,
        parent_id: uuid.UUID,
    ) -> Sequence[KnowledgeObject]:
        """Fetch derived knowledge objects descended from a parent version."""
        query = (
            select(KnowledgeObject)
            .where(KnowledgeObject.parent_id == parent_id)
            .order_by(KnowledgeObject.version.asc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def list_active(
        self,
        meeting_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[KnowledgeObject]:
        """List active knowledge objects in a meeting."""
        return await self.list_by_type_and_status(
            meeting_id=meeting_id,
            status="active",
            skip=skip,
            limit=limit,
        )

    async def get_by_qdrant_point_id(
        self,
        point_id: str,
    ) -> Optional[KnowledgeObject]:
        """Fetch a single knowledge object matching a Qdrant vector point ID."""
        query = select(KnowledgeObject).where(KnowledgeObject.qdrant_point_id == point_id)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def list_by_type_and_status(
        self,
        meeting_id: uuid.UUID,
        object_type: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[KnowledgeObject]:
        """List knowledge objects filtered by meeting ID, optional object type, and optional status."""
        query = select(KnowledgeObject).where(KnowledgeObject.meeting_id == meeting_id)
        if object_type:
            query = query.where(KnowledgeObject.object_type == object_type)
        if status:
            query = query.where(KnowledgeObject.status == status)
        query = query.order_by(KnowledgeObject.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get(self, id: uuid.UUID) -> Optional[KnowledgeObject]:
        """Alias for get_by_id."""
        return await self.get_by_id(id)

    async def get_by_meeting(
        self,
        meeting_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[KnowledgeObject]:
        """Get knowledge objects by meeting ID (snake_case alias)."""
        return await self.list_by_meeting(meeting_id, skip=skip, limit=limit)

    async def getByMeeting(
        self,
        meeting_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[KnowledgeObject]:
        """Get knowledge objects by meeting ID."""
        return await self.list_by_meeting(meeting_id, skip=skip, limit=limit)

    async def getByType(
        self,
        object_type: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[KnowledgeObject]:
        """Get knowledge objects by object type."""
        query = select(KnowledgeObject).where(KnowledgeObject.object_type == object_type)
        query = query.order_by(KnowledgeObject.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def getBySource(
        self,
        source_module: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[KnowledgeObject]:
        """Get knowledge objects by source module."""
        query = select(KnowledgeObject).where(KnowledgeObject.source_module == source_module)
        query = query.order_by(KnowledgeObject.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def getByVersion(
        self,
        meeting_id: uuid.UUID,
        version: int,
    ) -> Sequence[KnowledgeObject]:
        """Get knowledge objects by meeting ID and version."""
        query = select(KnowledgeObject).where(
            KnowledgeObject.meeting_id == meeting_id,
            KnowledgeObject.version == version,
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def archive(
        self,
        id: uuid.UUID,
    ) -> Optional[KnowledgeObject]:
        """Archive (deprecated status) a knowledge object."""
        ko = await self.get_by_id(id)
        if ko:
            ko.status = "deprecated"
            await self.session.commit()
            await self.session.refresh(ko)
        return ko

    async def get_history(
        self,
        object_id: uuid.UUID,
    ) -> Sequence[KnowledgeObject]:
        """
        Retrieve the chronological version history chain for a knowledge object.
        Traverses upstream ancestor links via parent_id to reconstruct the lineage root to leaf.
        """
        chain: list[KnowledgeObject] = []
        current: Optional[KnowledgeObject] = await self.get_by_id(object_id)
        
        visited = set()
        while current is not None and current.id not in visited:
            visited.add(current.id)
            chain.append(current)
            if current.parent_id:
                current = await self.get_by_id(current.parent_id)
            else:
                break

        # Return ascending by version / chronological order
        chain.reverse()
        return chain
