#!/usr/bin/env python3
"""One-shot YouTube video health check for Gemini 3.8 Flash.

Isolates YouTube video input from structured-output schema complexity.
Dry-run by default. --live sends exactly one request with no retry.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = "gemini-3.8-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
VIDEO_URL = "https://www.youtube.com/watch?v=gSu2ghFxoiY"
PROMPT = "이 영상에 실제로 보이는 핵심 사건을 한국어 한 문장으로만 요약하세요."
TIMEOUT_SECONDS = 240


def youtube_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url)
    if not m:
        raise ValueError("invalid YouTube URL")
    return m.group(1)


def safe_error_status(exc: HTTPError) -> str | None:
    try:
        payload = json.loads(exc.read(65536))
        error = payload.get("error") if isinstance(payload, dict) else None
        status = error.get("status") if isinstance(error, dict) else None
        if isinstance(status, str) and re.fullmatch(r"[A-Z_]{2,64}", status):
            return status
    except (ValueError, TypeError, OSError, AttributeError):
        pass
    return None


def extract_text(response: dict) -> str | None:
    try:
        parts = response["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return None
    texts = [p.get("text") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)]
    return "".join(texts).strip() if texts else None


def run(video_url: str, *, live: bool, api_key: str) -> dict:
    report = {
        "reportKind": "gemini-video-health",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model": MODEL,
        "videoId": youtube_id(video_url),
        "inputKind": "youtube_video_minimal",
        "structuredOutput": False,
        "status": "prepared",
        "attempts": 0,
        "httpStatus": None,
        "apiStatus": None,
        "elapsedSeconds": 0,
        "replyReceived": False,
        "usage": None,
    }
    if not live:
        return report
    if not api_key.strip():
        report.update(status="failed", apiStatus="MISSING_API_KEY")
        return report

    body = json.dumps({
        "contents": [{
            "role": "user",
            "parts": [
                {"text": PROMPT},
                {"fileData": {"fileUri": video_url}},
            ],
        }]
    }, ensure_ascii=False).encode("utf-8")

    req = Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={
            "x-goog-api-key": api_key.strip(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    report["status"] = "failed"
    report["attempts"] = 1
    started = time.monotonic()
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            report["httpStatus"] = resp.getcode()
            response = json.load(resp)
        text = extract_text(response)
        usage = response.get("usageMetadata") if isinstance(response, dict) else None
        if isinstance(usage, dict):
            allowed = ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "totalTokenCount")
            report["usage"] = {k: usage[k] for k in allowed if type(usage.get(k)) is int and usage[k] >= 0} or None
        if text:
            report["status"] = "success"
            report["replyReceived"] = True
    except HTTPError as exc:
        report["httpStatus"] = exc.code
        report["apiStatus"] = safe_error_status(exc)
        exc.close()
    except (URLError, TimeoutError, OSError, ValueError, TypeError):
        report["apiStatus"] = "NETWORK_OR_RESPONSE_ERROR"
    finally:
        report["elapsedSeconds"] = round(time.monotonic() - started, 3)
    return report


def write_report(out_dir: Path, report: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "gemini-video-health.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Movie Radar Gemini Video Health Check",
        "",
        f"- 상태: **{report['status']}**",
        f"- 모델: `{report['model']}`",
        f"- 영상 ID: `{report['videoId']}`",
        f"- 입력: `{report['inputKind']}`",
        f"- 구조화 출력/schema: {report['structuredOutput']}",
        f"- 실제 요청: {report['attempts']}회 (재시도 없음)",
        f"- HTTP: {report['httpStatus']}",
        f"- API 상태: {report['apiStatus']}",
        f"- 응답 텍스트 수신: {report['replyReceived']}",
        f"- 경과 시간: {report['elapsedSeconds']}초",
        "",
        "## 사용량",
        "",
        "```json",
        json.dumps(report["usage"], ensure_ascii=False, indent=2),
        "```",
        "",
        "> 성공하면 YouTube 영상 입력 자체는 동작한다는 증거가 됩니다.",
        "> 실패해도 한 번의 결과만으로 장기 안정성을 단정하지 않습니다.",
    ]
    (out_dir / "gemini-video-health.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--youtube-url", default=VIDEO_URL)
    p.add_argument("--live", action="store_true")
    p.add_argument("--out", default="gemini-video-health-output")
    args = p.parse_args(argv)

    report = run(args.youtube_url, live=args.live, api_key=os.environ.get("GEMINI_API_KEY", ""))
    write_report(Path(args.out), report)
    print(
        f"Video Health: {report['status']} / 요청 {report['attempts']}회 / "
        f"HTTP {report['httpStatus']} / {report['apiStatus']}"
    )
    return 0 if report["status"] in {"prepared", "success"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
