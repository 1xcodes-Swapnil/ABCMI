"""
Live Meeting Real Ingestion Service
Handles ingestion of real transcript segments, live participant presence tracking,
temporal synchronization, idempotency, multi-tenant isolation, Blackboard updates,
and SKW Knowledge Object synthesis.
"""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus, get_event_bus
from app.models.knowledge_object import KnowledgeObject
from app.models.live_session import LiveSession
from app.models.meeting import Meeting
from app.models.participant import Participant
from app.models.transcript import Transcript, TranscriptSegment
from app.orchestration.blackboard_event_consumer import BlackboardEventConsumer
from app.schemas.platform_integration import LiveTranscriptIngestRequest

logger = get_logger(__name__)


class LiveMeetingIngestionService:
    """
    Ingests, normalizes, and routes real live meeting transcripts, participant updates,
    and streaming audio events through the ABCI-MI core intelligence pipeline.
    """

    def __init__(self, db: AsyncSession, event_bus: Optional[RedisEventBus] = None):
        self.db = db
        self.event_bus = event_bus or get_event_bus()
        self.blackboard_consumer = BlackboardEventConsumer(event_bus=self.event_bus)
        self._processed_event_hashes: set = set()

    async def ingest_transcript_segment(
        self,
        meeting_id: uuid.UUID,
        payload: LiveTranscriptIngestRequest,
        auth_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Processes a real transcript segment utterance received from Google Meet or Teams.
        Preserves genuine participant identity, offsets, provenance, and triggers SKW knowledge synthesis.
        """
        # Verify meeting existence
        stmt = select(Meeting).where(Meeting.id == meeting_id)
        result = await self.db.execute(stmt)
        meeting = result.scalars().first()
        if not meeting:
            raise NotFoundException(message=f"Meeting {meeting_id} not found", code="MEETING_NOT_FOUND")

        tenant_id = auth_context.get("tenant_id", "default")

        # Compute idempotency hash
        event_key = payload.event_id or f"{payload.external_meeting_id}:{payload.sequence}:{payload.start_time_ms}:{payload.text[:30]}"
        event_hash = hashlib.sha256(f"{tenant_id}:{event_key}".encode("utf-8")).hexdigest()
        if event_hash in self._processed_event_hashes:
            logger.info("Ignoring duplicate transcript segment event %s", event_key)
            return {"status": "duplicate_ignored", "event_id": payload.event_id}

        self._processed_event_hashes.add(event_hash)

        # 1. Resolve or create Participant record if speaker information provided
        participant_id = None
        if payload.speaker_name or payload.speaker_id:
            participant_stmt = select(Participant).where(
                Participant.meeting_id == meeting_id,
                (Participant.speaker_label == payload.speaker_id) | (Participant.display_name == payload.speaker_name),
            )
            p_res = await self.db.execute(participant_stmt)
            participant = p_res.scalars().first()
            if not participant:
                participant = Participant(
                    meeting_id=meeting_id,
                    display_name=payload.speaker_name or (f"Speaker {payload.speaker_id}" if payload.speaker_id else "Attendee"),
                    email=payload.speaker_email,
                    speaker_label=payload.speaker_id,
                    role="attendee",
                    is_active=True,
                    joined_at=datetime.now(timezone.utc),
                )
                self.db.add(participant)
                await self.db.flush()
                await self.db.refresh(participant)

                # Publish ParticipantJoined event
                await self.event_bus.publish(
                    f"events:meetings:{meeting_id}:participants",
                    {
                        "event_type": "ParticipantJoined",
                        "meeting_id": str(meeting_id),
                        "participant_id": str(participant.id),
                        "display_name": participant.display_name,
                        "email": participant.email,
                        "speaker_label": participant.speaker_label,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            participant_id = participant.id

        # 2. Ensure parent Transcript record exists
        transcript_stmt = select(Transcript).where(Transcript.meeting_id == meeting_id)
        t_res = await self.db.execute(transcript_stmt)
        transcript = t_res.scalars().first()
        if not transcript:
            transcript = Transcript(
                meeting_id=meeting_id,
                full_text=payload.text,
                detected_language=payload.language or "en",
                is_final=False,
            )
            self.db.add(transcript)
            await self.db.flush()
            await self.db.refresh(transcript)
        else:
            if transcript.full_text:
                transcript.full_text = f"{transcript.full_text} {payload.text}"
            else:
                transcript.full_text = payload.text

        # 3. Create TranscriptSegment record
        segment = TranscriptSegment(
            meeting_id=meeting_id,
            participant_id=participant_id,
            speaker_label=payload.speaker_id or (payload.speaker_name if payload.speaker_name else "Unknown"),
            start_time_ms=payload.start_time_ms,
            end_time_ms=payload.end_time_ms,
            language=payload.language or "en",
            original_text=payload.text,
            confidence=payload.confidence,
            is_final=payload.is_final,
            sequence_number=payload.sequence,
            words_payload=[{
                "text": payload.text,
                "start_ms": payload.start_time_ms,
                "end_ms": payload.end_time_ms,
                "confidence": payload.confidence,
                "source": payload.source,
            }],
        )
        self.db.add(segment)

        # 4. Update LiveSession if present
        session_stmt = select(LiveSession).where(LiveSession.meeting_id == meeting_id)
        s_res = await self.db.execute(session_stmt)
        live_session = s_res.scalars().first()
        if live_session:
            live_session.last_event_at = datetime.now(timezone.utc)
            live_session.last_activity_at = datetime.now(timezone.utc)
            live_session.accepted_chunks_count += 1
            live_session.latest_sequence_number = max(live_session.latest_sequence_number, payload.sequence)

        # 5. Extract SKW knowledge objects if actionable intelligence patterns are present in real utterance
        knowledge_objects_created = await self._synthesize_live_knowledge(
            meeting_id=meeting_id,
            text=payload.text,
            speaker_name=payload.speaker_name,
            timestamp_ms=payload.start_time_ms,
            tenant_id=tenant_id,
        )

        await self.db.commit()
        await self.db.refresh(segment)

        # 6. Publish Redis Events
        segment_event_payload = {
            "event_type": "LiveTranscriptSegmentReceived",
            "meeting_id": str(meeting_id),
            "segment_id": str(segment.id),
            "speaker_id": payload.speaker_id,
            "speaker_name": payload.speaker_name,
            "text": payload.text,
            "language": payload.language,
            "start_time_ms": payload.start_time_ms,
            "end_time_ms": payload.end_time_ms,
            "confidence": payload.confidence,
            "sequence": payload.sequence,
            "is_final": payload.is_final,
            "source": payload.source,
            "event_id": payload.event_id or str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": payload.correlation_id,
        }
        await self.event_bus.publish(f"events:meetings:{meeting_id}:transcript", segment_event_payload)
        await self.event_bus.publish(f"events:meetings:{meeting_id}:live", segment_event_payload)

        # Also publish LiveTranscriptUpdated event
        await self.event_bus.publish(
            f"events:meetings:{meeting_id}:transcript_updated",
            {
                "event_type": "LiveTranscriptUpdated",
                "meeting_id": str(meeting_id),
                "full_transcript_length": len(transcript.full_text or ""),
                "latest_segment_id": str(segment.id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # 7. Feed into Blackboard event consumer
        await self.blackboard_consumer.handle_event({
            "event_id": str(uuid.uuid4()),
            "meeting_id": str(meeting_id),
            "event_type": "SKW_TRANSCRIPT_CHUNK_INGESTED",
            "payload": segment_event_payload,
        })

        return {
            "status": "ingested",
            "segment_id": str(segment.id),
            "meeting_id": str(meeting_id),
            "sequence": payload.sequence,
            "text": payload.text,
            "speaker_name": payload.speaker_name,
            "start_time_ms": payload.start_time_ms,
            "end_time_ms": payload.end_time_ms,
            "knowledge_objects_created": len(knowledge_objects_created),
        }

    async def _synthesize_live_knowledge(
        self,
        meeting_id: uuid.UUID,
        text: str,
        speaker_name: Optional[str],
        timestamp_ms: int,
        tenant_id: str,
    ) -> List[KnowledgeObject]:
        """
        Inspects live utterance text for action items, decisions, topics, or insights
        and generates persistent SKW KnowledgeObjects.
        """
        created: List[KnowledgeObject] = []
        lower_text = text.lower()

        # Action item detection heuristic
        action_keywords = ["action item", "todo", "i will", "we will", "please make sure", "assigned to", "follow up with", "need to"]
        if any(kw in lower_text for kw in action_keywords):
            ko = KnowledgeObject(
                meeting_id=meeting_id,
                object_type="action_item",
                title=f"Action Item: {text[:60]}...",
                content={
                    "task": text,
                    "assignee": speaker_name or "Unassigned",
                    "status": "pending",
                    "detected_at_offset_ms": timestamp_ms,
                },
                status="active",
                confidence=0.88,
                version=1,
                provenance={"source": "live_transcript", "speaker": speaker_name, "tenant_id": tenant_id},
            )
            self.db.add(ko)
            created.append(ko)

        # Decision detection heuristic
        decision_keywords = ["decided that", "agreed that", "we decided", "decision is", "we agreed", "conclusion is"]
        if any(kw in lower_text for kw in decision_keywords):
            ko = KnowledgeObject(
                meeting_id=meeting_id,
                object_type="decision",
                title=f"Decision: {text[:60]}...",
                content={
                    "decision": text,
                    "agreed_by": speaker_name or "Meeting participants",
                    "detected_at_offset_ms": timestamp_ms,
                },
                status="active",
                confidence=0.92,
                version=1,
                provenance={"source": "live_transcript", "speaker": speaker_name, "tenant_id": tenant_id},
            )
            self.db.add(ko)
            created.append(ko)

        # Topic detection heuristic
        topic_keywords = ["let's discuss", "moving on to", "agenda item", "focus on", "talking about"]
        if any(kw in lower_text for kw in topic_keywords):
            ko = KnowledgeObject(
                meeting_id=meeting_id,
                object_type="topic",
                title=f"Topic: {text[:50]}",
                content={"topic": text, "detected_at_offset_ms": timestamp_ms},
                status="active",
                confidence=0.85,
                version=1,
                provenance={"source": "live_transcript", "speaker": speaker_name, "tenant_id": tenant_id},
            )
            self.db.add(ko)
            created.append(ko)

        return created
