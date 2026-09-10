"""
ABCI-MI Redis Pub/Sub Distributed Event Bus
Implements asynchronous distributed event publishing, subscription dispatching,
safe failure isolation, production boundary validation, and serialization for domain events.
"""

import json
from enum import Enum
import os
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple, Union
import uuid
import redis.asyncio as aioredis

from app.core.logging import get_logger
from app.infrastructure.redis import get_redis_client
from app.schemas.base import CoreBaseModel

logger = get_logger("events.redis_bus")

EventHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]


class EventDeliveryStatus(str, Enum):
    """
    Explicit status of an event delivery attempt.
    DISTRIBUTED: Delivered to distributed Redis cluster / broker.
    LOCAL_FALLBACK: Redis unavailable; event dispatched only to local in-process handlers.
    FAILED: Event delivery failed completely.
    """
    DISTRIBUTED = "distributed"
    LOCAL_FALLBACK = "local_fallback"
    FAILED = "failed"


class RedisEventBus:
    """
    Asynchronous Redis Pub/Sub Event Bus.
    Provides typed event publishing, multi-channel distribution, subscriber listener management,
    stable event_id injection at publication time, and explicit failure degradation warnings
    when running in local in-memory fallback mode.
    """

    def __init__(self, redis_client: Optional[aioredis.Redis] = None) -> None:
        self._redis_client = redis_client
        self._handlers: Dict[str, Set[EventHandler]] = {}
        self._pubsub_task: Optional[Any] = None
        self._is_connected: bool = False
        self._has_logged_prod_warning: bool = False

    @property
    def is_distributed(self) -> bool:
        """Returns True if the event bus has an active connection to distributed Redis."""
        return self._is_connected

    async def _get_client(self) -> Optional[aioredis.Redis]:
        """Obtain active Redis async client instance safely."""
        if self._redis_client is not None:
            self._is_connected = True
            return self._redis_client
        try:
            client = await get_redis_client()
            if client is not None:
                self._is_connected = True
                return client
            self._is_connected = False
            return None
        except Exception as e:
            self._is_connected = False
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env in {"production", "staging"} and not self._has_logged_prod_warning:
                logger.error(
                    f"[REDIS PRODUCTION BOUNDARY WARNING] Redis cluster connection failed: {e}. "
                    "Operating in LOCAL IN-MEMORY FALLBACK mode. "
                    "Events will NOT be distributed across multiple container / worker processes until Redis is available."
                )
                self._has_logged_prod_warning = True
            else:
                logger.warning(f"Could not connect to Redis for EventBus: {e}. Operating in local fallback.")
            return None

    def _ensure_stable_event_id(self, event: Union[CoreBaseModel, Dict[str, Any], str]) -> Union[CoreBaseModel, Dict[str, Any], str]:
        """
        Guarantees that every domain event possesses a stable event_id at publication time,
        preventing consumer-side synthetic generation.
        """
        if isinstance(event, dict):
            # Check for existing event ID representations
            if not (event.get("event_id") or event.get("event_uuid") or event.get("id")):
                event["event_id"] = str(uuid.uuid4())
            return event
        elif isinstance(event, str):
            try:
                parsed = json.loads(event)
                if isinstance(parsed, dict) and not (parsed.get("event_id") or parsed.get("event_uuid") or parsed.get("id")):
                    parsed["event_id"] = str(uuid.uuid4())
                    return json.dumps(parsed)
            except Exception:
                pass
            return event
        return event

    def _serialize_event(self, event: Union[CoreBaseModel, Dict[str, Any], str]) -> str:
        """Serialize event to JSON string."""
        if isinstance(event, str):
            return event
        if isinstance(event, CoreBaseModel):
            return event.model_dump_json()
        if isinstance(event, dict):
            # Convert UUIDs or datetime to string if present
            def default_serializer(o: Any) -> Any:
                if isinstance(o, uuid.UUID):
                    return str(o)
                if hasattr(o, "isoformat"):
                    return o.isoformat()
                if hasattr(o, "value"):
                    return o.value
                return str(o)

            return json.dumps(event, default=default_serializer)
        return json.dumps({"payload": str(event)})

    async def publish_with_status(
        self,
        channel: str,
        event: Union[CoreBaseModel, Dict[str, Any], str],
    ) -> EventDeliveryStatus:
        """
        Publish an event to a Redis channel and return the explicit delivery status.
        Distinguishes between distributed Redis delivery and local in-process fallback.
        Ensures stable event_id is embedded prior to serialization.
        """
        prepared_event = self._ensure_stable_event_id(event)
        try:
            client = await self._get_client()
            if client is None:
                logger.warning(
                    f"[EVENT BUS LOCAL FALLBACK] Redis unavailable; dispatching event to local in-process subscribers on channel '{channel}'"
                )
                await self._dispatch_local(channel, prepared_event)
                return EventDeliveryStatus.LOCAL_FALLBACK

            payload_str = self._serialize_event(prepared_event)
            await client.publish(channel, payload_str)
            logger.debug(f"Event published to distributed Redis channel '{channel}': {payload_str[:120]}...")

            # Also notify any in-process subscribers
            await self._dispatch_local(channel, prepared_event)
            return EventDeliveryStatus.DISTRIBUTED

        except Exception as e:
            self._is_connected = False
            logger.warning(f"Failed to publish event to Redis channel '{channel}': {e}. Using local in-process fallback.")
            try:
                await self._dispatch_local(channel, prepared_event)
                return EventDeliveryStatus.LOCAL_FALLBACK
            except Exception as local_ex:
                logger.error(f"Local in-process fallback also failed on channel '{channel}': {local_ex}")
                return EventDeliveryStatus.FAILED

    async def publish(
        self,
        channel: str,
        event: Union[CoreBaseModel, Dict[str, Any], str],
    ) -> bool:
        """
        Publish an event to a Redis channel.
        Returns True if successfully dispatched to distributed Redis, False if degraded to local fallback.
        Guarantees that an unreachable Redis server never raises unhandled exceptions to callers.
        """
        status = await self.publish_with_status(channel, event)
        return status == EventDeliveryStatus.DISTRIBUTED

    async def _dispatch_local(
        self,
        channel: str,
        event: Union[CoreBaseModel, Dict[str, Any], str],
    ) -> None:
        """Dispatch event to in-process handlers registered on this event bus."""
        handlers = self._handlers.get(channel, set())
        if not handlers:
            return

        # Prepare parsed dict
        if isinstance(event, CoreBaseModel):
            event_dict = event.model_dump()
        elif isinstance(event, dict):
            event_dict = event
        else:
            try:
                event_dict = json.loads(event)
            except Exception:
                event_dict = {"raw": event}

        for handler in list(handlers):
            try:
                await handler(event_dict)
            except Exception as ex:
                logger.error(f"Error executing in-process event handler for channel '{channel}': {ex}")

    def subscribe(self, channel: str, handler: EventHandler) -> None:
        """Register an in-process handler for events published on a channel."""
        if channel not in self._handlers:
            self._handlers[channel] = set()
        self._handlers[channel].add(handler)

    def unsubscribe(self, channel: str, handler: EventHandler) -> None:
        """Unregister an in-process handler."""
        if channel in self._handlers:
            self._handlers[channel].discard(handler)
            if not self._handlers[channel]:
                del self._handlers[channel]

    def get_status(self) -> Dict[str, Any]:
        """Returns runtime operational status of the Event Bus for health and diagnostics."""
        return {
            "mode": "distributed" if self._is_connected else "local_fallback",
            "is_distributed": self._is_connected,
            "registered_channels": list(self._handlers.keys()),
            "total_handlers": sum(len(h) for h in self._handlers.values()),
        }

    async def verify_production_readiness(self) -> Tuple[bool, Optional[str]]:
        """
        Explicitly checks if Redis is reachable for multi-worker distributed event guarantees.
        """
        client = await self._get_client()
        if client is None:
            return False, "Redis connection could not be established; event bus running in local in-memory fallback mode."
        try:
            await client.ping()
            return True, None
        except Exception as e:
            return False, f"Redis ping verification failed: {str(e)}"



# Singleton / default event bus instance
_default_event_bus: Optional[RedisEventBus] = None


def get_event_bus() -> RedisEventBus:
    """Retrieve or initialize the default RedisEventBus instance."""
    global _default_event_bus
    if _default_event_bus is None:
        _default_event_bus = RedisEventBus()
    return _default_event_bus
