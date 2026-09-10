"""
ABCI-MI Audio & Artifact Storage Infrastructure
Provides filesystem and object storage abstraction for meeting audio files, transcripts, and model artifacts.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("infrastructure.storage")


class LocalStorageManager:
    """Manages local filesystem storage for uploaded audio, processed chunks, and artifacts."""

    def __init__(self, base_path: Optional[str] = None):
        settings = get_settings()
        self.base_path = Path(base_path or settings.AUDIO_STORAGE_PATH).resolve()
        self._ensure_storage_directory()

    def _ensure_storage_directory(self) -> None:
        """Creates the storage directories if they do not exist."""
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            # Create subdirectories for audio segments, transcripts, and temporary workspace
            (self.base_path / "raw").mkdir(exist_ok=True)
            (self.base_path / "segments").mkdir(exist_ok=True)
            (self.base_path / "cache").mkdir(exist_ok=True)
            logger.info(f"Storage directory initialized at {self.base_path}")
        except Exception as e:
            logger.error(f"Failed to create storage directory {self.base_path}: {e}")

    def save_audio_file(self, meeting_id: Any, file_name: str, content: bytes) -> Path:
        """Saves uploaded audio payload bytes into local storage directory."""
        raw_dir = self.base_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{meeting_id}_{file_name}"
        target_path = raw_dir / safe_name
        target_path.write_bytes(content)
        return target_path

    async def save_audio_chunk(self, meeting_id: str, session_id: str, sequence_number: int, file_bytes: bytes) -> str:
        """Saves an incoming streaming audio chunk into local storage."""
        chunks_dir = self.base_path / "segments" / meeting_id / session_id
        chunks_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = chunks_dir / f"chunk_{sequence_number:06d}.wav"
        chunk_path.write_bytes(file_bytes)
        return str(chunk_path)

    def save_report_file(self, tenant_id: str, meeting_id: str, report_id: str, format_type: str, content: bytes) -> str:
        """Saves a generated meeting report file under reports/{tenant_id}/{meeting_id}/{report_id}/file.{format_type}."""
        safe_tenant = str(tenant_id or "default").replace("..", "").replace("/", "_")
        safe_meeting = str(meeting_id).replace("..", "").replace("/", "_")
        safe_report = str(report_id).replace("..", "").replace("/", "_")
        
        report_dir = self.base_path / "reports" / safe_tenant / safe_meeting / safe_report
        report_dir.mkdir(parents=True, exist_ok=True)
        
        ext = format_type.lower()
        if ext == "markdown":
            ext = "md"
        
        file_path = report_dir / f"report.{ext}"
        # Ensure path traversal prevention
        resolved_path = file_path.resolve()
        if not str(resolved_path).startswith(str(self.base_path.resolve())):
            raise ValueError("Path traversal detected")
            
        resolved_path.write_bytes(content)
        return str(resolved_path)

    def get_report_file(self, storage_path: str) -> bytes:
        """Reads a report file from storage with path traversal protection."""
        target_path = Path(storage_path).resolve()
        if not str(target_path).startswith(str(self.base_path.resolve())):
            raise ValueError("Path traversal detected")
        if not target_path.exists():
            raise FileNotFoundError(f"Report file not found at {storage_path}")
        return target_path.read_bytes()

    def check_health(self) -> Dict[str, Any]:
        """Checks if the storage directory is accessible and writable."""
        try:
            test_file = self.base_path / ".storage_health_test"
            test_file.write_text("health_check_ok")
            test_file.unlink()
            return {
                "status": "healthy",
                "path": str(self.base_path),
                "writable": True,
                "error": None,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "path": str(self.base_path),
                "writable": False,
                "error": str(e),
            }


_storage_manager: Optional[LocalStorageManager] = None


def get_storage_manager() -> LocalStorageManager:
    """Returns the singleton LocalStorageManager."""
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = LocalStorageManager()
    return _storage_manager
