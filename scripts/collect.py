"""Build Movie Radar's public snapshot. Standard library only; no video download.
YOUTUBE_API_KEY must be provided by an environment variable / GitHub Secret.
No API key, private ratings, or notes are written into the public output.
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
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
CHANNEL = re.compile(r"^UC[A-Za-z0-9_-]{22}$")

class CollectionError(Exception):
    """Safe error message: never include request URL / credentials."""

def number(value):
    try:
        result = int(value)
        return result if result >= 0 else None
    except (ValueError, TypeError):
        return None

def duration_seconds(text):
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text or "")
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(x or 0) for x in match.groups())
    return hours * 3600 + minutes * 60 + seconds

def chunks(values, size=50):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start:start+size]

def timestamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def load_config(path):
    try:
        c = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CollectionError("config.json을 읽지 못했습니다. JSON 쉼표·따옴표를 확인하세요.") from exc
    if not isinstance(c, dict):
        raise CollectionError("config.json은 객체 형식이어야 합니다.")
    defaults = {"queries_per_run":4, "recent_days":30, "archive_days":0,
                "results_per_search":50, "max_videos":400, "min_seconds":10, "max_seconds":180}
    limits = {"queries_per_run":(1,4),"recent_days":(1,3650),"archive_days":(0,36500),
              "results_per_search":(1,50),"max_videos":(1,500),"min_seconds":(0,180),"max_seconds":(1,180)}
    for key, default in defaults.items():
        value = c.get(key, default)
        low, high = limits[key]
        if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:
            raise CollectionError(f"config.json의 {key}는 {low}~{high} 정수여야 합니다.")
        c[key] = value
    if c["min_seconds"]>c["max_seconds"]:
        raise CollectionError("min_seconds는 max_seconds보다 클 수 없습니다.")
    queries = c.get("queries", [])
    if not isinstance(queries,list) or not all(isinstance(q,str) and 0<len(q)<=150 for q in queries):
        raise CollectionError("queries에는 짧은 검색어 문자열을 넣으세요.")
    c["queries"] = list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:50]
    for field, pattern, maximum in [("channel_ids", CHANNEL, 5), ("video_ids", ID, 100)]:
        entries = c.get(field, [])
        if not isinstance(entries,list) or len(entries)>maximum or not all(isinstance(x,str) and pattern.fullmatch(x) for x in entries):
            raise CollectionError(f"{field} 형식이 잘못되었습니다. ID만 최대 {maximum}개 입력하세요.")
        c[field] = list(dict.fromkeys(entries))
    if not (c["queries"] or c["channel_ids"] or c["video_ids"]):
        raise CollectionError("검색어 또는 수집할 영상·채널 ID가 하나 이상 필요합니다.")
    c["relevance_language"] = c.get("relevance_language", "en")
    c["region_code"] = c.get("region_code", "US")
    if not re.fullmatch(r"[a-z]{2}",str(c["relevance_language"])) or not re.fullmatch(r"[A-Z]{2}",str(c["region_code"])):
        raise CollectionError("언어는 en, 지역은 US와 같은 두 글자 코드여야 합니다.")
    return c

class YouTube:
    def __init__(self, key):
        if not key:
            raise CollectionError("YOUTUBE_API_KEY Secret이 없습니다. 샘플은 mode=demo, 실제 수집은 Secret 등록 후 mode=live로 실행하세요.")
        self.key = key
        self.calls = {}
    def get(self, endpoint, **params):
        if endpoint not in {"search", "videos", "channels", "playlistItems"}:
            raise CollectionError("허용되지 않은 API 경로입니다.")
        # Key in header, never in a URL, log, traceback, or generated file.
        req = Request("https://www.googleapis.com/youtube/v3/"+endpoint+"?"+urlencode(params),
                      headers={"X-Goog-Api-Key":self.key, "Accept":"application/json"})
        for attempt in range(3):
            self.calls[endpoint] = self.calls.get(endpoint,0)+1
            try:
                with urlopen(req, timeout=30) as response:
                    result = json.load(response)
                if not isinstance(result,dict) or not isinstance(result.get("items",[]),list):
                    raise CollectionError("YouTube 응답 형식이 올바르지 않습니다.")
                return result
            except HTTPError as exc:
                if exc.code in {429,500,502,503,504} and attempt<2:
                    time.sleep(2**attempt);continue
                reason = ""
                try:
                    raw = json.loads(exc.read().decode("utf-8"))
                    reason = raw.get("error",{}).get("errors",[{}])[0].get("reason","")
                except (ValueError, KeyError, IndexError, AttributeError):
                    pass
                messages = {
                    "quotaExceeded":"YouTube 호출 한도를 초과했습니다. 추가 실행을 중단하고 해당 프로젝트 할당량을 확인하세요.",
                    "dailyLimitExceeded":"YouTube 일일 호출 한도를 초과했습니다.",
                    "keyInvalid":"API 키가 올바르지 않습니다. Secret을 확인하세요.",
                    "accessNotConfigured":"Google Cloud에서 YouTube Data API v3를 활성화하세요.",
                    "ipRefererBlocked":"API 키의 앱 제한이 GitHub Actions 요청을 차단했습니다. 서버용 키의 제한을 확인하세요.",
                    "forbidden":"YouTube API 접근이 거부되었습니다. API 활성화·키 제한을 확인하세요.",
                }
                raise CollectionError(messages.get(reason,f"YouTube 요청 실패 (HTTP {exc.code}). API 활성화·키 제한·할당량을 확인하세요.")) from None
            except (URLError,TimeoutError) as exc:
                if attempt<2:time.sleep(2**attempt);continue
                raise CollectionError("YouTube 연결에 실패했습니다. 기존 배포는 유지됩니다.") from None
            except ValueError:
                raise CollectionError("YouTube JSON 응답을 읽지 못했습니다.") from None
        raise CollectionError("YouTube 응답을 받지 못했습니다.")

def collect(api, c, rotation=0, now=None):
    now = now or datetime.now(timezone.utc)
    stamp = timestamp(now)
    found = {}
    warnings = []
    def add(vid, source):
        if isinstance(vid,str) and ID.fullmatch(vid):
            found.setdefault(vid,[])
            if source not in found[vid]:found[vid].append(source)
    pool = c["queries"]
    count = min(c["queries_per_run"],len(pool))
    selected = [pool[(rotation*count+i)%len(pool)] for i in range(count)] if pool else []
    # Up to 8 search calls per run: recent + all-time for each selected query.
    # Search preference is not a guarantee of English language / US origin.
    for query in selected:
        for recent in [True, False]:
            params = dict(part="snippet",type="video",q=query,order="viewCount",videoDuration="short",
                          maxResults=c["results_per_search"],relevanceLanguage=c["relevance_language"],
                          regionCode=c["region_code"],safeSearch="moderate")
            days = c["recent_days"] if recent else c["archive_days"]
            if days: params["publishedAfter"] = timestamp(now-timedelta(days=days))
            scope = f"최근 {days}일" if days else "전체 기간"
            result = api.get("search", **params)
            for item in result.get("items",[]):
                add(item.get("id",{}).get("videoId"),f"검색어: {query} · {scope}")
    if c["channel_ids"]:
        result = api.get("channels",part="contentDetails",id=",".join(c["channel_ids"]))
        for ch in result.get("items",[]):
            playlist = ch.get("contentDetails",{}).get("relatedPlaylists",{}).get("uploads")
            if not playlist:continue
            # One page per source channel in this lightweight version.
            uploads = api.get("playlistItems",part="contentDetails",playlistId=playlist,maxResults=50)
            for item in uploads.get("items",[]):add(item.get("contentDetails",{}).get("videoId"),"지정한 채널의 최근 업로드")
    for vid in c["video_ids"]:add(vid,"설정 파일에서 지정한 영상")
    if not found:
        return {"schema":1,"mode":"live","generatedAt":stamp,"warnings":["검색 결과가 없습니다. 설정의 검색어·기간을 확인하세요."],"videos":[],"searchQueries":selected}
    raw_videos=[]
    for batch in chunks(found):
        raw_videos.extend(api.get("videos",part="snippet,statistics,contentDetails,status",id=",".join(batch)).get("items",[]))
    eligible=[]
    for v in raw_videos:
        s=v.get("snippet",{});seconds=duration_seconds(v.get("contentDetails",{}).get("duration"))
        if v.get("status",{}).get("privacyStatus")!="public":continue
        if s.get("liveBroadcastContent","none")!="none":continue
        if seconds is None or not c["min_seconds"]<=seconds<=c["max_seconds"]:continue
        eligible.append((v,seconds))
    subscribers={}
    channel_ids=list(dict.fromkeys(v.get("snippet",{}).get("channelId") for v,_ in eligible if v.get("snippet",{}).get("channelId")))
    for batch in chunks(channel_ids):
        for ch in api.get("channels",part="statistics",id=",".join(batch)).get("items",[]):
            stats=ch.get("statistics",{})
            subscribers[ch["id"]]=None if stats.get("hiddenSubscriberCount") else number(stats.get("subscriberCount"))
    result=[]
    for v,seconds in eligible:
        s=v.get("snippet",{});st=v.get("statistics",{});cid=s.get("channelId","")
        thumbs=s.get("thumbnails",{});thumb=next((thumbs[k].get("url","") for k in ["high","medium","default"] if k in thumbs),"")
        if not re.match(r"^https://(?:i\.ytimg\.com|img\.youtube\.com)/",thumb):thumb=""
        vid=v.get("id","")
        if not ID.fullmatch(vid):continue
        result.append({"id":vid,"title":s.get("title",""),"channelTitle":s.get("channelTitle",""),"channelId":cid,
                       "views":number(st.get("viewCount")),"subscribers":subscribers.get(cid),
                       "publishedAt":s.get("publishedAt"),"fetchedAt":stamp,"durationSeconds":seconds,
                       "thumbnail":thumb,"source":" / ".join(found.get(vid,[])[:2])})
    result.sort(key=lambda x:x["views"] if x["views"] is not None else -1,reverse=True)
    result=result[:c["max_videos"]]
    if not result:warnings.append("길이·공개 조건에 맞는 후보가 없습니다. 검색어를 넓혀 주세요.")
    return {"schema":1,"mode":"live","generatedAt":stamp,"warnings":warnings,"videos":result,"searchQueries":selected}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=["demo","live"],default="demo")
    args=parser.parse_args()
    target=ROOT/"site/data/videos.json"
    if args.mode=="demo":
        data=json.loads(target.read_text(encoding="utf-8"))
        data["generatedAt"]=timestamp(datetime.now(timezone.utc))
        for v in data["videos"]:v["fetchedAt"]=data["generatedAt"]
        print("SAMPLE: 가상 샘플 데이터를 배포합니다. 실제 API는 호출하지 않았습니다.")
    else:
        c=load_config(ROOT/"config.json")
        try:rotation=max(0,int(os.environ.get("GITHUB_RUN_NUMBER","1"))-1)
        except ValueError:rotation=0
        api=YouTube(os.environ.get("YOUTUBE_API_KEY", "").strip())
        data=collect(api,c,rotation)
        print(f"LIVE: {len(data['videos'])}개 수집. API 요청 횟수: {json.dumps(api.calls)}")
    encoded=json.dumps(data,ensure_ascii=False,indent=2)
    secret=os.environ.get("YOUTUBE_API_KEY","")
    if secret and secret in encoded:raise CollectionError("보안 검사 실패: 공개 출력에 비밀키가 포함되어 배포를 중단했습니다.")
    tmp=target.with_suffix(".tmp")
    tmp.write_text(encoded+"\n",encoding="utf-8");tmp.replace(target)

if __name__=="__main__":
    try:main()
    except CollectionError as exc:
        print("ERROR: "+str(exc),file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("ERROR: 예기치 않은 수집 오류입니다. 출력은 교체하지 않았습니다. 설정 형식과 테스트 결과를 확인하세요.",file=sys.stderr)
        sys.exit(1)
