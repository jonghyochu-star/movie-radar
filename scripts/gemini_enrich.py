#!/usr/bin/env python3
"""Attach cached/limited Gemini v0.3 scene descriptors to Movie Radar candidates.

- Uses the proven plain-JSON generateContent path.
- API calls are opt-in via --limit > 0.
- Cached successful analyses are reused without new requests.
- At most --limit NEW requests are sent in one run.
- The first API/response failure stops further new requests for that run.
- Gemini describes scenes; it never creates user taste/production decisions.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from audience import audience_rank
from gemini_lab import DEFAULT_MODEL
from gemini_v03_plain import run as run_plain

CACHE_SCHEMA = 1
ANALYSIS_VERSION = "0.3-plain-local-schema-1"
MAX_NEW_CALLS = 8


class EnrichError(Exception):
    pass


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
        if (
            isinstance(vid, str)
            and len(vid) == 11
            and isinstance(row, dict)
            and isinstance(row.get("analysis"), dict)
            and isinstance(row.get("analyzedAt"), str)
        ):
            out["videos"][vid] = {
                "analysis": row["analysis"],
                "analyzedAt": row["analyzedAt"],
                "usage": row.get("usage") if isinstance(row.get("usage"), dict) else None,
            }
    return out


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def _site_payload(row: dict) -> dict:
    return {
        "status": "success",
        "version": ANALYSIS_VERSION,
        "model": DEFAULT_MODEL,
        "analyzedAt": row["analyzedAt"],
        "analysis": row["analysis"],
    }


def choose_new_candidates(videos: list[dict], cache: dict, limit: int) -> list[dict]:
    """Prefer audience-validated clips but reserve one exploration slot when possible."""
    if limit <= 0:
        return []
    rows = [
        v for v in videos
        if isinstance(v, dict)
        and isinstance(v.get("id"), str)
        and len(v["id"]) == 11
        and _cached_success(cache, v["id"]) is None
    ]
    validated = sorted(
        [v for v in rows if bool((v.get("audience") or {}).get("validated"))],
        key=_sort_key,
    )
    watch = sorted(
        [v for v in rows if not bool((v.get("audience") or {}).get("validated"))],
        key=_sort_key,
    )

    reserve_explore = 1 if limit >= 3 and watch else 0
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


def enrich_data(
    data: dict,
    cache: dict,
    *,
    limit: int,
    api_key: str,
    analyzer=run_plain,
    now: str | None = None,
) -> tuple[dict, dict]:
    if not isinstance(data, dict) or not isinstance(data.get("videos"), list):
        raise EnrichError("videos.json 형식이 올바르지 않습니다.")
    if limit < 0 or limit > MAX_NEW_CALLS:
        raise EnrichError(f"Gemini 신규 분석은 실행당 0~{MAX_NEW_CALLS}개만 허용합니다.")

    stamp = now or iso_now()
    videos = data["videos"]
    cache_hits = 0
    for video in videos:
        vid = video.get("id") if isinstance(video, dict) else None
        if not isinstance(vid, str):
            continue
        row = _cached_success(cache, vid)
        if row:
            video["gemini"] = _site_payload(row)
            cache_hits += 1

    selected = choose_new_candidates(videos, cache, limit)
    attempts = successes = deferred = 0
    stopped_after_error = False
    stop_code = None

    if selected and not api_key.strip():
        raise EnrichError("GEMINI_API_KEY가 없어서 요청된 Gemini enrichment를 실행할 수 없습니다.")

    for video in selected:
        vid = video["id"]
        attempts += 1
        report = analyzer(
            f"https://www.youtube.com/watch?v={vid}",
            live=True,
            api_key=api_key,
        )
        if report.get("status") == "success" and isinstance(report.get("analysis"), dict):
            row = {
                "analysis": report["analysis"],
                "analyzedAt": stamp,
                "usage": report.get("usage") if isinstance(report.get("usage"), dict) else None,
            }
            cache["videos"][vid] = row
            video["gemini"] = _site_payload(row)
            successes += 1
            continue

        error_code = report.get("apiStatus") or (
            f"HTTP_{report.get('httpStatus')}" if report.get("httpStatus") else "ANALYSIS_FAILED"
        )
        video["gemini"] = {
            "status": "deferred",
            "version": ANALYSIS_VERSION,
            "model": DEFAULT_MODEL,
            "analyzedAt": stamp,
            "errorCode": str(error_code)[:80],
        }
        deferred += 1
        stopped_after_error = True
        stop_code = str(error_code)[:80]
        break

    summary = {
        "method": ANALYSIS_VERSION,
        "model": DEFAULT_MODEL,
        "newCallLimit": limit,
        "cacheHits": cache_hits,
        "selectedForNewAnalysis": len(selected),
        "attempts": attempts,
        "successes": successes,
        "deferred": deferred,
        "stoppedAfterError": stopped_after_error,
        "stopCode": stop_code,
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
        f"cache {s['cacheHits']} / 신규시도 {s['attempts']} / 성공 {s['successes']} / 보류 {s['deferred']}"
    )
    if s["stoppedAfterError"]:
        print("Gemini enrichment는 첫 오류에서 추가 호출을 중단했습니다:", s["stopCode"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
