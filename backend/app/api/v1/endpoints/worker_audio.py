"""Read-only audio transfer for an authenticated inference worker."""
import secrets
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_async_db
from app.core.config import get_settings
from app.infrastructure.storage import get_storage_manager
from app.models.live_session import LiveAudioChunk

router = APIRouter(prefix="/worker", tags=["Inference worker"])


@router.get("/audio/{chunk_id}")
async def read_chunk(chunk_id: uuid.UUID, x_worker_token: str = Header(default=""),
                     db: AsyncSession = Depends(get_async_db)):
    expected = get_settings().LIVE_WORKER_TOKEN
    if not expected or not secrets.compare_digest(expected, x_worker_token):
        raise HTTPException(status_code=403, detail="Worker authentication required")
    chunk = await db.get(LiveAudioChunk, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="Chunk not found")
    path = Path(chunk.file_path).resolve()
    if not path.is_relative_to(get_storage_manager().base_path.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio unavailable")
    return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "no-store"})
