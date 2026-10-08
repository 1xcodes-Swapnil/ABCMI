"""Consume existing Redis domain channels into scoped persisted notifications."""
import asyncio
import json
import uuid
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.logging import get_logger
from app.infrastructure.database import init_database
from app.infrastructure.redis import get_redis_client
from app.models.meeting import Meeting
from app.models.project import Project
from app.services.notification_service import NotificationService

logger = get_logger("notifications.listener")
PATTERNS = ("Meeting*", "Project*", "ActionItem*", "Translation*", "Query*", "Report*",
            "DerivedRepresentationGenerated", "events:meetings:*", "events:reports:*", "abci.query.*", "abci.events")


async def consume_notification_event(channel: str, event: dict):
    if not isinstance(event, dict) or not event.get("event_id"):
        return  # Never fabricate historical event identity.
    sessions = async_sessionmaker(init_database(), expire_on_commit=False)
    async with sessions() as db:
        data = dict(event)
        data.setdefault("event_type", channel)
        scope = None
        if data.get("meeting_id"):
            scope = await db.get(Meeting, uuid.UUID(str(data["meeting_id"])))
            if scope is None:
                data.setdefault("resource_id", str(data["meeting_id"]))
                data["meeting_id"] = None
        elif data.get("project_id"):
            scope = await db.get(Project, uuid.UUID(str(data["project_id"])))
            if scope is None:
                data.setdefault("resource_id", str(data["project_id"]))
                data["project_id"] = None
        if scope is not None:
            if data.get("tenant_id") and str(data["tenant_id"]) != str(scope.tenant_id):
                raise ValueError("Event tenant differs from persisted resource scope")
            data["tenant_id"] = scope.tenant_id
        if not data.get("tenant_id"):
            return
        await NotificationService(db).consume_event(data)


async def listen_for_notifications():
    while True:
        pubsub = None
        try:
            client = await get_redis_client()
            if client is None:
                raise ConnectionError("Redis unavailable")
            pubsub = client.pubsub()
            await pubsub.psubscribe(*PATTERNS)
            logger.info("Redis notification listener AVAILABLE")
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                try:
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode("utf-8")
                    await consume_notification_event(channel, json.loads(message["data"]))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Notification event rejected (%s); source event remains unacknowledged", type(exc).__name__)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Redis notification listener FALLBACK (%s); distributed delivery unavailable, retry in 10s", type(exc).__name__)
            await asyncio.sleep(10)
        finally:
            if pubsub is not None:
                await pubsub.aclose()
