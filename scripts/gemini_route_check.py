#!/usr/bin/env python3
"""Isolated generateContent route check; dry-run unless --live is explicit.

Reuse the existing Lab model, prompt and schema. Never retry, follow a redirect,
fall back to another route/model, or modify site data. Preserve safe diagnostics
on failures; no API key, provider error message, or raw thoughts in reports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
from gemini_lab import DEFAULT_MODEL, PROMPT, LabError, canonical_youtube_url, schema, youtube_id

ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_MODEL}:generateContent"
TIMEOUT_SECONDS = 240
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ERROR_CODES = frozenset({
    "invalid_request", "failed_precondition", "parameter_unknown", "authentication",
    "payment_required", "permission_denied", "not_found", "model_not_found",
    "rate_limit_exceeded", "quota_exceeded", "too_many_requests", "api_error",
    "unimplemented", "service_unavailable", "deadline_exceeded", "cancelled",
    "INVALID_ARGUMENT", "FAILED_PRECONDITION", "UNAUTHENTICATED", "PERMISSION_DENIED",
    "NOT_FOUND", "RESOURCE_EXHAUSTED", "INTERNAL", "UNAVAILABLE", "DEADLINE_EXCEEDED",
})
USAGE_FIELDS = (
    "promptTokenCount", "cachedContentTokenCount", "candidatesTokenCount",
    "thoughtsTokenCount", "toolUsePromptTokenCount", "totalTokenCount",
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # No implicit second request or credential forwarding.


OPEN = build_opener(NoRedirect()).open


def request_payload(video_url: str) -> dict:
    """Provider wire format only changes; model/prompt/schema/media stay fixed."""
    return {
        "contents": [{"role": "user", "parts": [
            {"text": PROMPT},
            {"fileData": {"fileUri": canonical_youtube_url(video_url)}},
        ]}],
        "generationConfig": {
            "responseFormat": {"text": {"mimeType": "application/json", "schema": schema()}}
        },
    }


def schema_matches(value, spec: dict) -> bool:
    """Validate the object/array/string/boolean subset used by Lab v0.3."""
    kind = spec.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return False
        props = spec.get("properties", {})
        if any(key not in value for key in spec.get("required", [])):
            return False
        if spec.get("additionalProperties") is False and set(value) - set(props):
            return False
        return all(schema_matches(value[k], child) for k, child in props.items() if k in value)
    if kind == "array":
        return (isinstance(value, list)
                and spec.get("minItems", 0) <= len(value) <= spec.get("maxItems", float("inf"))
                and all(schema_matches(item, spec["items"]) for item in value))
    if kind == "boolean":
        return type(value) is bool
    if kind == "string":
        return isinstance(value, str) and ("enum" not in spec or value in spec["enum"])
    return False  # Fail closed if the shared schema later uses a new type.


def read_error(exc: HTTPError) -> tuple[str, int | None]:
    """Keep only allowlisted codes and numeric retry delay, never raw messages."""
    code = "unknown_http_error"
    delay = None
    try:
        payload = json.loads(exc.read(65536))
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            for candidate in (error.get("code"), error.get("status")):
                if isinstance(candidate, str) and candidate in ERROR_CODES:
                    code = candidate
                    break
    except (ValueError, TypeError, OSError, AttributeError, RecursionError, HTTPException):
        pass
    try:
        raw = (exc.headers or {}).get("Retry-After", "")
        if isinstance(raw, str) and re.fullmatch(r"[0-9]{1,5}", raw.strip()):
            delay = int(raw.strip())
    except (ValueError, TypeError, AttributeError):
        pass
    return code, delay


def consume_response(response: dict, report: dict) -> None:
    """Only an unblocked, finished, schema-valid response counts as success."""
    if not isinstance(response, dict):
        report["errorCode"] = "invalid_response_envelope"
        return
    usage = response.get("usageMetadata")
    if isinstance(usage, dict):
        report["usage"] = {k: usage[k] for k in USAGE_FIELDS
                           if type(usage.get(k)) is int and usage[k] >= 0} or None
    feedback = response.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        report["errorCode"] = "generation_blocked"
        return
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        report["errorCode"] = "missing_candidate"
        return
    candidate = candidates[0]
    if candidate.get("finishReason") != "STOP":
        report["errorCode"] = "generation_not_completed"
        return
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        report["errorCode"] = "missing_output_text"
        return
    text = "".join(p["text"] for p in parts
                   if isinstance(p, dict) and not p.get("thought") and isinstance(p.get("text"), str))
    try:
        analysis = json.loads(text)
    except (ValueError, RecursionError):
        report["errorCode"] = "invalid_analysis_json"
        return
    if not schema_matches(analysis, schema()):
        report["errorCode"] = "invalid_analysis_schema"
        return
    report.update(status="success", errorCode=None, schemaValid=True, analysis=analysis)


def run_check(video_url: str, *, live: bool = False, api_key: str = "") -> dict:
    payload = request_payload(video_url)  # Local validation before any connection.
    commit = os.environ.get("GITHUB_SHA", "")
    report = {
        "reportKind": "gemini-route-check", "probeVersion": "0.1", "labVersion": "0.3",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "gitCommit": commit if re.fullmatch(r"[0-9a-f]{40}", commit) else None,
        "route": "generateContent", "model": DEFAULT_MODEL,
        "videoId": youtube_id(video_url), "videoUrl": canonical_youtube_url(video_url),
        "promptSha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "schemaSha256": hashlib.sha256(json.dumps(schema(), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "status": "prepared", "attempts": 0, "httpStatus": None, "errorCode": None,
        "retryAfterSeconds": None, "elapsedSeconds": 0, "schemaValid": None,
        "analysis": None, "usage": None,
        "quotaConsumption": "not_measured", "billingEstimateUsd": None,
    }
    if not live:
        return report
    report["status"] = "failed"
    if not api_key.strip():
        report["errorCode"] = "missing_api_key"
        return report
    req = Request(ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                  headers={"x-goog-api-key": api_key.strip(), "Content-Type": "application/json",
                           "Accept": "application/json"}, method="POST")
    started = time.monotonic()
    report["attempts"] = 1
    try:
        with OPEN(req, timeout=TIMEOUT_SECONDS) as resp:
            report["httpStatus"] = resp.getcode()
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            report["errorCode"] = "response_too_large"
        else:
            consume_response(json.loads(raw), report)
    except HTTPError as exc:
        report["httpStatus"] = exc.code
        report["errorCode"], report["retryAfterSeconds"] = read_error(exc)
        exc.close()
    except (URLError, TimeoutError, OSError, HTTPException):
        report["errorCode"] = "network_error"
    except (ValueError, TypeError, RecursionError):
        report["errorCode"] = "invalid_response_json"
    finally:
        report["elapsedSeconds"] = round(time.monotonic() - started, 3)
    return report


def write_report(out_dir: Path, report: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "gemini-route-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Movie Radar Gemini Route Check", "",
             f"- 상태: **{report['status']}**", f"- 경로: `{report['route']}`",
             f"- 모델: `{report['model']}`", f"- 영상: `{report['videoId']}`",
             f"- 명시적 요청 시도: {report['attempts']}회 (재시도·자동 전환 없음)",
             f"- HTTP 상태: {report['httpStatus']}", f"- 안전한 오류 코드: {report['errorCode']}",
             f"- 서버가 안내한 대기 초: {report['retryAfterSeconds']}",
             f"- 경과 시간: {report['elapsedSeconds']}초", "",
             "> 실패 요청의 할당량 차감·청구 여부는 이 보고서로 확정하지 않습니다.",
             "> 경로 변경은 한도 우회가 아니며, 한 번의 성공도 안정성 검증은 아닙니다.", ""]
    if report["analysis"] is not None:
        lines += ["## v0.3 분석 결과", "", "```json",
                  json.dumps(report["analysis"], ensure_ascii=False, indent=2), "```", ""]
    lines += ["## 반환된 토큰 사용량", "", "```json",
              json.dumps(report["usage"], ensure_ascii=False, indent=2), "```", "",
              "`null`은 미제공/미확인입니다. 0으로 간주하지 않습니다."]
    (out_dir / "gemini-route-check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--youtube-url", required=True)
    p.add_argument("--live", action="store_true", help="실제 Gemini 요청을 최대 1회 전송")
    p.add_argument("--out", default="gemini-route-check-output")
    args = p.parse_args(argv)
    try:
        report = run_check(args.youtube_url, live=args.live,
                           api_key=os.environ.get("GEMINI_API_KEY", ""))
    except LabError:
        print("YouTube 영상 URL을 확인하세요. API를 호출하지 않았습니다.", file=sys.stderr)
        return 2
    write_report(Path(args.out), report)
    print(f"Route Check: {report['status']} / 요청 {report['attempts']}회 / "
          f"HTTP {report['httpStatus']} / {report['errorCode']}")
    return 2 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
