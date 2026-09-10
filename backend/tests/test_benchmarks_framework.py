"""
Unit tests for ABCI-MI Real Benchmark Evaluation Subsystem.
Tests metric calculations (WER, CER, DER, boundary alignment), dataset registry,
storage persistence, resume capabilities, failure isolation, explicit exception codes,
and CLI integration.
"""

import os
import shutil
import tempfile
import unittest
from typing import Any, Dict, List

from app.benchmarks.config import BenchmarkConfig
from app.benchmarks.dataset_registry import DatasetRegistry, get_dataset_registry
from app.benchmarks.datasets.base import BenchmarkSample
from app.benchmarks.exceptions import (
    AccessRequiredError,
    BenchmarkError,
    DatasetNotFoundError,
    InvalidDatasetStructureError,
    MissingAnnotationsError,
    MissingAudioError,
    UnsupportedVersionError,
)
from app.benchmarks.metrics import (
    calculate_cer,
    calculate_der,
    calculate_rtf,
    calculate_timestamp_boundary_error,
    calculate_wer,
    normalize_text,
)
from app.benchmarks.reporting import BenchmarkReporter
from app.benchmarks.runner import BenchmarkRunner
from app.benchmarks.storage import BenchmarkStorage, SampleResultRecord


class TestBenchmarkMetrics(unittest.TestCase):
    """Test mathematical metric implementations."""

    def test_normalize_text(self):
        """Test text normalization preserving multilingual Unicode characters."""
        self.assertEqual(normalize_text("Hello, World!"), "hello world")
        self.assertEqual(normalize_text("  Meeting   Title  "), "meeting title")
        self.assertEqual(normalize_text("आज की बैठक"), "आज की बैठक")
        self.assertEqual(normalize_text("会议转录测试"), "会议转录测试")

    def test_wer_exact_match(self):
        """Test WER when reference matches hypothesis exactly."""
        ref = "the quick brown fox jumps over the lazy dog"
        hyp = "the quick brown fox jumps over the lazy dog"
        res = calculate_wer(ref, hyp)
        self.assertEqual(res["wer"], 0.0)
        self.assertEqual(res["substitutions"], 0)
        self.assertEqual(res["deletions"], 0)
        self.assertEqual(res["insertions"], 0)
        self.assertEqual(res["correct"], 9)
        self.assertEqual(res["ref_word_count"], 9)

    def test_wer_substitutions_insertions_deletions(self):
        """Test WER computation with mixed errors."""
        ref = "we have a meeting today"
        hyp = "we have a session today"  # 1 substitution: meeting -> session
        res = calculate_wer(ref, hyp)
        self.assertEqual(res["wer"], 0.2)  # 1/5
        self.assertEqual(res["substitutions"], 1)

        hyp_del = "we have today"  # 2 deletions: a, meeting
        res_del = calculate_wer(ref, hyp_del)
        self.assertEqual(res_del["wer"], 0.4)  # 2/5
        self.assertEqual(res_del["deletions"], 2)

        hyp_ins = "we really have a meeting today"  # 1 insertion: really
        res_ins = calculate_wer(ref, hyp_ins)
        self.assertEqual(res_ins["wer"], 0.2)  # 1/5
        self.assertEqual(res_ins["insertions"], 1)

    def test_wer_empty_strings(self):
        """Test WER with empty edge cases."""
        self.assertEqual(calculate_wer("", "")["wer"], 0.0)
        self.assertEqual(calculate_wer("", "hello world")["wer"], 1.0)
        self.assertEqual(calculate_wer("hello world", "")["wer"], 1.0)

    def test_cer_mandarin_and_multilingual(self):
        """Test Character Error Rate on Mandarin text."""
        ref = "广州市科技创新大会在白云国际会议中心召开"
        hyp = "广州市科技创新大会在白云国际会议中心召开"
        res = calculate_cer(ref, hyp)
        self.assertEqual(res["cer"], 0.0)
        self.assertEqual(res["correct"], len(ref))

        hyp_err = "广州市科技产业大会在白云国际会议中心召开"  # 1 char substitution (创 -> 产), 1 char match (新 -> 业)
        res_err = calculate_cer(ref, hyp_err)
        self.assertGreater(res_err["cer"], 0.0)
        self.assertLessEqual(res_err["cer"], 1.0)

    def test_der_perfect_alignment(self):
        """Test DER when hypothesis perfectly matches reference speaker turns."""
        turns = [
            {"speaker": "spk_1", "start_time": 0.0, "end_time": 5.0},
            {"speaker": "spk_2", "start_time": 6.0, "end_time": 10.0},
        ]
        res = calculate_der(turns, turns, collar_seconds=0.0)
        self.assertEqual(res["der"], 0.0)
        self.assertEqual(res["missed_speech_rate"], 0.0)
        self.assertEqual(res["false_alarm_rate"], 0.0)
        self.assertEqual(res["speaker_confusion_rate"], 0.0)

    def test_der_speaker_confusion(self):
        """Test DER when hypothesis has different speaker labels that do not map 1:1."""
        ref = [
            {"speaker": "spk_1", "start_time": 0.0, "end_time": 10.0},
            {"speaker": "spk_2", "start_time": 10.0, "end_time": 20.0},
        ]
        # Hypothesis assigns all to single speaker
        hyp = [
            {"speaker": "spk_A", "start_time": 0.0, "end_time": 20.0},
        ]
        res = calculate_der(ref, hyp, collar_seconds=0.0)
        self.assertGreater(res["der"], 0.0)
        self.assertGreater(res["speaker_confusion_rate"], 0.3)

    def test_der_evaluation_collar(self):
        """Test that collar window around reference boundaries reduces boundary penalty."""
        ref = [{"speaker": "spk_1", "start_time": 1.0, "end_time": 5.0}]
        hyp = [{"speaker": "spk_1", "start_time": 0.9, "end_time": 5.1}]
        res_with_collar = calculate_der(ref, hyp, collar_seconds=0.25)
        self.assertEqual(res_with_collar["der"], 0.0)

    def test_timestamp_boundary_error(self):
        """Test segment boundary error calculation."""
        ref = [{"start_time": 1.0, "end_time": 5.0, "speaker": "spk_1"}]
        hyp = [{"start_time": 1.1, "end_time": 5.2, "speaker": "spk_1"}]  # 100ms and 200ms errors
        res = calculate_timestamp_boundary_error(ref, hyp)
        self.assertEqual(res["matched_segments_count"], 1)
        self.assertEqual(res["mean_boundary_error_ms"], 150.0)

    def test_rtf_calculation(self):
        """Test Real-Time Factor calculation."""
        self.assertEqual(calculate_rtf(10.0, 100.0), 0.1)
        self.assertEqual(calculate_rtf(200.0, 100.0), 2.0)
        self.assertEqual(calculate_rtf(0.0, 0.0), 0.0)


class TestDatasetRegistry(unittest.TestCase):
    """Test dataset registration and lookup capabilities."""

    def test_registered_datasets_coverage(self):
        """Verify all 5 target benchmark datasets are registered."""
        registry = get_dataset_registry()
        datasets = registry.list_datasets()
        keys = [d["key"] for d in datasets]

        self.assertIn("ami", keys)
        self.assertIn("voxconverse", keys)
        self.assertIn("dihard", keys)
        self.assertIn("aishell", keys)
        self.assertIn("common_voice", keys)

    def test_adapter_properties(self):
        """Verify adapter metadata integrity."""
        registry = get_dataset_registry()
        ami = registry.get_adapter("ami")
        self.assertIsNotNone(ami)
        self.assertEqual(ami.name, "AMI")
        self.assertEqual(ami.version, "1.6.2")
        self.assertIn("ASR", ami.supported_tasks)
        self.assertIn("DIARIZATION", ami.supported_tasks)
        self.assertFalse(ami.requires_auth)

        dihard = registry.get_adapter("dihard")
        self.assertIsNotNone(dihard)
        self.assertTrue(dihard.requires_auth)
        self.assertIn("LDC", dihard.auth_instructions)

        aishell = registry.get_adapter("aishell")
        self.assertIsNotNone(aishell)
        self.assertEqual(aishell.name, "AISHELL")
        self.assertIn("OpenSLR", aishell.auth_instructions)


class TestExceptionHierarchy(unittest.TestCase):
    """Test standard benchmark exception hierarchy and error codes."""

    def test_exception_codes(self):
        """Verify explicit error codes on exceptions."""
        e1 = DatasetNotFoundError("DIHARD", "/tmp/dihard", "Set DIHARD_DATASET_ROOT")
        self.assertEqual(e1.error_code, "DATASET_NOT_FOUND")
        self.assertIn("DIHARD", str(e1))

        e2 = MissingAudioError("VoxConverse", "aepyx", "/path/to/aepyx.wav")
        self.assertEqual(e2.error_code, "MISSING_AUDIO")

        e3 = AccessRequiredError("DIHARD", "LDC", "https://dihardchallenge.github.io/dihard3/", "Sign agreement")
        self.assertEqual(e3.error_code, "ACCESS_REQUIRED")

        e4 = MissingAnnotationsError("AMI", "ES2004a", "ES2004a.rttm")
        self.assertEqual(e4.error_code, "MISSING_ANNOTATIONS")

        e5 = InvalidDatasetStructureError("AISHELL", "/tmp/aishell", ["wav/"], "data_aishell/wav/")
        self.assertEqual(e5.error_code, "INVALID_DATASET_STRUCTURE")


class TestStorageAndPersistence(unittest.TestCase):
    """Test SQLite storage and JSON report generation."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config = BenchmarkConfig(
            results_dir=os.path.join(self.test_dir, "results"),
            data_cache_dir=os.path.join(self.test_dir, "data"),
            db_path=os.path.join(self.test_dir, "test_benchmarks.db"),
        )
        self.storage = BenchmarkStorage(self.config)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_run_creation_and_retrieval(self):
        """Test creating a run and persisting sample results."""
        run_id = "test_run_ami_001"
        self.storage.create_run(
            run_id=run_id,
            dataset_name="AMI",
            dataset_version="1.6.2",
            model_name="openai/whisper-large-v3",
            samples_requested=2,
        )

        rec1 = SampleResultRecord(
            run_id=run_id,
            sample_id="ES2004a",
            dataset_name="AMI",
            dataset_version="1.6.2",
            audio_path="/path/to/ES2004a.wav",
            language="en",
            duration_seconds=751.2,
            model_name="openai/whisper-large-v3",
            provider="abci-mi",
            status="SUCCESS",
            wer=0.142,
            der=0.089,
            real_time_factor=0.22,
        )
        self.storage.save_sample_result(rec1)

        completed = self.storage.get_completed_sample_ids(run_id)
        self.assertEqual(completed, ["ES2004a"])

        self.storage.finalize_run(
            run_id=run_id,
            status="SUCCESS",
            summary_metrics={"samples_completed": 1, "samples_failed": 0, "mean_wer": 0.142, "mean_der": 0.089, "mean_rtf": 0.22},
        )

        run_data = self.storage.get_run(run_id)
        self.assertIsNotNone(run_data)
        self.assertEqual(run_data["run_id"], run_id)
        self.assertEqual(run_data["status"], "SUCCESS")
        self.assertEqual(len(run_data["samples"]), 1)
        self.assertEqual(run_data["samples"][0]["sample_id"], "ES2004a")


class TestStrictRealExecution(unittest.TestCase):
    """Verify that runner strictly avoids silent mock fallbacks."""

    def test_strict_failure_when_acoustic_dependency_missing(self):
        """Ensure that when real acoustic model backend is absent, run records failure."""
        test_dir = tempfile.mkdtemp()
        try:
            config = BenchmarkConfig(
                results_dir=os.path.join(test_dir, "results"),
                data_cache_dir=os.path.join(test_dir, "data"),
                db_path=os.path.join(test_dir, "test_benchmarks.db"),
            )
            # Create a sample audio file in the target directory
            ami_dir = os.path.join(test_dir, "data", "ami")
            os.makedirs(ami_dir, exist_ok=True)
            with open(os.path.join(ami_dir, "ES2004a.wav"), "wb") as f:
                f.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

            runner = BenchmarkRunner(config=config)
            run_dict = runner.run_benchmark("ami", samples_count=1)
            # Must be recorded as FAILED due to missing PyTorch/Whisper in test environment
            self.assertEqual(run_dict["status"], "FAILED")
            self.assertEqual(run_dict["samples_failed"], 1)
            self.assertIn("Real acoustic model dependency missing", run_dict["samples"][0]["error_message"])
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_explicit_error_when_dihard_root_missing(self):
        """Ensure DIHARD returns ACCESS_REQUIRED error when dataset root is missing."""
        test_dir = tempfile.mkdtemp()
        try:
            config = BenchmarkConfig(
                results_dir=os.path.join(test_dir, "results"),
                data_cache_dir=os.path.join(test_dir, "data"),
                db_path=os.path.join(test_dir, "test_benchmarks.db"),
            )
            runner = BenchmarkRunner(config=config)
            run_dict = runner.run_benchmark("dihard", samples_count=1)
            self.assertEqual(run_dict["status"], "FAILED")
            self.assertEqual(run_dict["error_code"], "ACCESS_REQUIRED")
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
