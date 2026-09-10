"""
Explicit Exception Hierarchy for ABCI-MI Benchmark & Dataset Validation.
Provides standard error codes and actionable resolution instructions.
"""

from typing import Optional


class BenchmarkError(Exception):
    """Base exception for all benchmark framework errors."""

    def __init__(self, message: str, error_code: str = "BENCHMARK_ERROR", details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"


class DatasetNotFoundError(BenchmarkError):
    """Raised when the specified dataset root directory or catalog does not exist."""

    def __init__(self, dataset_name: str, path: str, instructions: str):
        super().__init__(
            message=f"Dataset '{dataset_name}' not found at '{path}'. {instructions}",
            error_code="DATASET_NOT_FOUND",
            details={"dataset": dataset_name, "path": path, "instructions": instructions},
        )


class InvalidDatasetStructureError(BenchmarkError):
    """Raised when the dataset directory is present but missing required directory layout."""

    def __init__(self, dataset_name: str, path: str, missing_elements: list, expected_structure: str):
        super().__init__(
            message=(
                f"Dataset '{dataset_name}' at '{path}' has invalid structure. "
                f"Missing: {', '.join(missing_elements)}. Expected layout: {expected_structure}"
            ),
            error_code="INVALID_DATASET_STRUCTURE",
            details={
                "dataset": dataset_name,
                "path": path,
                "missing_elements": missing_elements,
                "expected_structure": expected_structure,
            },
        )


class MissingAnnotationsError(BenchmarkError):
    """Raised when ground truth annotations (RTTM, TSV, transcript) are missing."""

    def __init__(self, dataset_name: str, sample_id: str, expected_file: str):
        super().__init__(
            message=(
                f"Ground truth annotation file missing for sample '{sample_id}' in dataset '{dataset_name}'. "
                f"Expected: '{expected_file}'"
            ),
            error_code="MISSING_ANNOTATIONS",
            details={"dataset": dataset_name, "sample_id": sample_id, "expected_file": expected_file},
        )


class MissingAudioError(BenchmarkError):
    """Raised when audio recording (.wav, .mp3, .flac) is missing or corrupted."""

    def __init__(self, dataset_name: str, sample_id: str, expected_path: str):
        super().__init__(
            message=(
                f"Audio recording missing for sample '{sample_id}' in dataset '{dataset_name}'. "
                f"Expected: '{expected_path}'"
            ),
            error_code="MISSING_AUDIO",
            details={"dataset": dataset_name, "sample_id": sample_id, "expected_path": expected_path},
        )


class AccessRequiredError(BenchmarkError):
    """Raised when dataset requires user license agreement, registration, or credentials."""

    def __init__(self, dataset_name: str, publisher: str, license_url: str, instructions: str):
        super().__init__(
            message=(
                f"Dataset '{dataset_name}' published by {publisher} requires authorization or manual download. "
                f"URL: {license_url}. Instructions: {instructions}"
            ),
            error_code="ACCESS_REQUIRED",
            details={
                "dataset": dataset_name,
                "publisher": publisher,
                "license_url": license_url,
                "instructions": instructions,
            },
        )


class UnsupportedVersionError(BenchmarkError):
    """Raised when the specified dataset version is not supported by the adapter."""

    def __init__(self, dataset_name: str, requested_version: str, supported_versions: list):
        super().__init__(
            message=(
                f"Version '{requested_version}' of dataset '{dataset_name}' is unsupported. "
                f"Supported versions: {', '.join(supported_versions)}"
            ),
            error_code="UNSUPPORTED_VERSION",
            details={
                "dataset": dataset_name,
                "requested_version": requested_version,
                "supported_versions": supported_versions,
            },
        )
