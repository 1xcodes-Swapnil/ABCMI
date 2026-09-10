"""
Translation & Derived Representation Service (Phase 4.20)
Orchestrates multilingual translation workflows, canonical source preservation,
idempotent representation caching, verification routing, and Redis event bus publishing.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.translation_engine import TranslationEngine, translation_provider_registry
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus
from app.models.knowledge_object import KnowledgeObject
from app.models.meeting import Meeting
from app.models.transcript import TranscriptSegment
from app.models.translation import DerivedTranslation
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.transcript_repo import TranscriptSegmentRepository
from app.schemas.translation import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_REPRESENTATION_TYPES,
    TranslationRegenerateRequest,
    TranslationRequest,
)

logger = get_logger("services.translation_service")


class TranslationService:
    """
    Application service managing multilingual translations and derived representations.
    Ensures that canonical meeting knowledge and transcripts are never overwritten.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.meeting_repo = MeetingRepository(db)
        self.ko_repo = KnowledgeObjectRepository(db)
        self.segment_repo = TranscriptSegmentRepository(db)
        self.engine = TranslationEngine(translation_provider_registry)
        self.event_bus = RedisEventBus()

    def _validate_auth(self, auth_context: Dict[str, Any], meeting: Optional[Meeting] = None) -> None:
        """Enforces tenant isolation and authentication."""
        if not auth_context or not auth_context.get("authenticated", False):
            raise ForbiddenException(message="Authentication required", code="UNAUTHORIZED")
        meeting_tenant = getattr(meeting, "tenant_id", None) if meeting else None
        if meeting_tenant:
            user_tenant = auth_context.get("tenant_id")
            if user_tenant and user_tenant != meeting_tenant:
                raise ForbiddenException(
                    message="Access denied: Cross-tenant operation forbidden",
                    code="FORBIDDEN_CROSS_TENANT",
                )

    async def generate_translations(
        self,
        meeting_id: uuid.UUID,
        request: TranslationRequest,
        auth_context: Dict[str, Any],
    ) -> List[DerivedTranslation]:
        """
        Generates translated derived representations for transcripts and knowledge objects.
        Executes idempotently and preserves canonical source objects.
        """
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        self._validate_auth(auth_context, meeting)

        target_lang = request.target_language.strip().lower()
        if target_lang not in SUPPORTED_LANGUAGES:
            raise BadRequestException(
                message=f"Unsupported target language '{target_lang}'",
                code="UNSUPPORTED_LANGUAGE",
            )

        source_lang = (
            request.source_language
            or getattr(meeting, "language", None)
            or "en"
        ).strip().lower()

        rep_types = (
            set(request.representation_types)
            if request.representation_types
            else SUPPORTED_REPRESENTATION_TYPES
        )

        conf_threshold = request.confidence_threshold if request.confidence_threshold is not None else 0.75
        correlation_id = request.correlation_id or str(uuid.uuid4())
        tenant_id = auth_context.get("tenant_id") or getattr(meeting, "tenant_id", None)

        # Emit TranslationRequested event
        await self.event_bus.publish(
            "TranslationRequested",
            {
                "meeting_id": str(meeting_id),
                "tenant_id": str(tenant_id) if tenant_id else None,
                "target_language": target_lang,
                "source_language": source_lang,
                "representation_types": list(rep_types),
                "correlation_id": correlation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        results: List[DerivedTranslation] = []

        # 1. Process Transcript Segments if requested
        if "transcript" in rep_types:
            segments = await self.segment_repo.list_by_meeting(meeting_id, limit=1000)
            if request.source_object_ids:
                allowed_ids = set(request.source_object_ids)
                segments = [s for s in segments if s.id in allowed_ids]

            for seg in segments:
                if not seg.text or not seg.text.strip():
                    continue

                # Idempotency Check
                stmt = select(DerivedTranslation).where(
                    DerivedTranslation.meeting_id == meeting_id,
                    DerivedTranslation.source_segment_id == seg.id,
                    DerivedTranslation.source_language == (seg.language or source_lang),
                    DerivedTranslation.target_language == target_lang,
                    DerivedTranslation.representation_type == "transcript",
                    DerivedTranslation.source_version == 1,
                )
                existing_res = await self.db.execute(stmt)
                existing = existing_res.scalars().first()

                if existing:
                    results.append(existing)
                    continue

                seg_source_lang = (seg.language or source_lang).strip().lower()

                engine_res = await self.engine.translate(
                    text=seg.text,
                    target_language=target_lang,
                    source_language=seg_source_lang,
                    confidence_threshold=conf_threshold,
                    metadata={
                        "source_segment_id": str(seg.id),
                        "source_segments": [str(seg.id)],
                        "source_intervals": [{"start_ms": seg.start_time_ms, "end_ms": seg.end_time_ms}],
                    },
                    correlation_id=correlation_id,
                )

                dt = DerivedTranslation(
                    meeting_id=meeting_id,
                    tenant_id=str(tenant_id) if tenant_id else None,
                    source_object_id=None,
                    source_segment_id=seg.id,
                    representation_type="transcript",
                    source_language=seg_source_lang,
                    target_language=target_lang,
                    original_text=seg.text,
                    translated_text=engine_res["translated_text"],
                    confidence=engine_res["confidence"],
                    is_low_confidence=engine_res["is_low_confidence"],
                    requires_verification=engine_res["requires_verification"],
                    status="active",
                    source_version=1,
                    version=1,
                    speaker_label=seg.speaker_label,
                    start_time_ms=seg.start_time_ms,
                    end_time_ms=seg.end_time_ms,
                    provenance=engine_res["provenance"],
                    correlation_id=correlation_id,
                )
                self.db.add(dt)
                results.append(dt)

                # Emit events
                await self.event_bus.publish(
                    "DerivedRepresentationGenerated",
                    {
                        "translation_id": str(dt.id),
                        "meeting_id": str(meeting_id),
                        "representation_type": "transcript",
                        "target_language": target_lang,
                        "confidence": dt.confidence,
                        "correlation_id": correlation_id,
                    },
                )
                if dt.requires_verification:
                    await self.event_bus.publish(
                        "TranslationVerificationRequired",
                        {
                            "translation_id": str(dt.id),
                            "meeting_id": str(meeting_id),
                            "representation_type": "transcript",
                            "confidence": dt.confidence,
                            "correlation_id": correlation_id,
                        },
                    )

        # 2. Process Knowledge Objects
        ko_types = rep_types.intersection({
            "summary", "topic", "decision", "action_item", "fact", "hypothesis", "transcript_insight"
        })
        if ko_types:
            all_kos = await self.ko_repo.list_by_meeting(meeting_id, limit=500)
            target_kos = [k for k in all_kos if k.object_type in ko_types]
            if request.source_object_ids:
                allowed_ids = set(request.source_object_ids)
                target_kos = [k for k in target_kos if k.id in allowed_ids]

            for ko in target_kos:
                if not ko.content or not ko.content.strip():
                    continue

                # Idempotency Check
                stmt = select(DerivedTranslation).where(
                    DerivedTranslation.meeting_id == meeting_id,
                    DerivedTranslation.source_object_id == ko.id,
                    DerivedTranslation.source_language == source_lang,
                    DerivedTranslation.target_language == target_lang,
                    DerivedTranslation.representation_type == ko.object_type,
                    DerivedTranslation.source_version == ko.version,
                )
                existing_res = await self.db.execute(stmt)
                existing = existing_res.scalars().first()

                if existing:
                    results.append(existing)
                    continue

                engine_res = await self.engine.translate(
                    text=ko.content,
                    target_language=target_lang,
                    source_language=source_lang,
                    confidence_threshold=conf_threshold,
                    metadata={
                        "source_object_id": str(ko.id),
                        "object_type": ko.object_type,
                    },
                    correlation_id=correlation_id,
                )

                dt = DerivedTranslation(
                    meeting_id=meeting_id,
                    tenant_id=str(tenant_id) if tenant_id else None,
                    source_object_id=ko.id,
                    source_segment_id=None,
                    representation_type=ko.object_type,
                    source_language=source_lang,
                    target_language=target_lang,
                    original_text=ko.content,
                    translated_text=engine_res["translated_text"],
                    confidence=engine_res["confidence"],
                    is_low_confidence=engine_res["is_low_confidence"],
                    requires_verification=engine_res["requires_verification"],
                    status="active",
                    source_version=ko.version,
                    version=1,
                    speaker_label=None,
                    start_time_ms=None,
                    end_time_ms=None,
                    provenance=engine_res["provenance"],
                    correlation_id=correlation_id,
                )
                self.db.add(dt)
                results.append(dt)

                # Emit events
                await self.event_bus.publish(
                    "DerivedRepresentationGenerated",
                    {
                        "translation_id": str(dt.id),
                        "meeting_id": str(meeting_id),
                        "representation_type": ko.object_type,
                        "target_language": target_lang,
                        "confidence": dt.confidence,
                        "correlation_id": correlation_id,
                    },
                )
                if dt.requires_verification:
                    await self.event_bus.publish(
                        "TranslationVerificationRequired",
                        {
                            "translation_id": str(dt.id),
                            "meeting_id": str(meeting_id),
                            "representation_type": ko.object_type,
                            "confidence": dt.confidence,
                            "correlation_id": correlation_id,
                        },
                    )

        await self.db.commit()

        # Emit TranslationGenerated summary event
        await self.event_bus.publish(
            "TranslationGenerated",
            {
                "meeting_id": str(meeting_id),
                "target_language": target_lang,
                "count": len(results),
                "correlation_id": correlation_id,
            },
        )

        return results

    async def list_translations(
        self,
        meeting_id: uuid.UUID,
        target_language: Optional[str] = None,
        representation_type: Optional[str] = None,
        requires_verification: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[DerivedTranslation], int]:
        """Lists translations with filtering and pagination."""
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting '{meeting_id}' not found", code="MEETING_NOT_FOUND")

        if auth_context:
            self._validate_auth(auth_context, meeting)

        query = select(DerivedTranslation).where(DerivedTranslation.meeting_id == meeting_id)

        if target_language:
            query = query.where(DerivedTranslation.target_language == target_language.strip().lower())
        if representation_type:
            query = query.where(DerivedTranslation.representation_type == representation_type.strip().lower())
        if requires_verification is not None:
            query = query.where(DerivedTranslation.requires_verification == requires_verification)

        # Count total
        count_stmt = select(func.count()).select_from(query.subquery())
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar() or 0

        # Fetch page
        query = query.order_by(DerivedTranslation.created_at.desc()).offset(offset).limit(limit)
        items_res = await self.db.execute(query)
        items = list(items_res.scalars().all())

        return items, total

    async def get_translation(
        self,
        translation_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> DerivedTranslation:
        """Retrieves a single derived translation by ID."""
        stmt = select(DerivedTranslation).where(DerivedTranslation.id == translation_id)
        res = await self.db.execute(stmt)
        dt = res.scalars().first()
        if not dt:
            raise NotFoundException(message=f"Translation '{translation_id}' not found", code="TRANSLATION_NOT_FOUND")

        meeting = await self.meeting_repo.get_by_id(dt.meeting_id)
        self._validate_auth(auth_context, meeting)

        return dt

    async def regenerate_translation(
        self,
        translation_id: uuid.UUID,
        request: TranslationRegenerateRequest,
        auth_context: Dict[str, Any],
    ) -> DerivedTranslation:
        """Regenerates a translation deterministically while maintaining version lineage."""
        dt = await self.get_translation(translation_id, auth_context)

        target_lang = (request.target_language or dt.target_language).strip().lower()
        correlation_id = request.correlation_id or dt.correlation_id or str(uuid.uuid4())

        engine_res = await self.engine.translate(
            text=dt.original_text,
            target_language=target_lang,
            source_language=dt.source_language,
            metadata={
                "confidence_override": request.confidence_override,
                "source_object_id": str(dt.source_object_id) if dt.source_object_id else None,
                "source_segment_id": str(dt.source_segment_id) if dt.source_segment_id else None,
            },
            correlation_id=correlation_id,
        )

        dt.target_language = target_lang
        dt.translated_text = engine_res["translated_text"]
        dt.confidence = engine_res["confidence"]
        dt.is_low_confidence = engine_res["is_low_confidence"]
        dt.requires_verification = engine_res["requires_verification"]
        dt.version += 1
        dt.provenance = engine_res["provenance"]
        dt.correlation_id = correlation_id

        await self.db.commit()
        await self.db.refresh(dt)

        await self.event_bus.publish(
            "DerivedRepresentationGenerated",
            {
                "translation_id": str(dt.id),
                "meeting_id": str(dt.meeting_id),
                "representation_type": dt.representation_type,
                "target_language": dt.target_language,
                "version": dt.version,
                "confidence": dt.confidence,
                "correlation_id": correlation_id,
            },
        )

        if dt.requires_verification:
            await self.event_bus.publish(
                "TranslationVerificationRequired",
                {
                    "translation_id": str(dt.id),
                    "meeting_id": str(dt.meeting_id),
                    "representation_type": dt.representation_type,
                    "confidence": dt.confidence,
                    "correlation_id": correlation_id,
                },
            )

        return dt
