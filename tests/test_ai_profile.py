import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_profile import extract_profile
from preset_manager import data_dir, default_export_dir, default_preset_dir


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class ProfileWorkflowTests(unittest.TestCase):
    def test_defaults_are_beside_app_in_separate_folders(self):
        self.assertTrue(default_preset_dir().is_relative_to(data_dir()))
        self.assertTrue(default_export_dir().is_relative_to(data_dir()))
        self.assertNotEqual(default_preset_dir(), default_export_dir())

    def test_rejects_ai_extraction_failure_without_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "guide.pdf"
            pdf.write_bytes(b"%PDF fake fixture")
            with patch("ai_profile.urllib.request.urlopen", return_value=FakeResponse({"output_text": json.dumps({"extraction_failed": "No MIDI information found"})})):
                with self.assertRaisesRegex(ValueError, "AI extraction failed"):
                    extract_profile(pdf, "test-key", "test-model", "https://example.invalid/v1/responses")
            self.assertEqual(list(Path(temp).glob("*.json")), [])

    def test_rejects_profile_without_page_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "guide.pdf"
            pdf.write_bytes(b"%PDF fake fixture")
            result = {"output_text": json.dumps({
                "library": "Library", "instrument": "Guitar", "octave_convention": "C4=60",
                "source": {"pages": [1], "confidence": "documented"},
                "techniques": {"palm_mute": {"events": [{"type": "keyswitch", "note": 24}]}}
            })}
            with patch("ai_profile.urllib.request.urlopen", return_value=FakeResponse(result)):
                with self.assertRaisesRegex(ValueError, "source quote or page reference"):
                    extract_profile(pdf, "test-key", "test-model", "https://example.invalid/v1/responses")

    def test_accepts_source_cited_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "guide.pdf"
            pdf.write_bytes(b"%PDF fake fixture")
            profile = {
                "library": "Library", "instrument": "Guitar", "octave_convention": "C4=60",
                "source": {"pages": [4], "octave_convention": "C4=60", "confidence": "documented"},
                "techniques": {"palm_mute": {
                    "events": [{"type": "keyswitch", "note": 24}], "source_pages": [4],
                    "evidence": "Palm mute is selected with the low C keyswitch.", "confidence": "documented"
                }}
            }
            with patch("ai_profile.urllib.request.urlopen", return_value=FakeResponse({"output_text": json.dumps(profile)})):
                result = extract_profile(pdf, "test-key", "test-model", "https://example.invalid/v1/responses")
            self.assertEqual(result["techniques"]["palm_mute"]["events"][0]["note"], 24)


if __name__ == "__main__":
    unittest.main()
