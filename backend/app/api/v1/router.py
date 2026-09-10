"""
ABCI-MI API Version 1 Main Router
Aggregates all API v1 domain endpoint routers.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    action_items,
    admin,
    auth,
    health,
    knowledge,
    live_sessions,
    meeting_intelligence,
    meetings,
    memory,
    notifications,
    platform_integrations,
    projects,
    query,
    reports,
    translations,
)

api_v1_router = APIRouter()

# Register auth endpoints
api_v1_router.include_router(auth.router)

# Register core health & diagnostic endpoints
api_v1_router.include_router(health.router)

# Register knowledge endpoints
api_v1_router.include_router(knowledge.router)

# Register meeting intake & lifecycle endpoints
api_v1_router.include_router(meetings.router)

# Register live streaming session endpoints
api_v1_router.include_router(live_sessions.router)

# Register platform integration endpoints
api_v1_router.include_router(platform_integrations.router)

# Register memory endpoints
api_v1_router.include_router(memory.router)

# Register meeting report endpoints
api_v1_router.include_router(reports.router)

# Register multilingual translation & derived representation endpoints
api_v1_router.include_router(translations.router)

# Register action items endpoints
api_v1_router.include_router(action_items.router)

# Register meeting intelligence endpoints
api_v1_router.include_router(meeting_intelligence.router)

# Register projects & cross-meeting intelligence endpoints (Phase 4.22)
api_v1_router.include_router(projects.router)

# Register Ask ABCI-MI natural language query endpoint (Phase 4.23)
api_v1_router.include_router(query.router)

# Register notifications & real-time events endpoint (Phase 4.24)
api_v1_router.include_router(notifications.router)

# Register admin, immutable audit, and security endpoints (Phase 4.25)
api_v1_router.include_router(admin.router)
