#!/usr/bin/env python3
"""Movie Radar v0.3 one-shot analysis without server-side structured output.

Uses the proven generateContent + public YouTube URL path.
The model is asked for JSON in the prompt; JSON/schema validation happens locally.
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

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from gemini_lab import DEFAULT_MODEL, PROMPT, canonical_youtube_url, schema, youtube_id

ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_MODEL}:generateContent"
TIMEOUT_SECONDS = 240
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def build_prompt() -> str:
    compact_schema = json.dumps(schema(), ensure_ascii=False, separators=(",", ":"))
    return (
        PROMPT
        + "\n\n이번 요청에서는 서버의 structured-output 기능을 사용하지 않습니다. "
          "대신 아래 JSON Schema를 직접 따라 결과를 만드세요. "
          "반드시 JSON 객체 하나만 반환하고, 마크다운 코드블록이나 JSON 앞뒤 설명문은 쓰지 마세요.\n"
        + compact_schema
    )


def schema_matches(value, spec: dict) -> bool:
    kind = spec.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return False
        props = spec.get("properties", {})
        if any(k not in value for k in spec.get("required", [])):
            return False
        if spec.get("additionalProperties") is False and set(value) - set(props):
            return False
        return all(schema_matches(value[k], child) for k, child in props.items() if k in value)
    if kind == "array":
        if not isinstance(value, list):
            return False
        if len(value) < spec.get("minItems", 0) or len(value) > spec.get("maxItems", float("inf")):
            return False
        return all(schema_matches(x, spec["items"]) for x in value)
    if kind == "boolean":
        return type(value) is bool
    if kind == "string":
        return isinstance(value, str) and ("enum" not in spec or value in spec["enum"])
    return False


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


def extract_model_text(response: dict) -> str | None:
    try:
        parts = response["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return None
    texts = [
        p["text"] for p in parts
        if isinstance(p, dict) and not p.get("thought") and isinstance(p.get("text"), str)
    ]
    return "".join(texts).strip() if texts else None


def parse_json_object(text: str) -> dict | None:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    try:
        obj = json.loads(value)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(value[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def run(video_url: str, *, live: bool, api_key: str) -> dict:
    report = {
        "reportKind": "gemini-v03-plain-json",
        "labVersion": "0.3",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model": DEFAULT_MODEL,
        "videoId": youtube_id(video_url),
        "route": "generateContent",
        "serverStructuredOutput": False,
        "status": "prepared",
        "attempts": 0,
        "httpStatus": None,
        "apiStatus": None,
        "elapsedSeconds": 0,
        "jsonParsed": False,
        "schemaValid": False,
        "analysis": None,
        "usage": None,
    }
    if not live:
        return report
    if not api_key.strip():
        report.update(status="failed", apiStatus="MISSING_API_KEY")
        return report

    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": build_prompt()},
                {"fileData": {"fileUri": canonical_youtube_url(video_url)}},
            ],
        }]
    }
    req = Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
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
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            report["apiStatus"] = "RESPONSE_TOO_LARGE"
            return report
        response = json.loads(raw)
        usage = response.get("usageMetadata") if isinstance(response, dict) else None
        if isinstance(usage, dict):
            allowed = (
                "promptTokenCount", "cachedContentTokenCount", "candidatesTokenCount",
                "thoughtsTokenCount", "toolUsePromptTokenCount", "totalTokenCount",
            )
            report["usage"] = {
                k: usage[k] for k in allowed
                if type(usage.get(k)) is int and usage[k] >= 0
            } or None

        text = extract_model_text(response)
        if not text:
            report["apiStatus"] = "MISSING_OUTPUT_TEXT"
            return report
        result = parse_json_object(text)
        if result is None:
            report["apiStatus"] = "INVALID_JSON"
            return report
        report["jsonParsed"] = True
        if not schema_matches(result, schema()):
            report["apiStatus"] = "SCHEMA_MISMATCH"
            return report

        report.update(
            status="success",
            apiStatus=None,
            schemaValid=True,
            analysis=result,
        )
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
    (out_dir / "gemini-v03-plain.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Movie Radar Gemini v0.3 Plain JSON",
        "",
        f"- 상태: **{report['status']}**",
        f"- 모델: `{report['model']}`",
        f"- 영상 ID: `{report['videoId']}`",
        f"- 서버 structured output: {report['serverStructuredOutput']}",
        f"- 실제 요청: {report['attempts']}회 (재시도 없음)",
        f"- HTTP: {report['httpStatus']}",
        f"- API/로컬 상태: {report['apiStatus']}",
        f"- JSON 파싱: {report['jsonParsed']}",
        f"- v0.3 schema 검증: {report['schemaValid']}",
        f"- 경과 시간: {report['elapsedSeconds']}초",
        "",
    ]
    if report["analysis"] is not None:
        lines += [
            "## v0.3 분석 결과",
            "",
            "```json",
            json.dumps(report["analysis"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    lines += [
        "## 사용량",
        "",
        "```json",
        json.dumps(report["usage"], ensure_ascii=False, indent=2),
        "```",
        "",
        "> 이 경로는 서버의 JSON schema 강제 기능을 쓰지 않고 로컬에서 형식을 검증합니다.",
    ]
    (out_dir / "gemini-v03-plain.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--youtube-url", required=True)
    p.add_argument("--live", action="store_true")
    p.add_argument("--out", default="gemini-v03-plain-output")
    args = p.parse_args(argv)

    report = run(
        args.youtube_url,
        live=args.live,
        api_key=os.environ.get("GEMINI_API_KEY", ""),
    )
    write_report(Path(args.out), report)
    print(
        f"v0.3 Plain: {report['status']} / 요청 {report['attempts']}회 / "
        f"HTTP {report['httpStatus']} / {report['apiStatus']}"
    )
    return 0 if report["status"] in {"prepared", "success"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
