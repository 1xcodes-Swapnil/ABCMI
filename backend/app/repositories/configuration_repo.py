"""
System Configuration Repository
PostgreSQL async implementation for SystemConfiguration entity operations.
"""

from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration import SystemConfiguration
from app.repositories.base import BaseRepository


class ConfigurationRepository(BaseRepository[SystemConfiguration]):
    """Repository handling database operations for SystemConfiguration entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(SystemConfiguration, session)

    async def get_by_key(self, key: str) -> Optional[SystemConfiguration]:
        """Fetch system configuration by unique key."""
        query = select(SystemConfiguration).where(SystemConfiguration.key == key)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def list_by_category(
        self,
        category: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[SystemConfiguration]:
        """List configuration keys belonging to a specific category."""
        query = (
            select(SystemConfiguration)
            .where(SystemConfiguration.category == category)
            .order_by(SystemConfiguration.key.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def upsert_key(
        self,
        key: str,
        value: dict,
        category: str = "general",
        description: Optional[str] = None,
        is_secret: bool = False,
    ) -> SystemConfiguration:
        """Create or update a system configuration key."""
        existing = await self.get_by_key(key)
        if existing is not None:
            existing.value = value
            existing.category = category
            if description is not None:
                existing.description = description
            existing.is_secret = is_secret
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        new_config = SystemConfiguration(
            key=key,
            value=value,
            category=category,
            description=description,
            is_secret=is_secret,
        )
        return await self.create(new_config)
