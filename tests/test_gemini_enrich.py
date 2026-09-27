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
    NOW = "2026-09-27T12:00:00Z"

    def test_limit_zero_reuses_cache_without_api(self):
        data = {"videos": [video("AbCdEfGhI01", 9_000_000, True)]}
        cache = M.empty_cache()
        cache["videos"]["AbCdEfGhI01"] = {
            "status": "success",
            "analysis": {"screen_scene_decision": "yes", "story_pattern": "재회"},
            "analyzedAt": "2026-09-27T00:00:00Z",
            "usage": None,
        }
        calls = []
        def analyzer(*args, **kwargs):
            calls.append(1)
            return success_report()
        out, _ = M.enrich_data(
            data, cache, limit=0, api_key="", analyzer=analyzer, now=self.NOW,
            sleeper=lambda _: None
        )
        self.assertEqual(calls, [])
        self.assertEqual(out["videos"][0]["gemini"]["analysis"]["story_pattern"], "재회")
        self.assertEqual(out["geminiSummary"]["cacheHits"], 1)

    def test_limit_three_spends_calls_on_validated_candidates_first(self):
        rows = [
            video("Validated01", 20_000_000, True),
            video("Validated02", 10_000_000, True),
            video("Validated03", 8_000_000, True),
            video("Explore0001", 4_000_000, False),
        ]
        chosen = M.choose_new_candidates(rows, M.empty_cache(), 3, self.NOW)
        self.assertEqual([x["id"] for x in chosen], ["Validated01", "Validated02", "Validated03"])

    def test_limit_five_reserves_one_exploration_slot(self):
        rows = [
            video("Validated01", 20_000_000, True),
            video("Validated02", 10_000_000, True),
            video("Validated03", 8_000_000, True),
            video("Validated04", 7_000_000, True),
            video("Validated05", 6_000_000, True),
            video("Explore0001", 4_000_000, False),
        ]
        chosen = M.choose_new_candidates(rows, M.empty_cache(), 5, self.NOW)
        self.assertEqual(len(chosen), 5)
        self.assertIn("Explore0001", [x["id"] for x in chosen])
        self.assertNotIn("Validated05", [x["id"] for x in chosen])

    def test_success_is_cached_and_reused_next_run(self):
        data = {"videos": [video("AbCdEfGhI01", 9_000_000, True)]}
        cache = M.empty_cache()
        calls = []
        def analyzer(*args, **kwargs):
            calls.append(1)
            return success_report("편견·오해의 반전")
        out, cache = M.enrich_data(
            data, cache, limit=1, api_key="secret", analyzer=analyzer,
            now=self.NOW, sleeper=lambda _: None
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(out["geminiSummary"]["successes"], 1)
        self.assertIn("AbCdEfGhI01", cache["videos"])

        calls.clear()
        data2 = {"videos": [video("AbCdEfGhI01", 10_000_000, True)]}
        out2, _ = M.enrich_data(
            data2, cache, limit=1, api_key="secret", analyzer=analyzer,
            now="2026-09-27T13:00:00Z", sleeper=lambda _: None
        )
        self.assertEqual(calls, [])
        self.assertEqual(out2["geminiSummary"]["cacheHits"], 1)

    def test_one_503_moves_to_other_candidates(self):
        data = {"videos": [
            video("AbCdEfGhI01", 9_000_000, True),
            video("AbCdEfGhI02", 8_000_000, True),
            video("AbCdEfGhI03", 7_000_000, True),
        ]}
        cache = M.empty_cache()
        calls = []
        responses = [
            {"status": "failed", "httpStatus": 503, "apiStatus": "UNAVAILABLE"},
            success_report("재회"),
            success_report("가족애"),
        ]
        def analyzer(url, **kwargs):
            calls.append(url)
            return responses[len(calls)-1]
        out, cache = M.enrich_data(
            data, cache, limit=3, api_key="secret", analyzer=analyzer,
            now=self.NOW, sleeper=lambda _: None
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(out["geminiSummary"]["attempts"], 3)
        self.assertEqual(out["geminiSummary"]["successes"], 2)
        self.assertEqual(out["geminiSummary"]["deferred"], 1)
        self.assertFalse(out["geminiSummary"]["stoppedAfterError"])
        self.assertEqual(cache["videos"]["AbCdEfGhI01"]["status"], "deferred")

    def test_two_consecutive_503s_stop_before_third(self):
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
        out, _ = M.enrich_data(
            data, cache, limit=3, api_key="secret", analyzer=analyzer,
            now=self.NOW, sleeper=lambda _: None
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(out["geminiSummary"]["serviceFailures"], 2)
        self.assertTrue(out["geminiSummary"]["stoppedAfterError"])
        self.assertEqual(out["geminiSummary"]["stopCode"], "UNAVAILABLE")

    def test_429_stops_immediately(self):
        data = {"videos": [
            video("AbCdEfGhI01", 9_000_000, True),
            video("AbCdEfGhI02", 8_000_000, True),
        ]}
        calls = []
        def analyzer(url, **kwargs):
            calls.append(url)
            return {"status": "failed", "httpStatus": 429, "apiStatus": "RESOURCE_EXHAUSTED"}
        out, _ = M.enrich_data(
            data, M.empty_cache(), limit=2, api_key="secret", analyzer=analyzer,
            now=self.NOW, sleeper=lambda _: None
        )
        self.assertEqual(len(calls), 1)
        self.assertTrue(out["geminiSummary"]["stoppedAfterError"])
        self.assertEqual(out["geminiSummary"]["stopCode"], "RESOURCE_EXHAUSTED")

    def test_recent_deferred_video_is_skipped_then_retried_after_cooldown(self):
        cache = M.empty_cache()
        cache["videos"]["AbCdEfGhI01"] = {
            "status": "deferred",
            "deferredAt": "2026-09-27T10:00:00Z",
            "errorCode": "UNAVAILABLE",
        }
        data = {"videos": [
            video("AbCdEfGhI01", 9_000_000, True),
            video("AbCdEfGhI02", 8_000_000, True),
        ]}
        chosen = M.choose_new_candidates(data["videos"], cache, 2, self.NOW)
        self.assertNotIn("AbCdEfGhI01", [x["id"] for x in chosen])

        later = M.choose_new_candidates(
            data["videos"], cache, 2, "2026-09-27T17:00:01Z"
        )
        self.assertIn("AbCdEfGhI01", [x["id"] for x in later])

    def test_load_cache_preserves_deferred_rows(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cache.json"
            raw = M.empty_cache()
            raw["videos"]["AbCdEfGhI01"] = {
                "status": "deferred",
                "deferredAt": "2026-09-27T10:00:00Z",
                "errorCode": "UNAVAILABLE",
            }
            path.write_text(__import__("json").dumps(raw), encoding="utf-8")
            loaded = M.load_cache(path)
            self.assertEqual(loaded["videos"]["AbCdEfGhI01"]["status"], "deferred")

    def test_validated_deferred_candidate_is_carried_into_next_batch(self):
        old = video("AbCdEfGhI01", 9_000_000, True)
        old.update({"title": "strong old candidate", "channelId": "chan-old"})
        data = {"videos": [old]}
        cache = M.empty_cache()

        def fail_once(url, **kwargs):
            return {"status": "failed", "httpStatus": 503, "apiStatus": "UNAVAILABLE"}

        _, cache = M.enrich_data(
            data, cache, limit=1, api_key="secret", analyzer=fail_once,
            now="2026-09-27T10:00:00Z", sleeper=lambda _: None
        )
        self.assertIn("carryover", cache["videos"]["AbCdEfGhI01"])

        new_data = {"videos": [video("AbCdEfGhI02", 8_000_000, True)]}
        out, _ = M.enrich_data(
            new_data, cache, limit=0, api_key="",
            now="2026-09-27T12:00:00Z", sleeper=lambda _: None
        )
        self.assertEqual(out["videos"][0]["id"], "AbCdEfGhI01")
        self.assertTrue(out["videos"][0]["geminiCarryover"])
        self.assertEqual(out["videos"][0]["gemini"]["status"], "deferred")
        self.assertEqual(out["geminiSummary"]["carryoverCandidates"], 1)

    def test_missing_key_only_errors_when_new_call_is_needed(self):
        data = {"videos": [video("AbCdEfGhI01", 9_000_000, True)]}
        with self.assertRaises(M.EnrichError):
            M.enrich_data(data, M.empty_cache(), limit=1, api_key="", now=self.NOW)

    def test_limit_is_hard_bounded(self):
        with self.assertRaises(M.EnrichError):
            M.enrich_data({"videos": []}, M.empty_cache(), limit=9, api_key="", now=self.NOW)


if __name__ == "__main__":
    unittest.main()
