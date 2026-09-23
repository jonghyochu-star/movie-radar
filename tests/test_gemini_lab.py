import importlib.util
import json
import io
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gemini_lab", ROOT / "scripts" / "gemini_lab.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class GeminiLabTests(unittest.TestCase):
    def test_youtube_url_validation(self):
        self.assertEqual(M.youtube_id("https://www.youtube.com/watch?v=AbCdEfGhI01"), "AbCdEfGhI01")
        self.assertEqual(M.youtube_id("https://youtu.be/AbCdEfGhI01?t=1"), "AbCdEfGhI01")
        self.assertEqual(M.youtube_id("https://www.youtube.com/shorts/AbCdEfGhI01"), "AbCdEfGhI01")
        for bad in [
            "http://www.youtube.com/watch?v=AbCdEfGhI01",
            "https://youtube.com.evil.test/watch?v=AbCdEfGhI01",
            "https://www.youtube.com/channel/UC123",
            "javascript:alert(1)",
        ]:
            with self.assertRaises(M.LabError):
                M.youtube_id(bad)

    def test_schema_has_core_blind_fields(self):
        s = M.schema()
        self.assertEqual(s["type"], "object")
        for key in ["screen_scene_decision", "content_type", "story_arc", "summary_ko", "preference_features"]:
            self.assertIn(key, s["properties"])
            self.assertIn(key, s["required"])

    def test_prompt_does_not_contain_expected_label(self):
        self.assertNotIn("movie_drama", M.PROMPT)
        self.assertNotIn("not_movie_drama", M.PROMPT)
        self.assertIn("블라인드", M.PROMPT)

    def test_cost_estimate(self):
        x = M.estimate_cost_usd({
            "total_input_tokens": 100000,
            "total_tool_use_tokens": 0,
            "total_output_tokens": 1000,
            "total_thought_tokens": 1000,
        })
        self.assertAlmostEqual(x["rough_paid_usd"], 0.0825, places=6)

    def test_comparison(self):
        self.assertTrue(M.comparison("movie_drama", "yes")["correct"])
        self.assertTrue(M.comparison("not_movie_drama", "no")["correct"])
        self.assertFalse(M.comparison("movie_drama", "no")["correct"])
        self.assertIsNone(M.comparison("unknown", "yes")["correct"])

    def test_extract_output_text(self):
        response = {"steps": [{"type": "model_output", "content": [{"type": "text", "text": "{\"a\":1}"}]}]}
        self.assertEqual(M.extract_output_text(response), '{"a":1}')

    def test_http_503_retries_then_succeeds(self):
        result = {
            "screen_scene_decision": "no",
            "content_type": "real_life_or_vlog",
            "confidence": "high",
            "why": ["실제 인물 촬영"],
            "relationship": [],
            "story_arc": "불명확",
            "emotional_turn": False,
            "turn_timestamp": "",
            "story_completeness": "moment_only",
            "aftertaste": "weak",
            "summary_ko": "실제 인물 영상이다.",
            "preference_features": [],
        }
        response = {
            "status": "completed",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}],
            "usage": {},
        }
        class FakeResponse:
            def __enter__(self):
                return io.StringIO(json.dumps(response, ensure_ascii=False))
            def __exit__(self, *args):
                return False
        transient = M.HTTPError("https://example.invalid", 503, "Service Unavailable", None, None)
        with mock.patch.object(M, "urlopen", side_effect=[transient, FakeResponse()]) as open_mock, \
             mock.patch.object(M.time, "sleep") as sleep_mock:
            got, usage = M.call_gemini("secret", "https://youtu.be/AbCdEfGhI01")
        self.assertEqual(got["screen_scene_decision"], "no")
        self.assertEqual(open_mock.call_count, 2)
        sleep_mock.assert_called_once()

    def test_report_contains_no_api_key(self):
        result = {
            "screen_scene_decision": "yes", "content_type": "feature_film_scene", "confidence": "high",
            "why": ["배우의 연기 장면"], "relationship": ["부녀"], "story_arc": "갈등→이해→화해",
            "emotional_turn": True, "turn_timestamp": "00:40", "story_completeness": "complete",
            "aftertaste": "strong", "summary_ko": "가족 갈등이 풀린다.", "preference_features": ["가족", "화해"]
        }
        with tempfile.TemporaryDirectory() as td:
            M.write_reports(Path(td), "https://youtu.be/AbCdEfGhI01", M.DEFAULT_MODEL, result, {}, "movie_drama")
            text = (Path(td)/"gemini-lab-report.json").read_text(encoding="utf-8")
            self.assertIn("feature_film_scene", text)
            self.assertNotIn("GEMINI_API_KEY", text)


if __name__ == "__main__":
    unittest.main()
