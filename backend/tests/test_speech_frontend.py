"""Fast frontend contract checks; no generated audio/model, GPU, DB or network."""
import unittest
from types import SimpleNamespace
from app.ai.speech_frontend import SpeechFrontend, merge_speech_frames, speech_frontend_identity


class SpeechFrontendContracts(unittest.TestCase):
    def test_off_does_not_decode_or_load(self):
        result = SpeechFrontend(SimpleNamespace(AUDIO_VAD_MODE="off")).analyze("not-an-input-file")
        self.assertEqual(result["status"], "DISABLED")
        self.assertIsNone(result["speech_detected"])

    def test_missing_enabled_artifact_fails(self):
        with self.assertRaisesRegex(RuntimeError, "no download or fallback"):
            speech_frontend_identity(SimpleNamespace(AUDIO_VAD_MODE="filter", AUDIO_VAD_MODEL_PATH=None))

    def test_unknown_mode_fails(self):
        with self.assertRaises(ValueError):
            speech_frontend_identity(SimpleNamespace(AUDIO_VAD_MODE="invented"))

    def test_collar_bounds_and_join(self):
        self.assertEqual(merge_speech_frames([(0., .1), (.2, .4), (.9, 1.)], 1., .25),
                         [{"start": 0., "end": 1.}])

    def test_internal_silence_not_compressed(self):
        self.assertEqual(merge_speech_frames([(1., 2.), (4., 5.)], 6., .25),
                         [{"start": .75, "end": 2.25}, {"start": 3.75, "end": 5.25}])

    def test_empty_speech_is_explicit(self):
        self.assertEqual(merge_speech_frames([], 2., .25), [])

    def test_invalid_intervals_fail(self):
        for frames in ([(2., 1.)], [(-1., 1.)], [(0., 3.)], [(1., 2.), (0., 1.)], [(0., float("nan"))]):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                merge_speech_frames(frames, 2., .25)


if __name__ == "__main__":
    unittest.main()
