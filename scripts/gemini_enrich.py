#!/usr/bin/env python3
"""Attach cached/limited Gemini v0.3 scene descriptors to Movie Radar candidates.

- Uses the proven plain-JSON generateContent path.
- API calls are opt-in via --limit > 0.
- Cached successful analyses are reused without new requests.
- Recently deferred videos cool down instead of blocking every later run.
- At most --limit NEW requests are sent in one run.
- Quota/auth failures stop immediately.
- One transient service failure moves to another video; two consecutive service
  failures stop the run to protect the free-tier quota.
- Gemini describes scenes; it never creates user taste/production decisions.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from audience import audience_rank
from gemini_lab import DEFAULT_MODEL
from gemini_v03_plain import run as run_plain

CACHE_SCHEMA = 1
ANALYSIS_VERSION = "0.3-plain-local-schema-1"
MAX_NEW_CALLS = 8
DEFER_HOURS = 6
REQUEST_GAP_SECONDS = 8.0
TRANSIENT_CODES = {
    "UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED", "NETWORK_OR_RESPONSE_ERROR",
    "HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504",
}
HARD_STOP_CODES = {
    "RESOURCE_EXHAUSTED", "UNAUTHENTICATED", "PERMISSION_DENIED",
    "QUOTA_EXCEEDED", "RATE_LIMIT_EXCEEDED", "MISSING_API_KEY",
    "HTTP_401", "HTTP_403", "HTTP_429",
}


class EnrichError(Exception):
    pass


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _dt(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def empty_cache() -> dict:
    return {
        "schema": CACHE_SCHEMA,
        "analysisVersion": ANALYSIS_VERSION,
        "model": DEFAULT_MODEL,
        "videos": {},
    }


def load_cache(path: Path) -> dict:
    if not path.exists():
        return empty_cache()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_cache()
    if (
        not isinstance(raw, dict)
        or raw.get("schema") != CACHE_SCHEMA
        or raw.get("analysisVersion") != ANALYSIS_VERSION
        or raw.get("model") != DEFAULT_MODEL
        or not isinstance(raw.get("videos"), dict)
    ):
        return empty_cache()

    out = empty_cache()
    for vid, row in raw["videos"].items():
        if not (isinstance(vid, str) and len(vid) == 11 and isinstance(row, dict)):
            continue
        if isinstance(row.get("analysis"), dict) and isinstance(row.get("analyzedAt"), str):
            out["videos"][vid] = {
                "status": "success",
                "analysis": row["analysis"],
                "analyzedAt": row["analyzedAt"],
                "usage": row.get("usage") if isinstance(row.get("usage"), dict) else None,
            }
        elif (
            row.get("status") == "deferred"
            and isinstance(row.get("deferredAt"), str)
            and isinstance(row.get("errorCode"), str)
        ):
            item = {
                "status": "deferred",
                "deferredAt": row["deferredAt"],
                "errorCode": row["errorCode"][:80],
            }
            if isinstance(row.get("carryover"), dict) and row["carryover"].get("id") == vid:
                item["carryover"] = row["carryover"]
            out["videos"][vid] = item
    return out


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


CARRYOVER_FIELDS = (
    "language", "languageBasis", "audioLanguage", "declaredLanguage",
    "languageSource", "titleLanguage", "titleLanguageBasis",
    "screenKind", "screenReason", "metadataVersion", "id", "title",
    "channelTitle", "channelId", "views", "subscribers", "publishedAt",
    "fetchedAt", "durationSeconds", "audience", "thumbnail",
    "originalStatus", "source", "discoveryRoutes", "discoveryLabels",
    "sourceKinds", "screenGate", "shortsHint",
)


def compact_candidate(video: dict) -> dict:
    return {k: video[k] for k in CARRYOVER_FIELDS if k in video}


def recover_deferred_carryovers(cache: dict, prior_data: dict) -> int:
    """Migrate old deferred cache rows using the previous public deployment."""
    if not isinstance(prior_data, dict) or not isinstance(prior_data.get("videos"), list):
        return 0
    by_id = {
        v.get("id"): v for v in prior_data["videos"]
        if isinstance(v, dict) and isinstance(v.get("id"), str)
    }
    recovered = 0
    for vid, row in (cache.get("videos") or {}).items():
        if not isinstance(row, dict) or row.get("status") != "deferred" or isinstance(row.get("carryover"), dict):
            continue
        video = by_id.get(vid)
        if not isinstance(video, dict) or not bool((video.get("audience") or {}).get("validated")):
            continue
        row["carryover"] = compact_candidate(video)
        recovered += 1
    return recovered


def load_prior_pages(repository: str) -> dict | None:
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        return None
    owner, repo = repository.split("/", 1)
    url = f"https://{owner}.github.io/{repo}/data/videos.json?t={int(time.time())}"
    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "MovieRadar/1.9.4"})
        with urlopen(req, timeout=10) as response:
            data = json.load(response)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _views(video: dict) -> int:
    value = video.get("views")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _sort_key(video: dict):
    return (audience_rank(video), -_views(video), str(video.get("id", "")))


def _cached_success(cache: dict, vid: str) -> dict | None:
    row = (cache.get("videos") or {}).get(vid)
    if not isinstance(row, dict) or not isinstance(row.get("analysis"), dict):
        return None
    return row


def _active_deferred(cache: dict, vid: str, now: str) -> dict | None:
    row = (cache.get("videos") or {}).get(vid)
    if not isinstance(row, dict) or row.get("status") != "deferred":
        return None
    at = _dt(row.get("deferredAt"))
    current = _dt(now)
    if not at or not current:
        return None
    if current - at < timedelta(hours=DEFER_HOURS):
        return row
    return None


def _site_success(row: dict) -> dict:
    return {
        "status": "success",
        "version": ANALYSIS_VERSION,
        "model": DEFAULT_MODEL,
        "analyzedAt": row["analyzedAt"],
        "analysis": row["analysis"],
    }


def _site_deferred(row: dict) -> dict:
    return {
        "status": "deferred",
        "version": ANALYSIS_VERSION,
        "model": DEFAULT_MODEL,
        "analyzedAt": row.get("deferredAt"),
        "errorCode": str(row.get("errorCode") or "ANALYSIS_FAILED")[:80],
    }


def choose_new_candidates(videos: list[dict], cache: dict, limit: int, now: str | None = None) -> list[dict]:
    """Prefer audience-validated clips but reserve one exploration slot when possible."""
    if limit <= 0:
        return []
    stamp = now or iso_now()
    rows = [
        v for v in videos
        if isinstance(v, dict)
        and isinstance(v.get("id"), str)
        and len(v["id"]) == 11
        and _cached_success(cache, v["id"]) is None
        and _active_deferred(cache, v["id"], stamp) is None
    ]
    validated = sorted(
        [v for v in rows if bool((v.get("audience") or {}).get("validated"))],
        key=_sort_key,
    )
    watch = sorted(
        [v for v in rows if not bool((v.get("audience") or {}).get("validated"))],
        key=_sort_key,
    )

    # With a tiny free-tier budget (3), spend every call on audience-validated
    # candidates first. From 5+ calls, reserve one slot for exploration.
    reserve_explore = 1 if limit >= 5 and watch else 0
    selected = validated[: max(0, limit - reserve_explore)]
    selected_ids = {v["id"] for v in selected}

    if reserve_explore:
        selected.append(watch[0])
        selected_ids.add(watch[0]["id"])

    if len(selected) < limit:
        remaining = sorted(
            [v for v in rows if v["id"] not in selected_ids],
            key=_sort_key,
        )
        selected.extend(remaining[: limit - len(selected)])
    return selected[:limit]


def _error_code(report: dict) -> str:
    return str(
        report.get("apiStatus")
        or (f"HTTP_{report.get('httpStatus')}" if report.get("httpStatus") else "ANALYSIS_FAILED")
    )[:80]


def _is_hard_stop(report: dict, code: str) -> bool:
    return report.get("httpStatus") in {401, 403, 429} or code in HARD_STOP_CODES


def _is_transient(report: dict, code: str) -> bool:
    status = report.get("httpStatus")
    return status in {500, 502, 503, 504} or code in TRANSIENT_CODES


def enrich_data(
    data: dict,
    cache: dict,
    *,
    limit: int,
    api_key: str,
    analyzer=run_plain,
    now: str | None = None,
    sleeper=time.sleep,
    request_gap_seconds: float = REQUEST_GAP_SECONDS,
) -> tuple[dict, dict]:
    if not isinstance(data, dict) or not isinstance(data.get("videos"), list):
        raise EnrichError("videos.json 형식이 올바르지 않습니다.")
    if limit < 0 or limit > MAX_NEW_CALLS:
        raise EnrichError(f"Gemini 신규 분석은 실행당 0~{MAX_NEW_CALLS}개만 허용합니다.")

    stamp = now or iso_now()
    videos = data["videos"]

    # Carry forward audience-validated videos that previously hit a Gemini
    # service error. This bypasses collector duplicate history only for the
    # bounded retry queue; it does not revive ordinary old candidates.
    present = {v.get("id") for v in videos if isinstance(v, dict)}
    carryovers = []
    for vid, row in (cache.get("videos") or {}).items():
        candidate = row.get("carryover") if isinstance(row, dict) else None
        if (
            vid not in present
            and isinstance(candidate, dict)
            and candidate.get("id") == vid
            and bool((candidate.get("audience") or {}).get("validated"))
        ):
            copy = json.loads(json.dumps(candidate))
            copy["geminiCarryover"] = True
            carryovers.append(copy)
    carryovers.sort(key=_sort_key)
    if carryovers:
        videos[:0] = carryovers[:MAX_NEW_CALLS]

    cache_hits = cooldown_hits = 0

    for video in videos:
        vid = video.get("id") if isinstance(video, dict) else None
        if not isinstance(vid, str):
            continue
        success = _cached_success(cache, vid)
        if success:
            video["gemini"] = _site_success(success)
            cache_hits += 1
            continue
        deferred_row = _active_deferred(cache, vid, stamp)
        if deferred_row:
            video["gemini"] = _site_deferred(deferred_row)
            cooldown_hits += 1

    selected = choose_new_candidates(videos, cache, limit, stamp)
    attempts = successes = deferred = service_failures = 0
    stopped_after_error = False
    stop_code = None
    consecutive_transient = 0

    if selected and not api_key.strip():
        raise EnrichError("GEMINI_API_KEY가 없어서 요청된 Gemini enrichment를 실행할 수 없습니다.")

    for video in selected:
        if attempts > 0 and request_gap_seconds > 0:
            sleeper(request_gap_seconds)

        vid = video["id"]
        attempts += 1
        report = analyzer(
            f"https://www.youtube.com/watch?v={vid}",
            live=True,
            api_key=api_key,
        )

        if report.get("status") == "success" and isinstance(report.get("analysis"), dict):
            row = {
                "status": "success",
                "analysis": report["analysis"],
                "analyzedAt": stamp,
                "usage": report.get("usage") if isinstance(report.get("usage"), dict) else None,
            }
            cache["videos"][vid] = row
            video["gemini"] = _site_success(row)
            successes += 1
            consecutive_transient = 0
            continue

        code = _error_code(report)
        row = {"status": "deferred", "deferredAt": stamp, "errorCode": code}
        if bool((video.get("audience") or {}).get("validated")):
            # Keep only the bounded public candidate snapshot needed to retry a
            # strong video even after the collector's duplicate history moves on.
            row["carryover"] = compact_candidate(video)
        cache["videos"][vid] = row
        video["gemini"] = _site_deferred(row)
        deferred += 1

        if _is_hard_stop(report, code):
            stopped_after_error = True
            stop_code = code
            break

        if _is_transient(report, code):
            service_failures += 1
            consecutive_transient += 1
            if consecutive_transient >= 2:
                stopped_after_error = True
                stop_code = code
                break
            continue

        # Candidate-specific parse/input problems do not block the next candidate.
        consecutive_transient = 0

    summary = {
        "method": ANALYSIS_VERSION,
        "model": DEFAULT_MODEL,
        "newCallLimit": limit,
        "cacheHits": cache_hits,
        "cooldownHits": cooldown_hits,
        "carryoverCandidates": len(carryovers[:MAX_NEW_CALLS]),
        "selectedForNewAnalysis": len(selected),
        "attempts": attempts,
        "successes": successes,
        "deferred": deferred,
        "serviceFailures": service_failures,
        "stoppedAfterError": stopped_after_error,
        "stopCode": stop_code,
        "deferHours": DEFER_HOURS,
    }
    data["geminiSummary"] = summary
    return data, cache


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="site/data/videos.json")
    p.add_argument("--cache", default=".cache/movie-radar/gemini-v03.json")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args(argv)

    source = Path(args.input)
    cache_path = Path(args.cache)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        cache = load_cache(cache_path)
        recovered = recover_deferred_carryovers(
            cache,
            load_prior_pages(os.environ.get("GITHUB_REPOSITORY", "")) or {},
        )
        if recovered:
            print(f"Gemini carry-over migration: 이전 배포에서 강한 보류 후보 {recovered}개 복구")
        data, cache = enrich_data(
            data,
            cache,
            limit=args.limit,
            api_key=os.environ.get("GEMINI_API_KEY", ""),
        )
        source.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        save_cache(cache_path, cache)
    except (OSError, json.JSONDecodeError, EnrichError) as exc:
        print("ERROR:", exc)
        return 2

    s = data["geminiSummary"]
    print(
        "Gemini enrichment:",
        f"cache {s['cacheHits']} / cooldown {s['cooldownHits']} / "
        f"신규시도 {s['attempts']} / 성공 {s['successes']} / 보류 {s['deferred']}"
    )
    if s["stoppedAfterError"]:
        print("Gemini enrichment는 보호 규칙에 따라 추가 호출을 중단했습니다:", s["stopCode"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
