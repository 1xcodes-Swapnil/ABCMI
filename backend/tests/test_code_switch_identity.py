"""Same-language routing checks, without model/audio/network execution."""
import unittest
from app.ai.code_switch_intelligence import declared_english_identity


class IdentityRouting(unittest.TestCase):
    def setUp(self):
        self.text = "No, no! Harvey didn't think so."
        self.segments = [{"segment_id": "unit-record", "transcript": self.text}]

    def test_explicit_english_preserves_verbatim(self):
        result = declared_english_identity(self.text, self.segments, ["en"])
        self.assertEqual(result["canonical_text"], self.text)
        self.assertEqual(result["normalized_turns"][0]["original_text"], self.text)
        self.assertEqual(result["representation"], "original_language_identity")
        self.assertFalse(result["generation_executed"])
        self.assertIsNone(result["model"])

    def test_english_locale(self):
        self.assertIsNotNone(declared_english_identity(self.text, self.segments, ["en-US"]))

    def test_unknown_does_not_skip_provider(self):
        for codes in ([], ["auto"], ["und"]):
            self.assertIsNone(declared_english_identity(self.text, self.segments, codes))

    def test_mixed_does_not_skip_provider(self):
        self.assertIsNone(declared_english_identity(self.text, self.segments, ["en", "hi"]))

    def test_nonenglish_does_not_skip_provider(self):
        self.assertIsNone(declared_english_identity(self.text, self.segments, ["hi"]))

    def test_contradictory_detection_does_not_skip_provider(self):
        self.assertIsNone(declared_english_identity(self.text, self.segments, ["en"], ["hi"]))


if __name__ == "__main__":
    unittest.main()
