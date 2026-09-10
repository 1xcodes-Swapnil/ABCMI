"""
Persistence layer for benchmark runs, sample results, and reproducible execution artifacts.
Stores run records in local SQLite database and structured JSON file hierarchies.
"""

import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.benchmarks.config import BenchmarkConfig, get_benchmark_config, get_hardware_info


@dataclass
class SampleResultRecord:
    """Detailed record of a single benchmark sample evaluation."""
    run_id: str
    sample_id: str
    dataset_name: str
    dataset_version: str
    audio_path: str
    language: str
    duration_seconds: float
    model_name: str
    provider: str
    status: str  # SUCCESS | FAILED | SKIPPED
    wer: Optional[float] = None
    cer: Optional[float] = None
    der: Optional[float] = None
    missed_speech_rate: Optional[float] = None
    false_alarm_rate: Optional[float] = None
    speaker_confusion_rate: Optional[float] = None
    mean_boundary_error_ms: Optional[float] = None
    processing_time_seconds: Optional[float] = None
    real_time_factor: Optional[float] = None
    ground_truth_transcript: Optional[str] = None
    predicted_transcript: Optional[str] = None
    ground_truth_turns: List[Dict[str, Any]] = field(default_factory=list)
    predicted_turns: List[Dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class BenchmarkStorage:
    """Manages SQLite storage and JSON artifacts for benchmark runs."""

    def __init__(self, config: Optional[BenchmarkConfig] = None):
        self.config = config or get_benchmark_config()
        self.config.ensure_directories()
        self.db_path = self.config.db_path
        self._init_sqlite_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a sqlite connection with Row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite_db(self) -> None:
        """Initialize database schema for benchmark runs and samples."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    run_id TEXT PRIMARY KEY,
                    dataset_name TEXT NOT NULL,
                    dataset_version TEXT,
                    model_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    device TEXT,
                    language TEXT,
                    samples_requested INTEGER,
                    samples_completed INTEGER DEFAULT 0,
                    samples_failed INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    mean_wer REAL,
                    mean_cer REAL,
                    mean_der REAL,
                    mean_rtf REAL,
                    hardware_info TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_summary TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    sample_id TEXT NOT NULL,
                    dataset_name TEXT NOT NULL,
                    dataset_version TEXT,
                    audio_path TEXT,
                    language TEXT,
                    duration_seconds REAL,
                    model_name TEXT,
                    status TEXT NOT NULL,
                    wer REAL,
                    cer REAL,
                    der REAL,
                    missed_speech_rate REAL,
                    false_alarm_rate REAL,
                    speaker_confusion_rate REAL,
                    mean_boundary_error_ms REAL,
                    processing_time_seconds REAL,
                    real_time_factor REAL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES benchmark_runs(run_id),
                    UNIQUE(run_id, sample_id)
                )
            """)
            conn.commit()

    def create_run(
        self,
        run_id: str,
        dataset_name: str,
        dataset_version: str,
        model_name: str,
        provider: str = "abci-mi",
        device: str = "cpu",
        language: str = "en",
        samples_requested: int = 5,
    ) -> None:
        """Register a new benchmark run."""
        hw_info = json.dumps(get_hardware_info())
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO benchmark_runs (
                    run_id, dataset_name, dataset_version, model_name, provider,
                    device, language, samples_requested, status, hardware_info, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, dataset_name, dataset_version, model_name, provider,
                device, language, samples_requested, "RUNNING", hw_info, now
            ))
            conn.commit()

        # Create folder structure for this run
        run_dir = os.path.join(self.config.results_dir, "runs", run_id)
        os.makedirs(run_dir, exist_ok=True)
        config_data = {
            "run_id": run_id,
            "dataset_name": dataset_name,
            "dataset_version": dataset_version,
            "model_name": model_name,
            "provider": provider,
            "device": device,
            "language": language,
            "samples_requested": samples_requested,
            "hardware_info": get_hardware_info(),
            "created_at": now,
        }
        with open(os.path.join(run_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

    def save_sample_result(self, record: SampleResultRecord) -> None:
        """Persist individual sample result in SQLite and JSON."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO benchmark_samples (
                    run_id, sample_id, dataset_name, dataset_version, audio_path,
                    language, duration_seconds, model_name, status, wer, cer, der,
                    missed_speech_rate, false_alarm_rate, speaker_confusion_rate,
                    mean_boundary_error_ms, processing_time_seconds, real_time_factor,
                    error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.run_id, record.sample_id, record.dataset_name, record.dataset_version,
                record.audio_path, record.language, record.duration_seconds, record.model_name,
                record.status, record.wer, record.cer, record.der, record.missed_speech_rate,
                record.false_alarm_rate, record.speaker_confusion_rate, record.mean_boundary_error_ms,
                record.processing_time_seconds, record.real_time_factor, record.error_message,
                record.created_at
            ))
            conn.commit()

    def get_completed_sample_ids(self, run_id: str) -> List[str]:
        """Fetch list of already successfully processed sample IDs for resume functionality."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sample_id FROM benchmark_samples WHERE run_id = ? AND status = 'SUCCESS'",
                (run_id,)
            )
            return [row["sample_id"] for row in cursor.fetchall()]

    def finalize_run(
        self,
        run_id: str,
        status: str,
        summary_metrics: Dict[str, Any],
        error_summary: Optional[str] = None,
    ) -> None:
        """Mark benchmark run complete, update aggregations, and generate file artifacts."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE benchmark_runs SET
                    status = ?,
                    samples_completed = ?,
                    samples_failed = ?,
                    mean_wer = ?,
                    mean_cer = ?,
                    mean_der = ?,
                    mean_rtf = ?,
                    completed_at = ?,
                    error_summary = ?
                WHERE run_id = ?
            """, (
                status,
                summary_metrics.get("samples_completed", 0),
                summary_metrics.get("samples_failed", 0),
                summary_metrics.get("mean_wer"),
                summary_metrics.get("mean_cer"),
                summary_metrics.get("mean_der"),
                summary_metrics.get("mean_rtf"),
                now,
                error_summary,
                run_id
            ))
            conn.commit()

        # Update latest pointer
        run_dir = os.path.join(self.config.results_dir, "runs", run_id)
        latest_dir = os.path.join(self.config.results_dir, "latest")
        if os.path.exists(run_dir):
            try:
                if os.path.exists(latest_dir):
                    shutil.rmtree(latest_dir)
                shutil.copytree(run_dir, latest_dir)
            except Exception:
                pass

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve run details and sample results."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM benchmark_runs WHERE run_id = ?", (run_id,))
            run_row = cursor.fetchone()
            if not run_row:
                return None

            cursor.execute("SELECT * FROM benchmark_samples WHERE run_id = ?", (run_id,))
            sample_rows = cursor.fetchall()

            run_dict = dict(run_row)
            if run_dict.get("hardware_info"):
                try:
                    run_dict["hardware_info"] = json.loads(run_dict["hardware_info"])
                except Exception:
                    pass
            run_dict["samples"] = [dict(s) for s in sample_rows]
            return run_dict

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List historical benchmark runs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM benchmark_runs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]
