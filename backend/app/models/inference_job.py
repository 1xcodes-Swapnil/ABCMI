"""Durable work references; Redis remains a notification transport, not a job store."""
from datetime import datetime
import uuid
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel


class InferenceJob(BaseModel):
    __tablename__ = "inference_jobs"

    job_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    meeting_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("meetings.id"), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("live_sessions.id"), index=True)
    payload: Mapped[dict | None] = mapped_column(JSON)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("live_audio_chunks.id"))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
