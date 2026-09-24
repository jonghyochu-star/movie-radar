#!/usr/bin/env python3
"""Movie Radar Gemini Lab v0.3

One-video blind evaluation using Gemini video understanding via a public YouTube URL.
- Never writes or prints GEMINI_API_KEY.
- Does not modify Movie Radar site data.
- Produces JSON + Markdown reports as GitHub Actions artifacts.
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

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_MODEL = "gemini-3.8-flash"
YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class LabError(Exception):
    pass


def youtube_id(url: str) -> str:
    """Accept public-looking YouTube video URLs and return the 11-char video ID."""
    from urllib.parse import urlparse, parse_qs

    if not isinstance(url, str) or len(url) > 500:
        raise LabError("YouTube URL 형식이 올바르지 않습니다.")
    u = urlparse(url.strip())
    if u.scheme != "https" or u.hostname not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"
    }:
        raise LabError("https:// 형식의 YouTube 영상 URL만 지원합니다.")
    vid = None
    if u.hostname == "youtu.be":
        vid = u.path.strip("/").split("/")[0] if u.path.strip("/") else None
    elif u.path == "/watch":
        vid = (parse_qs(u.query).get("v") or [None])[0]
    else:
        m = re.match(r"^/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})(?:/|$)", u.path)
        if m:
            vid = m.group(1)
    if not vid or not YT_ID.fullmatch(vid):
        raise LabError("영상 ID를 찾지 못했습니다. 채널 URL이 아닌 영상 URL을 넣어 주세요.")
    return vid


def canonical_youtube_url(url: str) -> str:
    return f"https://www.youtube.com/watch?v={youtube_id(url)}"


def schema() -> dict:
    """Compact schema: classification first, story analysis second."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "screen_scene_decision": {
                "type": "string",
                "enum": ["yes", "no", "uncertain"],
                "description": "Whether the video itself primarily shows a scripted movie/TV/short-film/animation scene rather than commentary, BTS, tutorial, interview, performance, real-life footage, product content, or gameplay."
            },
            "content_type": {
                "type": "string",
                "enum": [
                    "feature_film_scene", "tv_drama_scene", "short_film_scene", "animation_scene",
                    "behind_the_scenes", "interview_or_talk", "review_or_commentary",
                    "filmmaking_tutorial", "music_or_performance", "real_life_or_vlog",
                    "product_or_tech", "gameplay", "other", "uncertain"
                ]
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "why": {
                "type": "array", "minItems": 1, "maxItems": 4,
                "items": {"type": "string"},
                "description": "Short Korean paraphrases of concrete visual/audio evidence. Do not quote dialogue verbatim."
            },
            "relationship": {
                "type": "array", "maxItems": 4,
                "items": {"type": "string"},
                "description": "Visible relationship(s), in Korean. Keep this descriptive and do not infer hidden biography."
            },
            "primary_relationship": {
                "type": "string",
                "enum": [
                    "부모-자녀", "조부모-손자녀", "부부·연인", "친구", "동료",
                    "교사-학생", "권위자-시민", "낯선 사람", "가족 기타", "기타", "불명확"
                ],
                "description": "The relationship most central to the emotional event in this clip."
            },
            "story_pattern": {
                "type": "string",
                "enum": [
                    "뜻밖의 친절", "관계 회복", "용서·두 번째 기회", "존엄·인정",
                    "우정·연대", "희생·보호", "가족애", "유머 속 따뜻함",
                    "노력 끝의 인정", "재회", "편견·오해의 반전", "위기·구원",
                    "상실·위로", "로맨스", "성장", "기타", "불명확"
                ],
                "description": "Broad reusable story pattern, chosen descriptively rather than as a preference score."
            },
            "story_arc": {
                "type": "string",
                "enum": [
                    "갈등→이해→화해", "배려→위로", "희생→인정", "상실→위로",
                    "성장→인정", "유머→따뜻함", "우정→연대", "보호→안도",
                    "오해→진실→태도변화", "기타", "불명확"
                ]
            },
            "emotional_turn": {"type": "boolean"},
            "turn_timestamp": {
                "type": "string",
                "description": "MM:SS if a clear emotional/story turn is visible; otherwise empty string."
            },
            "story_completeness": {
                "type": "string", "enum": ["complete", "partial", "moment_only", "uncertain"]
            },
            "aftertaste": {"type": "string", "enum": ["strong", "medium", "weak", "uncertain"]},
            "emotional_payoff": {
                "type": "array", "maxItems": 3,
                "items": {
                    "type": "string",
                    "enum": ["따뜻함", "감동", "통쾌함", "안도", "슬픔", "애틋함", "웃음", "희망", "씁쓸함", "놀람", "기타", "불명확"]
                },
                "description": "What the ending or turn leaves the viewer feeling; descriptive, not a quality score."
            },
            "setup_clear": {"type": "boolean", "description": "Whether the clip itself establishes enough setup to follow the event."},
            "payoff_clear": {"type": "boolean", "description": "Whether the clip itself contains a visible emotional or story payoff."},
            "context_required": {"type": "boolean", "description": "True when outside film context is materially needed to understand why the scene matters."},
            "visual_dependency": {
                "type": "string", "enum": ["high", "medium", "low", "uncertain"],
                "description": "How much key story or emotion depends on visuals, expressions, actions, or editing rather than words."
            },
            "transcript_sufficiency": {
                "type": "string", "enum": ["likely", "maybe", "unlikely", "uncertain"],
                "description": "Whether a transcript alone would probably preserve enough information for first-pass story analysis."
            },
            "summary_ko": {
                "type": "string",
                "description": "2-4 sentence Korean summary of what actually happens in the video, without reproducing dialogue."
            },
            "preference_features": {
                "type": "array", "maxItems": 8,
                "items": {"type": "string"},
                "description": "Short Korean tags describing the story/emotional texture, not quality scores."
            }
        },
        "required": [
            "screen_scene_decision", "content_type", "confidence", "why", "relationship",
            "primary_relationship", "story_pattern", "story_arc", "emotional_turn", "turn_timestamp",
            "story_completeness", "aftertaste", "emotional_payoff", "setup_clear", "payoff_clear",
            "context_required", "visual_dependency", "transcript_sufficiency",
            "summary_ko", "preference_features"
        ]
    }


PROMPT = """당신은 Movie Radar의 블라인드 영상 분석기입니다.
이 분석은 사용자의 좋아요/별로 정답을 전혀 보지 않은 상태에서 수행합니다.

가장 먼저 이 YouTube 영상 자체가 '영화·TV 드라마·단편영화·애니메이션의 각본 장면'을 주로 보여주는지 판별하세요.
영화에 대해 말하는 리뷰/해설, 촬영법 강의, 메이킹/BTS, 배우 인터뷰, 오디션/공연,
실제 사람의 사연·브이로그, 제품/카메라 영상, 게임플레이는 screen_scene_decision=no 입니다.
제목이나 해시태그에 movie/film/shorts가 있다는 이유만으로 yes라고 하지 마세요.
영상의 시각과 음성을 실제로 확인해 판별하세요.

그 다음에만 장면의 관계, 사건 흐름, 감정 전환, 여운을 분석하세요.
사용자 취향에 맞는지, 많이 본 소재인지, 제작 후보인지 직접 판정하지 마세요.
대신 이후 사용자 기록과 비교할 수 있도록 핵심 관계와 넓은 이야기 패턴을 일관된 항목으로 분류하세요.
또한 이 장면을 자막/대사만으로 1차 분석해도 충분할지 판단할 수 있도록 시각 의존도와 transcript_sufficiency를 구분하세요.
표정·행동·무언의 반전처럼 화면이 핵심이면 visual_dependency를 높이고 transcript_sufficiency를 낮추세요.
확실하지 않으면 uncertain/불명확을 사용하세요. 작품명이나 제작국을 추측하지 마세요.
대사를 길게 인용하지 말고 한국어로 요약하세요. 숫자 점수는 만들지 마세요.
"""


def extract_output_text(response: dict) -> str:
    texts = []
    for step in response.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for part in step.get("content", []):
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
    if not texts:
        raise LabError("Gemini 응답에서 텍스트 결과를 찾지 못했습니다.")
    return "".join(texts)


def call_gemini(api_key: str, url: str, model: str = DEFAULT_MODEL) -> tuple[dict, dict]:
    payload = {
        "model": model,
        "input": [
            {"type": "text", "text": PROMPT},
            {"type": "video", "uri": canonical_youtube_url(url)},
        ],
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": schema(),
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    response = None
    retryable = {429, 500, 502, 503, 504}
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            with urlopen(req, timeout=240) as r:
                response = json.load(r)
            break
        except HTTPError as exc:
            # Never include body/URL because provider errors can echo request details.
            if exc.code in retryable and attempt < max_attempts - 1:
                retry_after = None
                try:
                    retry_after = int((exc.headers or {}).get("Retry-After", ""))
                except (ValueError, TypeError, AttributeError):
                    retry_after = None
                delay = retry_after if retry_after is not None else min(8, 2 ** attempt)
                print(f"Gemini 일시 오류 HTTP {exc.code}; {delay}초 뒤 재시도 {attempt + 2}/{max_attempts}.", file=sys.stderr)
                time.sleep(delay)
                continue
            messages = {
                400: "Gemini 요청 형식 또는 영상 URL을 확인하세요.",
                401: "Gemini API 인증에 실패했습니다. GEMINI_API_KEY를 확인하세요.",
                403: "Gemini API 사용 권한/프로젝트 설정을 확인하세요.",
                404: "요청 모델 또는 공개 영상을 찾지 못했습니다.",
                429: "Gemini API 사용 한도에 도달했습니다. 잠시 뒤 다시 시도하세요.",
                500: "Gemini 서비스가 일시적으로 불안정합니다. 잠시 뒤 다시 시도하세요.",
                502: "Gemini 서비스가 일시적으로 불안정합니다. 잠시 뒤 다시 시도하세요.",
                503: "Gemini 서비스가 일시적으로 혼잡하거나 불안정합니다. 자동 재시도 후에도 실패했습니다.",
                504: "Gemini 서비스 응답 시간이 초과되었습니다. 잠시 뒤 다시 시도하세요.",
            }
            raise LabError(messages.get(exc.code, f"Gemini API 요청 실패 (HTTP {exc.code}).")) from None
        except (URLError, TimeoutError):
            if attempt < max_attempts - 1:
                delay = min(8, 2 ** attempt)
                print(f"Gemini 네트워크 일시 오류; {delay}초 뒤 재시도 {attempt + 2}/{max_attempts}.", file=sys.stderr)
                time.sleep(delay)
                continue
            raise LabError("Gemini API 연결 시간이 초과되었거나 네트워크 요청에 실패했습니다.") from None
    if response is None:
        raise LabError("Gemini 응답을 받지 못했습니다.")
    if response.get("status") not in {None, "completed"}:
        raise LabError(f"Gemini 분석이 완료되지 않았습니다: {response.get('status', 'unknown')}")
    raw = extract_output_text(response)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise LabError("Gemini가 구조화된 JSON을 반환하지 않았습니다.") from None
    return result, response.get("usage") or {}


def estimate_cost_usd(usage: dict) -> dict:
    """Rough paid-tier estimate for Sep-Dec 2026 Gemini 3.8 Flash.

    Input $0.75/M. Output incl. thinking $3.75/M. Tool-use tokens are shown separately;
    we conservatively add them to input for a rough ceiling-like estimate.
    Actual billing can differ and the YouTube URL preview itself is currently no-charge.
    """
    inp = int(usage.get("total_input_tokens") or 0)
    tool = int(usage.get("total_tool_use_tokens") or 0)
    out = int(usage.get("total_output_tokens") or 0)
    thought = int(usage.get("total_thought_tokens") or 0)
    input_billable_est = inp + tool
    output_billable_est = out + thought
    usd = input_billable_est * 0.75 / 1_000_000 + output_billable_est * 3.75 / 1_000_000
    return {
        "input_tokens": inp,
        "tool_use_tokens": tool,
        "output_tokens": out,
        "thought_tokens": thought,
        "rough_paid_usd": round(usd, 6),
        "note": "2026-09~12 Gemini 3.8 Flash 공개 단가를 이용한 대략값입니다. 실제 청구액과 다를 수 있습니다. YouTube URL 입력 Preview 자체는 현재 무료로 안내됩니다."
    }


def comparison(expected: str, decision: str) -> dict:
    if expected == "unknown":
        return {"expected": expected, "comparable": False, "correct": None}
    if decision == "uncertain":
        return {"expected": expected, "comparable": True, "correct": False}
    predicted = "movie_drama" if decision == "yes" else "not_movie_drama"
    return {"expected": expected, "predicted": predicted, "comparable": True, "correct": predicted == expected}


def write_reports(out_dir: Path, video_url: str, model: str, result: dict, usage: dict, expected: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    vid = youtube_id(video_url)
    payload = {
        "schema": 1,
        "labVersion": "0.3",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "videoId": vid,
        "videoUrl": canonical_youtube_url(video_url),
        "model": model,
        "analysis": result,
        "comparison": comparison(expected, result.get("screen_scene_decision", "uncertain")),
        "usage": usage,
        "costEstimate": estimate_cost_usd(usage),
    }
    (out_dir / "gemini-lab-report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    c = payload["costEstimate"]
    comp = payload["comparison"]
    why = "\n".join(f"- {x}" for x in result.get("why", [])) or "- 없음"
    rel = ", ".join(result.get("relationship", [])) or "미확인"
    feats = ", ".join(result.get("preference_features", [])) or "없음"
    verdict = "비교 안 함" if not comp.get("comparable") else ("일치" if comp.get("correct") else "불일치")
    md = f"""# Movie Radar Gemini Lab v0.3\n\n- 영상 ID: `{vid}`\n- 모델: `{model}`\n- 사람이 넣은 정답: `{expected}`\n- 블라인드 비교: **{verdict}**\n\n## Gemini 판별\n\n- 실제 영화·드라마 계열 장면: **{result.get('screen_scene_decision')}**\n- 콘텐츠 유형: **{result.get('content_type')}**\n- 확신도: **{result.get('confidence')}**\n\n### 근거\n{why}\n\n## 이야기 분석\n\n- 관계: {rel}\n- 핵심 관계: {result.get('primary_relationship', '미확인')}\n- 이야기 패턴: {result.get('story_pattern', '불명확')}\n- 흐름: {result.get('story_arc')}\n- 감정 전환: {result.get('emotional_turn')}\n- 전환 시각: {result.get('turn_timestamp') or '없음'}\n- 이야기 완결성: {result.get('story_completeness')}\n- 시작 맥락 충분: {result.get('setup_clear')}\n- 결말/보상 명확: {result.get('payoff_clear')}\n- 외부 맥락 필요: {result.get('context_required')}\n- 여운: {result.get('aftertaste')}\n- 감정 보상: {', '.join(result.get('emotional_payoff') or []) or '불명확'}\n- 시각 의존도: {result.get('visual_dependency', 'uncertain')}\n- 자막만 1차 분석 가능성: {result.get('transcript_sufficiency', 'uncertain')}\n- 요약: {result.get('summary_ko')}\n- 이야기 특징: {feats}\n\n## 실제 API 사용량\n\n- 입력 토큰: {c['input_tokens']:,}\n- 도구 사용 토큰: {c['tool_use_tokens']:,}\n- 출력 토큰: {c['output_tokens']:,}\n- thinking 토큰: {c['thought_tokens']:,}\n- 유료 단가 기준 대략 비용: **${c['rough_paid_usd']:.6f}**\n\n> {c['note']}\n"""
    (out_dir / "gemini-lab-report.md").write_text(md, encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--youtube-url", required=True)
    p.add_argument("--expected", choices=["unknown", "movie_drama", "not_movie_drama"], default="unknown")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--out", default="gemini-lab-output")
    args = p.parse_args(argv)

    canonical_youtube_url(args.youtube_url)  # validate before touching the API
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise LabError("GEMINI_API_KEY Secret이 없습니다.")
    result, usage = call_gemini(key, args.youtube_url, args.model)
    write_reports(Path(args.out), args.youtube_url, args.model, result, usage, args.expected)
    print("Gemini Lab 분석 완료. 보고서는 Actions artifact에 저장됩니다.")
    print("판별:", result.get("screen_scene_decision"), "/", result.get("content_type"), "/ 확신도", result.get("confidence"))
    c = estimate_cost_usd(usage)
    print("토큰:", c["input_tokens"], "input /", c["tool_use_tokens"], "tool /", c["output_tokens"], "output /", c["thought_tokens"], "thought")
    print("대략 유료단가 비용(참고): $%.6f" % c["rough_paid_usd"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LabError as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(2)
