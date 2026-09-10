"""
Unit and integration tests for the ABCI-MI CLI testing interface (backend/cli.py and app/cli.py).
"""

import os
import sys
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.cli import (
    SUPPORTED_FILE_FORMATS,
    build_arg_parser,
    sanitize_error_text,
    validate_local_file,
)


def test_cli_parser_defaults():
    """Verify argument parser configurations and default values."""
    parser = build_arg_parser()
    args = parser.parse_args([])
    assert args.file is None
    assert args.meeting_id is None
    assert args.language == "en"
    assert args.mode == "batch"
    assert args.interactive is False
    assert args.export_format == "json"
    assert args.tenant_id == "default-tenant"
    assert args.role == "host"


def test_cli_parser_custom_arguments():
    """Verify custom CLI flags parse accurately."""
    parser = build_arg_parser()
    args = parser.parse_args([
        "--file", "meeting_recording.mp4",
        "--meeting-id", "12345678-1234-5678-1234-567812345678",
        "--title", "Product Roadmap Sync",
        "--language", "es",
        "--mode", "live",
        "--interactive",
        "--query", "What deadlines were committed?",
        "--translate", "fr",
        "--export-format", "markdown",
        "--tenant-id", "acme-corp",
        "--role", "admin",
        "--debug"
    ])
    assert args.file == "meeting_recording.mp4"
    assert args.meeting_id == "12345678-1234-5678-1234-567812345678"
    assert args.title == "Product Roadmap Sync"
    assert args.language == "es"
    assert args.mode == "live"
    assert args.interactive is True
    assert args.query == "What deadlines were committed?"
    assert args.translate == "fr"
    assert args.export_format == "markdown"
    assert args.tenant_id == "acme-corp"
    assert args.role == "admin"
    assert args.debug is True


def test_sanitize_error_text():
    """Verify sensitive credentials are not leaked in CLI logs."""
    raw_error = "Connection failed for postgresql+asyncpg://admin:supersecretpassword@localhost:5432/db with token=secret_token_123"
    sanitized = sanitize_error_text(raw_error)
    assert "supersecretpassword" not in sanitized
    assert "secret_token_123" not in sanitized
    assert "[REDACTED]" in sanitized


def test_validate_local_file_empty_and_missing():
    """Verify proper validation errors for missing or empty paths."""
    with pytest.raises(ValueError, match="File path cannot be empty"):
        validate_local_file("")

    with pytest.raises(FileNotFoundError, match="File not found"):
        validate_local_file("non_existent_path_to_audio_file.wav")


def test_validate_local_file_supported_extension():
    """Verify supported extensions pass validation."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tf.write(b"RIFF dummy wav audio data")
        temp_path = tf.name

    try:
        validated = validate_local_file(temp_path)
        assert validated["file_name"] == os.path.basename(temp_path)
        assert validated["file_size_bytes"] > 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_validate_local_file_unsupported_extension():
    """Verify unsupported extensions are rejected."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
        tf.write(b"text file content")
        temp_path = tf.name

    try:
        with pytest.raises(ValueError, match="Unsupported file extension"):
            validate_local_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
