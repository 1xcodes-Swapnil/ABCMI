"""
User Repository
PostgreSQL async implementation for User entity operations.
"""

from typing import Optional, Sequence, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository handling database operations for User entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    @staticmethod
    def tenant_membership(tenant_id: str):
        from app.models.meeting import Meeting
        from app.models.participant import Participant
        hosted = select(Meeting.id).where(Meeting.host_id == User.id, Meeting.tenant_id == tenant_id).exists()
        participant = select(Participant.id).join(Meeting, Meeting.id == Participant.meeting_id).where(
            Participant.user_id == User.id, Meeting.tenant_id == tenant_id).exists()
        return (User.login_tenant_id == tenant_id) | hosted | participant

    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch user by exact email address (case-insensitive search)."""
        query = select(User).where(User.email == email.lower().strip())
        result = await self.session.execute(query)
        return result.scalars().first()

    async def list_active(self, skip: int = 0, limit: int = 100) -> Sequence[User]:
        """Fetch all active user accounts based on status column."""
        query = (
            select(User)
            .where(User.status == "active")
            .order_by(User.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def list_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[User]:
        """Fetch users by explicit account status."""
        query = (
            select(User)
            .where(User.status == status)
            .order_by(User.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def list_users_filtered(
        self,
        role: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
        tenant_id: Optional[str] = None,
    ) -> Tuple[Sequence[User], int]:
        """
        List users with filtering across role, status, and full text search on email/name.
        Returns a tuple of (users, total_count).
        """
        base_filters = []
        if tenant_id is not None:
            base_filters.append(self.tenant_membership(tenant_id))
        if role:
            base_filters.append(User.role == role.lower().strip())
        if status:
            base_filters.append(User.status == status.lower().strip())
        if search:
            search_term = f"%{search.lower().strip()}%"
            base_filters.append(
                (func.lower(User.email).like(search_term)) | (func.lower(User.full_name).like(search_term))
            )

        # Count total
        count_query = select(func.count(User.id))
        if base_filters:
            count_query = count_query.where(*base_filters)
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        # Query items
        items_query = select(User)
        if base_filters:
            items_query = items_query.where(*base_filters)
        items_query = items_query.order_by(User.created_at.desc()).offset(skip).limit(limit)

        items_result = await self.session.execute(items_query)
        items = items_result.scalars().all()

        return items, total
