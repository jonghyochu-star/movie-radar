#!/usr/bin/env python3
"""One-shot text-only Gemini health check.

Purpose: isolate model/API availability from YouTube video input.
Dry-run by default. --live sends exactly one request with no retry.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = "gemini-3.8-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PROMPT = "Reply with exactly OK."
TIMEOUT_SECONDS = 60


def safe_error_status(exc: HTTPError) -> str | None:
    try:
        raw = exc.read(65536)
        payload = json.loads(raw)
        error = payload.get("error") if isinstance(payload, dict) else None
        status = error.get("status") if isinstance(error, dict) else None
        if isinstance(status, str) and re.fullmatch(r"[A-Z_]{2,64}", status):
            return status
    except (ValueError, TypeError, OSError, AttributeError):
        pass
    return None


def extract_text(response: dict) -> str | None:
    try:
        candidates = response["candidates"]
        parts = candidates[0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return None
    texts = [p.get("text") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)]
    return "".join(texts).strip() if texts else None


def run(*, live: bool, api_key: str) -> dict:
    report = {
        "reportKind": "gemini-text-health",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model": MODEL,
        "inputKind": "text_only",
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
        report["status"] = "failed"
        report["apiStatus"] = "MISSING_API_KEY"
        return report

    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": PROMPT}]}]
    }).encode("utf-8")
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
    (out_dir / "gemini-text-health.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Movie Radar Gemini Text Health Check",
        "",
        f"- 상태: **{report['status']}**",
        f"- 모델: `{report['model']}`",
        f"- 입력: `{report['inputKind']}`",
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
        "> 이 검사는 텍스트만 사용합니다. 성공해도 YouTube 영상 입력 성공을 뜻하지 않습니다.",
    ]
    (out_dir / "gemini-text-health.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    p.add_argument("--out", default="gemini-text-health-output")
    args = p.parse_args(argv)

    report = run(live=args.live, api_key=os.environ.get("GEMINI_API_KEY", ""))
    write_report(Path(args.out), report)
    print(
        f"Text Health: {report['status']} / 요청 {report['attempts']}회 / "
        f"HTTP {report['httpStatus']} / {report['apiStatus']}"
    )
    return 0 if report["status"] in {"prepared", "success"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
