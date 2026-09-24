#!/usr/bin/env python3
"""Movie Radar Gemini Lab v0.2

Batch blind evaluation for up to 10 public YouTube videos.
Expected labels are compared only AFTER Gemini analysis and are never sent to the model.
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

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from gemini_lab import (
    DEFAULT_MODEL, LabError, call_gemini, canonical_youtube_url,
    comparison, estimate_cost_usd, youtube_id,
)

LABELS={"unknown","movie_drama","not_movie_drama"}
DEFAULT_REQUEST_GAP_SECONDS=6.0

def parse_urls(value: str, limit: int = 10) -> list[str]:
    if not isinstance(value,str):
        raise LabError("YouTube URL 목록이 필요합니다.")
    parts=[x.strip() for x in re.split(r"[\n,]+",value) if x.strip()]
    if not parts:
        raise LabError("YouTube URL을 하나 이상 넣어 주세요.")
    if len(parts)>limit:
        raise LabError(f"한 번에 최대 {limit}개까지 분석합니다.")
    out=[]
    for x in parts:
        u=canonical_youtube_url(x)
        if u not in out: out.append(u)
    return out

def parse_labels(value: str, count: int) -> list[str]:
    if not value or not value.strip():
        return ["unknown"]*count
    parts=[x.strip() for x in re.split(r"[\n,]+",value) if x.strip()]
    if len(parts)!=count:
        raise LabError("정답 라벨 수가 영상 수와 다릅니다.")
    if any(x not in LABELS for x in parts):
        raise LabError("정답 라벨은 unknown, movie_drama, not_movie_drama만 사용할 수 있습니다.")
    return parts

def summarize(rows: list[dict]) -> dict:
    comparable=[r for r in rows if r["comparison"].get("comparable")]
    correct=sum(bool(r["comparison"].get("correct")) for r in comparable)
    fp=fn=uncertain=0
    for r in comparable:
        exp=r["comparison"]["expected"]
        dec=r["analysis"].get("screen_scene_decision")
        if dec=="uncertain":
            uncertain+=1
        elif exp=="not_movie_drama" and dec=="yes":
            fp+=1
        elif exp=="movie_drama" and dec=="no":
            fn+=1
    total_tokens={"input_tokens":0,"tool_use_tokens":0,"output_tokens":0,"thought_tokens":0}
    total_cost=0.0
    for r in rows:
        c=r["costEstimate"]
        for k in total_tokens: total_tokens[k]+=int(c.get(k) or 0)
        total_cost+=float(c.get("rough_paid_usd") or 0)
    return {
        "videos":len(rows),
        "comparable":len(comparable),
        "correct":correct,
        "accuracy":round(correct/len(comparable),4) if comparable else None,
        "falsePositive":fp,
        "falseNegative":fn,
        "uncertain":uncertain,
        "totalUsage":total_tokens,
        "roughPaidUsd":round(total_cost,6),
        "averageRoughPaidUsd":round(total_cost/len(rows),6) if rows else 0,
    }

def write_report(out_dir: Path, rows: list[dict], model: str, batch_error: str = "") -> None:
    out_dir.mkdir(parents=True,exist_ok=True)
    summary=summarize(rows)
    payload={
        "schema":1,"labVersion":"0.2",
        "generatedAt":datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),
        "model":model,"summary":summary,"rows":rows,"batchError":batch_error or None,
    }
    (out_dir/"gemini-lab-batch.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# Movie Radar Gemini Lab v0.2","",f"- 모델: `{model}`",f"- 영상: **{summary['videos']}개**"]
    if summary["comparable"]:
        lines += [
            f"- 블라인드 비교: **{summary['correct']}/{summary['comparable']} 정답**",
            f"- 정확도: **{summary['accuracy']*100:.1f}%**",
            f"- 영화를 비영화로 놓침: **{summary['falseNegative']}**",
            f"- 비영화를 영화로 오탐: **{summary['falsePositive']}**",
            f"- 불확실 판정: **{summary['uncertain']}**",
        ]
    lines += [
        "- 총 유료 단가 환산 추정: **$" + f"{summary['roughPaidUsd']:.6f}**",
        "- 영상당 평균 추정: **$" + f"{summary['averageRoughPaidUsd']:.6f}**",
        "",
        "## 개별 결과","",
        "| # | 영상 ID | 사람 정답 | Gemini | 유형 | 확신 | 비교 | 대략 비용 |",
        "|---:|---|---|---|---|---|---|---:|",
    ]
    for i,r in enumerate(rows,1):
        comp=r["comparison"]
        verdict="—" if not comp.get("comparable") else ("✅" if comp.get("correct") else "❌")
        a=r["analysis"];c=r["costEstimate"]
        lines.append(f"| {i} | `{r['videoId']}` | {comp.get('expected')} | {a.get('screen_scene_decision')} | {a.get('content_type')} | {a.get('confidence')} | {verdict} | $" + f"{c.get('rough_paid_usd',0):.6f} |")
    lines += ["","## 이야기 특징",""]
    for i,r in enumerate(rows,1):
        a=r["analysis"]
        feats=", ".join(a.get("preference_features") or []) or "없음"
        lines += [f"### {i}. {r['videoId']}",f"- 요약: {a.get('summary_ko','')}",f"- 관계: {', '.join(a.get('relationship') or []) or '미확인'}",f"- 흐름: {a.get('story_arc')}",f"- 특징: {feats}",""]
    (out_dir/"gemini-lab-batch.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main(argv=None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--youtube-urls",required=True)
    p.add_argument("--expected-labels",default="")
    p.add_argument("--model",default=DEFAULT_MODEL)
    p.add_argument("--out",default="gemini-lab-batch-output")
    p.add_argument("--request-gap-seconds",type=float,default=float(os.environ.get("GEMINI_REQUEST_GAP_SECONDS","6")),
                   help="Successful video analyses are spaced by this many seconds to avoid burst RPM usage.")
    args=p.parse_args(argv)
    if not 0 <= args.request_gap_seconds <= 60:
        raise LabError("요청 간 대기 시간은 0~60초로 설정하세요.")
    urls=parse_urls(args.youtube_urls)
    labels=parse_labels(args.expected_labels,len(urls))
    key=os.environ.get("GEMINI_API_KEY","").strip()
    if not key: raise LabError("GEMINI_API_KEY Secret이 없습니다.")
    rows=[]
    out_dir=Path(args.out)
    for i,(url,expected) in enumerate(zip(urls,labels),1):
        print(f"[{i}/{len(urls)}] Gemini 분석 시작: {youtube_id(url)}", flush=True)
        try:
            analysis,usage=call_gemini(key,url,args.model)
        except LabError as exc:
            message=str(exc)
            write_report(out_dir,rows,args.model,message)
            (out_dir/"gemini-lab-batch-error.txt").write_text(
                f"{i}번째 영상({youtube_id(url)})에서 중단: {message}\n"
                f"완료된 영상: {len(rows)}/{len(urls)}\n", encoding="utf-8")
            print(f"배치 중단: {message} / 완료 {len(rows)}/{len(urls)}", flush=True)
            return 3
        rows.append({
            "videoId":youtube_id(url),"videoUrl":url,
            "analysis":analysis,
            "comparison":comparison(expected,analysis.get("screen_scene_decision","uncertain")),
            "usage":usage,"costEstimate":estimate_cost_usd(usage),
        })
        write_report(out_dir,rows,args.model)
        print(f"[{i}/{len(urls)}] 판별 {analysis.get('screen_scene_decision')} / {analysis.get('content_type')} / {analysis.get('confidence')}", flush=True)
        if i < len(urls) and args.request_gap_seconds > 0:
            print(f"다음 Gemini 요청까지 {args.request_gap_seconds:g}초 대기합니다.", flush=True)
            time.sleep(args.request_gap_seconds)
    s=summarize(rows)
    print("Gemini Lab batch 완료:",s["videos"],"개 / 비교",s["comparable"],"개 / 정답",s["correct"])
    print("대략 유료단가 총 비용(참고): $%.6f" % s["roughPaidUsd"])
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except LabError as exc:
        print("ERROR:",exc)
        raise SystemExit(2)
