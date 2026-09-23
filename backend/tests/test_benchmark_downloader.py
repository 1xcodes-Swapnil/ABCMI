"""
Unit and integration tests for benchmark dataset downloader and local preparer.
"""

import os
import shutil
import sys
import tempfile
import unittest
import wave
from pathlib import Path

# Add backend directory to sys.path
test_dir_path = Path(__file__).resolve().parent
backend_dir_path = test_dir_path.parent
workspace_dir_path = backend_dir_path.parent

for p in (str(backend_dir_path), str(workspace_dir_path)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.benchmarks.dataset_registry import get_dataset_registry
from scripts.download_benchmark_datasets import (
    AMIDatasetPreparer,
    AISHELLPreparer,
    CommonVoicePreparer,
    DIHARDPreparer,
    VoxConversePreparer,
    verify_datasets,
    write_valid_pcm_wav,
)


class TestBenchmarkDatasetDownloader(unittest.TestCase):
    """Test suite for benchmark dataset preparation and adapter compatibility."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_write_valid_pcm_wav(self):
        """Verify generated WAV conforms strictly to standard 16kHz mono 16-bit PCM RIFF."""
        wav_path = os.path.join(self.test_dir, "test.wav")
        write_valid_pcm_wav(wav_path, duration_seconds=1.5, sample_rate=16000, channels=1)

        self.assertTrue(os.path.exists(wav_path))
        with wave.open(wav_path, "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getframerate(), 16000)
            self.assertEqual(wf.getnframes(), 24000)  # 1.5 * 16000

    def test_ami_preparer_and_adapter(self):
        """Test AMI meeting corpus preparation and adapter sample loading."""
        preparer = AMIDatasetPreparer()
        samples_prep = preparer.prepare(self.test_dir, max_samples=2, download_real=False)
        self.assertEqual(len(samples_prep), 2)

        # Check adapter discovery
        registry = get_dataset_registry()
        adapter = registry.get_adapter("ami")
        self.assertIsNotNone(adapter)

        samples = adapter.locate_or_download_samples(self.test_dir, max_samples=2)
        self.assertEqual(len(samples), 2)
        for s in samples:
            self.assertEqual(s.dataset_name, "AMI")
            self.assertTrue(os.path.exists(s.audio_path))
            self.assertTrue(len(s.reference_speaker_turns) > 0)
            self.assertTrue(s.duration_seconds > 0)
            self.assertIsNotNone(s.audio_sha256)

    def test_voxconverse_preparer_and_adapter(self):
        """Test VoxConverse preparation and adapter loading."""
        preparer = VoxConversePreparer()
        samples_prep = preparer.prepare(self.test_dir, max_samples=2, download_real=False)
        self.assertEqual(len(samples_prep), 2)

        registry = get_dataset_registry()
        adapter = registry.get_adapter("voxconverse")
        self.assertIsNotNone(adapter)

        samples = adapter.locate_or_download_samples(self.test_dir, max_samples=2)
        self.assertEqual(len(samples), 2)
        for s in samples:
            self.assertEqual(s.dataset_name, "VoxConverse")
            self.assertTrue(os.path.exists(s.audio_path))
            self.assertTrue(len(s.reference_speaker_turns) > 0)
            self.assertIsNotNone(s.audio_sha256)

    def test_aishell_preparer_and_adapter(self):
        """Test AISHELL Mandarin speech preparation and adapter loading."""
        preparer = AISHELLPreparer()
        samples_prep = preparer.prepare(self.test_dir, max_samples=2, download_real=False)
        self.assertEqual(len(samples_prep), 2)

        registry = get_dataset_registry()
        adapter = registry.get_adapter("aishell")
        self.assertIsNotNone(adapter)

        samples = adapter.locate_or_download_samples(self.test_dir, max_samples=2, language="zh")
        self.assertEqual(len(samples), 2)
        for s in samples:
            self.assertEqual(s.dataset_name, "AISHELL")
            self.assertEqual(s.language, "zh")
            self.assertTrue(os.path.exists(s.audio_path))
            self.assertTrue(len(s.reference_transcript) > 0)

    def test_common_voice_preparer_and_adapter(self):
        """Test Common Voice preparation across en, hi, zh and adapter loading."""
        preparer = CommonVoicePreparer()
        prep_res = preparer.prepare(self.test_dir, languages=["en", "hi", "zh"], max_samples=2, download_real=False)
        self.assertIn("en", prep_res)
        self.assertIn("hi", prep_res)
        self.assertIn("zh", prep_res)

        registry = get_dataset_registry()
        adapter = registry.get_adapter("common_voice")
        self.assertIsNotNone(adapter)

        # Test English
        samples_en = adapter.locate_or_download_samples(self.test_dir, max_samples=2, language="en")
        self.assertEqual(len(samples_en), 2)
        self.assertTrue(os.path.exists(samples_en[0].audio_path))
        self.assertEqual(samples_en[0].language, "en")

        # Test Hindi
        samples_hi = adapter.locate_or_download_samples(self.test_dir, max_samples=2, language="hi")
        self.assertEqual(len(samples_hi), 2)
        self.assertEqual(samples_hi[0].language, "hi")

    def test_dihard_preparer_and_adapter(self):
        """Test DIHARD-III preparation and adapter loading."""
        preparer = DIHARDPreparer()
        samples_prep = preparer.prepare(self.test_dir, max_samples=2, download_real=False)
        self.assertEqual(len(samples_prep), 2)

        registry = get_dataset_registry()
        adapter = registry.get_adapter("dihard")
        self.assertIsNotNone(adapter)

        samples = adapter.locate_or_download_samples(self.test_dir, max_samples=2)
        self.assertEqual(len(samples), 2)
        for s in samples:
            self.assertEqual(s.dataset_name, "DIHARD")
            self.assertTrue(os.path.exists(s.audio_path))
            self.assertTrue(len(s.reference_speaker_turns) > 0)

    def test_verification_reporter(self):
        """Test verify_datasets runs cleanly across initialized datasets."""
        preparers = [
            AMIDatasetPreparer(),
            VoxConversePreparer(),
            AISHELLPreparer(),
            CommonVoicePreparer(),
            DIHARDPreparer(),
        ]
        for p in preparers:
            p.prepare(self.test_dir, max_samples=2, download_real=False)

        report = verify_datasets(self.test_dir, max_samples=2)
        self.assertEqual(len(report), 5)
        for d_key, info in report.items():
            self.assertEqual(info["status"], "VALID", f"Dataset {d_key} failed verification: {info['error']}")
            self.assertTrue(info["samples_count"] > 0)


if __name__ == "__main__":
    unittest.main()
