"""
ABCI-MI Generic Repository Interface & Base SQLAlchemy Implementation
Provides standard CRUD abstraction over async SQLAlchemy sessions.
"""

from typing import Any, Generic, List, Optional, Sequence, Type, TypeVar
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    """
    Generic asynchronous repository providing type-safe CRUD operations.
    Concrete domain repositories inherit from this class.
    """

    def __init__(self, model: Type[T], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, entity_id: uuid.UUID) -> Optional[T]:
        """Fetch a single record by its UUID primary key."""
        result = await self.session.get(self.model, entity_id)
        return result

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> Sequence[T]:
        """Fetch multiple records with optional filters and pagination."""
        query = select(self.model)
        for field, value in filters.items():
            if value is not None and hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count(self, **filters: Any) -> int:
        """Count total records matching optional filter criteria."""
        query = select(func.count(self.model.id))
        for field, value in filters.items():
            if value is not None and hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)
        result = await self.session.execute(query)
        count_val = result.scalar()
        return count_val if count_val is not None else 0

    async def create(self, entity: T) -> T:
        """Persist a new entity into the database."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def update(self, entity: T) -> T:
        """Update an existing entity and refresh its state."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity_id: uuid.UUID) -> bool:
        """Delete an entity by its UUID. Returns True if deleted, False if not found."""
        entity = await self.get_by_id(entity_id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True

    async def exists(self, entity_id: uuid.UUID) -> bool:
        """Check if an entity exists by its UUID primary key."""
        query = select(func.count(self.model.id)).where(self.model.id == entity_id)
        result = await self.session.execute(query)
        count_val = result.scalar()
        return bool(count_val and count_val > 0)
