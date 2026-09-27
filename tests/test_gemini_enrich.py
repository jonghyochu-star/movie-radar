import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gemini_enrich", ROOT / "scripts" / "gemini_enrich.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def video(vid, views, validated):
    return {
        "id": vid,
        "views": views,
        "audience": {
            "status": "proven" if validated else "watch",
            "validated": validated,
        },
    }


def success_report(pattern="재회"):
    return {
        "status": "success",
        "analysis": {
            "screen_scene_decision": "yes",
            "story_pattern": pattern,
        },
        "usage": {"totalTokenCount": 100},
    }


class GeminiEnrichTests(unittest.TestCase):
    def test_limit_zero_reuses_cache_without_api(self):
        data = {"videos": [video("AbCdEfGhI01", 9_000_000, True)]}
        cache = M.empty_cache()
        cache["videos"]["AbCdEfGhI01"] = {
            "analysis": {"screen_scene_decision": "yes", "story_pattern": "재회"},
            "analyzedAt": "2026-09-27T00:00:00Z",
            "usage": None,
        }
        calls = []
        def analyzer(*args, **kwargs):
            calls.append(1)
            return success_report()
        out, _ = M.enrich_data(data, cache, limit=0, api_key="", analyzer=analyzer)
        self.assertEqual(calls, [])
        self.assertEqual(out["videos"][0]["gemini"]["analysis"]["story_pattern"], "재회")
        self.assertEqual(out["geminiSummary"]["cacheHits"], 1)

    def test_selection_prefers_validated_and_reserves_exploration_slot(self):
        rows = [
            video("Validated01", 20_000_000, True),
            video("Validated02", 10_000_000, True),
            video("Validated03", 8_000_000, True),
            video("Explore0001", 4_000_000, False),
        ]
        chosen = M.choose_new_candidates(rows, M.empty_cache(), 3)
        self.assertEqual(len(chosen), 3)
        self.assertIn("Explore0001", [x["id"] for x in chosen])
        self.assertIn("Validated01", [x["id"] for x in chosen])

    def test_success_is_cached_and_reused_next_run(self):
        data = {"videos": [video("AbCdEfGhI01", 9_000_000, True)]}
        cache = M.empty_cache()
        calls = []
        def analyzer(*args, **kwargs):
            calls.append(1)
            return success_report("편견·오해의 반전")
        out, cache = M.enrich_data(
            data, cache, limit=1, api_key="secret", analyzer=analyzer,
            now="2026-09-27T00:00:00Z"
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(out["geminiSummary"]["successes"], 1)
        self.assertIn("AbCdEfGhI01", cache["videos"])

        calls.clear()
        data2 = {"videos": [video("AbCdEfGhI01", 10_000_000, True)]}
        out2, _ = M.enrich_data(data2, cache, limit=1, api_key="secret", analyzer=analyzer)
        self.assertEqual(calls, [])
        self.assertEqual(out2["geminiSummary"]["cacheHits"], 1)

    def test_first_failure_stops_remaining_calls(self):
        data = {"videos": [
            video("AbCdEfGhI01", 9_000_000, True),
            video("AbCdEfGhI02", 8_000_000, True),
            video("AbCdEfGhI03", 7_000_000, True),
        ]}
        cache = M.empty_cache()
        calls = []
        def analyzer(url, **kwargs):
            calls.append(url)
            return {"status": "failed", "httpStatus": 503, "apiStatus": "UNAVAILABLE"}
        out, _ = M.enrich_data(data, cache, limit=3, api_key="secret", analyzer=analyzer)
        self.assertEqual(len(calls), 1)
        self.assertEqual(out["geminiSummary"]["attempts"], 1)
        self.assertTrue(out["geminiSummary"]["stoppedAfterError"])
        self.assertEqual(out["geminiSummary"]["stopCode"], "UNAVAILABLE")

    def test_missing_key_only_errors_when_new_call_is_needed(self):
        data = {"videos": [video("AbCdEfGhI01", 9_000_000, True)]}
        with self.assertRaises(M.EnrichError):
            M.enrich_data(data, M.empty_cache(), limit=1, api_key="")

    def test_limit_is_hard_bounded(self):
        with self.assertRaises(M.EnrichError):
            M.enrich_data({"videos": []}, M.empty_cache(), limit=9, api_key="")


if __name__ == "__main__":
    unittest.main()
