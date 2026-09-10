"""
Project & ProjectMeeting Repository (Phase 4.22)
PostgreSQL async implementation for Project and ProjectMeeting entity operations.
"""

from typing import List, Optional, Sequence, Tuple
import uuid
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.meeting import Meeting
from app.models.project import Project, ProjectMeeting
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository handling database operations for Project entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Project, session)

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Project], int]:
        """List projects for a tenant with pagination and optional status filter."""
        query = select(Project).where(Project.tenant_id == tenant_id)
        if status:
            query = query.where(Project.status == status)

        count_stmt = select(func.count()).select_from(query.subquery())
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        query = (
            query.options(selectinload(Project.project_meetings))
            .order_by(Project.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def get_with_meetings(self, project_id: uuid.UUID) -> Optional[Project]:
        """Fetch a project with eagerly loaded meeting associations."""
        query = (
            select(Project)
            .where(Project.id == project_id)
            .options(
                selectinload(Project.project_meetings).selectinload(ProjectMeeting.meeting),
            )
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(query)
        return result.scalars().first()


class ProjectMeetingRepository(BaseRepository[ProjectMeeting]):
    """Repository handling project-meeting association mappings."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ProjectMeeting, session)

    async def get_association(self, project_id: uuid.UUID, meeting_id: uuid.UUID) -> Optional[ProjectMeeting]:
        """Find existing association between a project and a meeting."""
        query = (
            select(ProjectMeeting)
            .where(
                ProjectMeeting.project_id == project_id,
                ProjectMeeting.meeting_id == meeting_id,
            )
            .options(selectinload(ProjectMeeting.meeting))
        )
        result = await self.session.execute(query)
        return result.scalars().first()

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[ProjectMeeting], int]:
        """List meetings associated with a project."""
        query = select(ProjectMeeting).where(ProjectMeeting.project_id == project_id)

        count_stmt = select(func.count()).select_from(query.subquery())
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        query = (
            query.options(selectinload(ProjectMeeting.meeting))
            .order_by(ProjectMeeting.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def delete_association(self, project_id: uuid.UUID, meeting_id: uuid.UUID) -> bool:
        """Removes a meeting association from a project."""
        stmt = delete(ProjectMeeting).where(
            ProjectMeeting.project_id == project_id,
            ProjectMeeting.meeting_id == meeting_id,
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def list_projects_for_meeting(self, meeting_id: uuid.UUID) -> List[ProjectMeeting]:
        """Finds all projects a meeting belongs to."""
        query = (
            select(ProjectMeeting)
            .where(ProjectMeeting.meeting_id == meeting_id)
            .options(selectinload(ProjectMeeting.project))
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
