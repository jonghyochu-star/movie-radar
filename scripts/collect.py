"""Build Movie Radar's public snapshot. Standard library only; no video download.
YOUTUBE_API_KEY must be provided by an environment variable / GitHub Secret.
No API key, private ratings, or notes are written into the public output.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
# Also works under importlib-based local/unit tests.
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
from screen_rules import infer_language, screen_evidence
from discovery import validate_discovery, select_profiles, shorts_hint, diverse_snapshot, LABELS, parse_collection_plan

CHANNEL = re.compile(r"^UC[A-Za-z0-9_-]{22}$")

class CollectionError(Exception):
    """Safe error message: never include request URL / credentials."""
    def __init__(self, message, reason=''):
        super().__init__(message)
        self.reason=reason


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
    if not isinstance(queries, list) or len(queries) > 64:
        raise CollectionError("queries는 최대 64개의 검색어 목록이어야 합니다.")
    normalized = []
    for entry in queries:
        if isinstance(entry, str):
            q, language = entry.strip(), c.get("relevance_language", "")
        elif isinstance(entry, dict):
            q, language = entry.get("q", ""), entry.get("language", "")
            if not isinstance(q, str):
                raise CollectionError("검색어 q에는 문자열을 넣으세요.")
            q = q.strip()
        else:
            raise CollectionError("검색어는 문자열 또는 q/language 객체여야 합니다.")
        if not q or len(q) > 150:
            raise CollectionError("검색어 q는 비어 있지 않은 150자 이하 문자열이어야 합니다.")
        if not isinstance(language, str) or (language and not (re.fullmatch(r"[a-z]{2}", language) or language in {"zh-Hans", "zh-Hant"})):
            raise CollectionError("language는 en, es, ja, zh-Hans 등의 언어 코드 또는 빈 문자열이어야 합니다.")
        item = {"q": q, "language": language}
        if item not in normalized:
            normalized.append(item)
    c["queries"] = normalized
    for field, pattern, maximum in [("channel_ids", CHANNEL, 5), ("video_ids", ID, 100)]:
        entries = c.get(field, [])
        if not isinstance(entries,list) or len(entries)>maximum or not all(isinstance(x,str) and pattern.fullmatch(x) for x in entries):
            raise CollectionError(f"{field} 형식이 잘못되었습니다. ID만 최대 {maximum}개 입력하세요.")
        c[field] = list(dict.fromkeys(entries))
    if not (c["queries"] or c["channel_ids"] or c["video_ids"]):
        raise CollectionError("검색어 또는 수집할 영상·채널 ID가 하나 이상 필요합니다.")
    c["relevance_language"] = c.get("relevance_language", "")
    c["region_code"] = c.get("region_code", "")
    region = c["region_code"]
    if not isinstance(region, str) or (region and not re.fullmatch(r"[A-Z]{2}", region)):
        raise CollectionError("region_code는 US 같은 국가 코드 또는 빈 문자열이어야 합니다.")
    c["anchor_language"] = c.get("anchor_language", "")
    if not isinstance(c["anchor_language"],str) or (c["anchor_language"] and not re.fullmatch(r"[a-z]{2}",c["anchor_language"])):
        raise CollectionError("anchor_language 형식이 잘못되었습니다.")
    for field,default in [("recent_order","viewCount"),("archive_order","relevance")]:
        c[field]=c.get(field,default)
        if c[field] not in {"viewCount","date","relevance"}:
            raise CollectionError(f"{field}는 viewCount/date/relevance 중 하나여야 합니다.")
    c["recent_topic_id"]=c.get("recent_topic_id", "")
    if c["recent_topic_id"] not in {"", "/m/02vxn", "/m/0f2f9"}:
        raise CollectionError("recent_topic_id 형식이 잘못되었습니다.")
    # Region is availability, NOT a film's production country. Never use it
    # or a channel's language/country to infer whether the original film is Korean.
    plan_path=Path(path).resolve().parent/'discovery.json'
    if plan_path.exists():
        try:
            c['discovery']=validate_discovery(json.loads(plan_path.read_text(encoding='utf-8')))
        except (OSError, ValueError) as exc:
            raise CollectionError('discovery.json을 확인하세요: '+str(exc)) from None
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
                raise CollectionError(messages.get(reason,f"YouTube 요청 실패 (HTTP {exc.code}). API 활성화·키 제한·할당량을 확인하세요."), reason=reason) from None
            except (URLError,TimeoutError) as exc:
                if attempt<2:time.sleep(2**attempt);continue
                raise CollectionError("YouTube 연결에 실패했습니다. 기존 배포는 유지됩니다.") from None
            except ValueError:
                raise CollectionError("YouTube JSON 응답을 읽지 못했습니다.") from None
        raise CollectionError("YouTube 응답을 받지 못했습니다.")

GENERIC_TITLE_TOKENS = {
    'movie','movies','film','films','scene','scenes','short','shorts','edit','edits','clip','clips','viral','fyp','video','videos','tv','series','episode','part','official','trailer','cinema',
    'pelicula','peliculas','escena','escenas','corto','cortos','serie','parte','cine',
    'filme','filmes','cena','cenas','curta','curtas','video','videos','serie','series',
    'extrait','scene','scenes','film','films','video','clip',
    'scena','scene','film','video','clip',
    'szene','szenen','film','video','clip'
}

def _plain_text(value):
    text=unicodedata.normalize('NFKD', str(value or '').casefold())
    return ''.join(ch for ch in text if not unicodedata.combining(ch))

def title_token_hashes(title):
    """Irreversible token hashes for high-confidence repeat suppression.
    This is not a semantic similarity model and intentionally fails open.
    """
    words=re.findall(r'[^\W_]+',_plain_text(title),flags=re.UNICODE)
    clean=[]
    for word in words:
        if len(word)<3 or word.isdigit() or word in GENERIC_TITLE_TOKENS:continue
        digest=hashlib.sha256(word.encode('utf-8')).hexdigest()[:12]
        if digest not in clean:clean.append(digest)
    return sorted(clean)[:32]

def near_duplicate(tokens, previous):
    current=set(tokens or [])
    if len(current)<3:return False
    for old in previous or []:
        other=set(old or [])
        if len(other)<3:continue
        inter=len(current & other)
        if current==other and inter>=3:return True
        union=len(current | other)
        if inter>=4 and union and inter/union>=0.82:return True
    return False

def load_cache_history(path, id_limit=5000, fp_limit=2500):
    if not path:return set(),[]
    try:
        raw=json.loads(Path(path).read_text(encoding='utf-8'))
        ids=[x for x in raw.get('ids',[]) if isinstance(x,str) and ID.fullmatch(x)]
        fps=[x for x in raw.get('fingerprints',[]) if isinstance(x,list) and all(isinstance(t,str) and re.fullmatch(r'[0-9a-f]{12}',t) for t in x)]
        return set(ids[-id_limit:]),fps[-fp_limit:]
    except (OSError,ValueError,TypeError):
        return set(),[]

def save_cache_history(path, ids, fingerprints, id_limit=5000, fp_limit=2500):
    if not path:return
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    payload={'schema':1,'ids':list(dict.fromkeys(ids))[-id_limit:],'fingerprints':list(fingerprints)[-fp_limit:]}
    tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8');tmp.replace(target)

def prior_pages_url(repository):
    if not isinstance(repository,str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",repository):
        return None
    owner,repo=repository.split('/',1)
    return f"https://{owner}.github.io/{repo}/data/videos.json"

def load_prior_history(repository, limit=5000, fp_limit=800):
    """Read prior public IDs and irreversible title fingerprints as a fallback.
    The Actions cache is the primary immediate retry memory; Pages is a second source.
    """
    url=prior_pages_url(repository)
    if not url:return set(), [], None
    try:
        req=Request(url+'?t='+str(int(time.time())),headers={'Accept':'application/json','User-Agent':'MovieRadar/1.4.1'})
        with urlopen(req,timeout=12) as response:data=json.load(response)
        ids=[];fps=[]
        if isinstance(data,dict):
            ids.extend(x for x in data.get('collectorHistoryIds',[]) if isinstance(x,str) and ID.fullmatch(x))
            for v in data.get('videos',[]):
                if not isinstance(v,dict):continue
                vid=v.get('id')
                if isinstance(vid,str) and ID.fullmatch(vid):ids.append(vid)
                fp=title_token_hashes(v.get('title',''))
                if fp:fps.append(fp)
            fps.extend(x for x in data.get('collectorRecentFingerprints',[]) if isinstance(x,list) and all(isinstance(t,str) and re.fullmatch(r'[0-9a-f]{12}',t) for t in x))
        return set(list(dict.fromkeys(ids))[-limit:]), fps[-fp_limit:], None
    except Exception:
        return set(), [], '이전 배포 목록을 읽지 못했습니다. Actions 캐시가 있으면 그 기록으로 중복을 제외합니다.'

def collect(api, c, rotation=0, now=None, collection_preset='english_focus', custom_weights='', retry_round=1, excluded_ids=None, excluded_fingerprints=None, trigger='manual'):
    now = now or datetime.now(timezone.utc)
    stamp = timestamp(now)
    found, routes = {}, {}
    warnings = []
    excluded_ids=set(excluded_ids or [])
    excluded_fingerprints=list(excluded_fingerprints or [])
    try: collection_plan=parse_collection_plan(collection_preset,custom_weights)
    except ValueError as exc: raise CollectionError('수집 언어 설정 오류: '+str(exc)) from None
    allowed_output={'zh-Hans':'zh','zh-Hant':'zh',**{x:x for x in ['en','ja','es','pt','fr','de','it']}}
    plan=c.get('discovery')
    plan=plan if plan and plan['enabled'] else None
    reference_ids=plan['reference_video_ids'] if plan else []
    def add(vid, source, route='legacy'):
        if isinstance(vid,str) and ID.fullmatch(vid) and vid not in reference_ids and vid not in excluded_ids:
            found.setdefault(vid,[]);routes.setdefault(vid,[])
            if source not in found[vid]:found[vid].append(source)
            if route not in routes[vid]:routes[vid].append(route)
    selected=select_profiles(c,rotation,collection_preset,custom_weights,retry_round)
    query_names=[entry['q'] for entry in selected]
    languages=list(dict.fromkeys(entry['language'] for entry in selected if entry['language']))
    # Keep source-channel results inside the languages actually selected for THIS run.
    # Previously english_focus allowed every language present in its weight table, so a
    # Spanish reference channel could dominate even when Spanish was not this run's slot.
    active_languages={allowed_output.get(x,x) for x in languages}
    # The existing maximum of 8 search requests is retained (retries are separate).
    # No request multiplies with the number of reference uploads or themes.
    for profile in selected:
        for recent in [True,False]:
            params=dict(part='snippet',type='video',q=profile['q'],
                        order=c['recent_order'] if recent else c['archive_order'],
                        videoDuration='short',maxResults=c['results_per_search'],safeSearch='moderate')
            # In the new plan the film topic is NOT a gate: it loses TV/indie scenes.
            if not plan and recent and c.get('recent_topic_id'):params['topicId']=c['recent_topic_id']
            if profile['language']:params['relevanceLanguage']=profile['language']
            if c['region_code']:params['regionCode']=c['region_code']
            days=c['recent_days'] if recent else c['archive_days']
            if days:params['publishedAfter']=timestamp(now-timedelta(days=days))
            scope=f'최근 {days}일' if days else '전체 기간'
            result=api.get('search',**params)
            for item in result.get('items',[]):
                add(item.get('id',{}).get('videoId'),
                    f"{LABELS[profile['lane']]} / {profile['label']} · 검색어: {profile['q']} · {scope}",profile['lane'])
    # Resolve user-provided VIDEO IDs at runtime; never guess channel IDs or map
    # the user's 9 files to these 4 URLs. Reference videos themselves are not new candidates.
    reference_channels=[];resolved_reference_ids=[]
    if reference_ids:
        seed_result=api.get('videos',part='snippet',id=','.join(reference_ids))
        for v in seed_result.get('items',[]):
            if v.get('id') not in reference_ids:continue
            cid=v.get('snippet',{}).get('channelId','')
            if isinstance(cid,str) and CHANNEL.fullmatch(cid):
                resolved_reference_ids.append(v['id'])
                if cid not in reference_channels:reference_channels.append(cid)
        missing=len(set(reference_ids)-set(resolved_reference_ids))
        if missing:warnings.append(f'참고 링크 {missing}개의 공개 채널 정보를 확인하지 못해 해당 출처는 건너뛰었습니다.')
        reference_channels=reference_channels[:plan['reference_channel_limit']]
    source_channels=list(dict.fromkeys(reference_channels+c['channel_ids']))
    source_stats=[]
    if source_channels:
        response=api.get('channels',part='snippet,contentDetails',id=','.join(source_channels))
        for ch in response.get('items',[]):
            cid=ch.get('id','')
            if cid not in source_channels:continue
            playlist=ch.get('contentDetails',{}).get('relatedPlaylists',{}).get('uploads')
            if not playlist:continue
            pages=plan['reference_pages_per_channel'] if plan and cid in reference_channels else 1
            token=None;seen_tokens=set();scanned=0
            for page in range(pages):
                params={'part':'contentDetails','playlistId':playlist,'maxResults':50}
                if token:params['pageToken']=token
                try:uploads=api.get('playlistItems',**params)
                except CollectionError as exc:
                    if exc.reason in {'playlistNotFound','playlistItemsNotAccessible'}:
                        warnings.append('참고 채널 1개의 업로드 목록에 접근하지 못해 건너뛰었습니다.');break
                    raise
                entries=uploads.get('items',[]);scanned+=len(entries)
                for item in entries:
                    add(item.get('contentDetails',{}).get('videoId'),
                        '참고 채널의 업로드 목록에서 발견 · 같은 감동결이라는 보장은 없음' if cid in reference_channels else '지정한 채널의 최근 업로드','source')
                token=uploads.get('nextPageToken')
                if not token or token in seen_tokens:break
                seen_tokens.add(token)
            source_stats.append({'channelId':cid,'channelTitle':ch.get('snippet',{}).get('title',''),
                                 'scannedUploads':scanned,'referenceSource':cid in reference_channels})
    for vid in c['video_ids']:add(vid,'설정 파일에서 지정한 영상','direct')
    base={'schema':1,'mode':'live','generatedAt':stamp,'collectorVersion':'1.4.1',
          'reviewPolicy':'manual-original-country-v1','warnings':warnings,
          'searchQueries':query_names,'searchLanguages':languages,
          'collectionPlan':{'preset':collection_plan['preset'],'weights':collection_plan['weights'],
                            'retryRound':int(retry_round),'trigger':trigger,
                            'excludedPreviousIds':len(excluded_ids),'activeLanguages':languages},
          'discoveryPlan':[{'lane':p['lane'],'label':p['label'],'language':p['language'],'query':p['q']} for p in selected],
          'referenceSummary':{'requested':len(reference_ids),'resolved':len(resolved_reference_ids),
                              'channels':source_stats},'shortsPolicy':'publisher-hint-or-user-confirmation-only'}
    if not found:
        base['warnings'].append('검색 결과가 없습니다. 참고 출처와 검색어·기간을 확인하세요.')
        return {**base,'collectorHistoryIds':list(excluded_ids)[-5000:],'collectorRecentFingerprints':[],'videos':[]}
    raw_videos=[]
    for batch in chunks(found):
        raw_videos.extend(api.get('videos',part='snippet,statistics,contentDetails,status,topicDetails',id=','.join(batch)).get('items',[]))
    eligible=[];seen=set()
    for v in raw_videos:
        vid=v.get('id','')
        if vid in seen or vid not in found:continue
        seen.add(vid)
        s=v.get('snippet',{});seconds=duration_seconds(v.get('contentDetails',{}).get('duration'))
        if v.get('status',{}).get('privacyStatus')!='public':continue
        if s.get('liveBroadcastContent','none')!='none':continue
        if seconds is None or not c['min_seconds']<=seconds<=c['max_seconds']:continue
        eligible.append((v,seconds))
    subscribers={}
    channel_ids=list(dict.fromkeys(v.get('snippet',{}).get('channelId') for v,_ in eligible if v.get('snippet',{}).get('channelId')))
    for batch in chunks(channel_ids):
        for ch in api.get('channels',part='statistics',id=','.join(batch)).get('items',[]):
            stats=ch.get('statistics',{})
            subscribers[ch['id']]=None if stats.get('hiddenSubscriberCount') else number(stats.get('subscriberCount'))
    result=[]; accepted_fingerprints=[]; duplicate_suppressed=0
    for v,seconds in eligible:
        s=v.get('snippet',{});st=v.get('statistics',{});cid=s.get('channelId','')
        thumbs=s.get('thumbnails',{});thumb=next((thumbs[k].get('url','') for k in ['high','medium','default'] if k in thumbs),'')
        if not re.match(r'^https://(?:i\.ytimg\.com|img\.youtube\.com)/',thumb):thumb=''
        vid=v.get('id','')
        if not ID.fullmatch(vid):continue
        lang=infer_language(s);evidence=screen_evidence(v)
        # Collection language controls actual candidates, not only the browser display.
        # Apply the languages selected in this run to search AND reference-channel results.
        if plan:
            if lang['code']=='unknown':continue
            if active_languages and lang['code'] not in active_languages:continue
        fp=title_token_hashes(s.get('title',''))
        if near_duplicate(fp,[*excluded_fingerprints,*accepted_fingerprints]):
            duplicate_suppressed+=1;continue
        if fp:accepted_fingerprints.append(fp)
        result.append({'language':lang['code'],'languageBasis':lang['basis'],'audioLanguage':lang['audio'],
                       'declaredLanguage':lang['declared'],'languageSource':lang['source'],
                       'titleLanguage':lang['titleCode'],'titleLanguageBasis':lang['titleBasis'],
                       'screenKind':evidence['kind'],'screenReason':evidence['reason'],
                       'metadataVersion':'1.4.1','id':vid,'title':s.get('title',''),'channelTitle':s.get('channelTitle',''),'channelId':cid,
                       'views':number(st.get('viewCount')),'subscribers':subscribers.get(cid),
                       'publishedAt':s.get('publishedAt'),'fetchedAt':stamp,'durationSeconds':seconds,
                       'thumbnail':thumb,'originalStatus':'unverified','source':' / '.join(found.get(vid,[])[:2]),
                       'discoveryRoutes':routes.get(vid,[]),'shortsHint':shorts_hint(s)})
    eligible_count=len(result)
    result=diverse_snapshot(result,c['max_videos'])
    if not result:warnings.append('길이·공개 조건에 맞는 후보가 없습니다.')
    base['warnings']=warnings
    base['collectionSummary']={'uniqueFound':len(found),'eligibleBeforeCap':eligible_count,'kept':len(result),
        'duplicateCandidatesSuppressed':duplicate_suppressed,'snapshotLimit':c['max_videos'],
        'routeCounts':{lane:sum(lane in v['discoveryRoutes'] for v in result) for lane in LABELS},
        'note':'경로별 수는 중복 포함. 중복 억제는 정확한 영상 ID와 제목이 거의 같은 재업로드 후보에만 보수적으로 적용합니다.'}
    history=list(dict.fromkeys([*excluded_ids,*[v['id'] for v in result]]))[-5000:]
    return {**base,'collectorHistoryIds':history,'collectorRecentFingerprints':accepted_fingerprints[-800:],'videos':result}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=["demo","live"],default="demo")
    parser.add_argument("--collect-preset",choices=["english_focus","english_only","balanced","custom"],default=os.environ.get("COLLECT_PRESET","english_focus"))
    parser.add_argument("--custom-weights",default=os.environ.get("CUSTOM_LANGUAGE_WEIGHTS",""))
    parser.add_argument("--retry-round",type=int,choices=[1,2,3],default=int(os.environ.get("RETRY_ROUND","1")))
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
        page_ids,page_fps,prior_warning=load_prior_history(os.environ.get('GITHUB_REPOSITORY',''))
        cache_path=os.environ.get('COLLECT_HISTORY_PATH','').strip()
        cache_ids,cache_fps=load_cache_history(cache_path)
        prior=set(page_ids)|set(cache_ids)
        fingerprints=[*cache_fps,*page_fps]
        trigger=os.environ.get('COLLECTION_TRIGGER','manual')
        data=collect(api,c,rotation,collection_preset=args.collect_preset,custom_weights=args.custom_weights,
                     retry_round=args.retry_round,excluded_ids=prior,excluded_fingerprints=fingerprints,trigger=trigger)
        if prior_warning:data.setdefault('warnings',[]).append(prior_warning)
        merged_fps=[*fingerprints,*data.get('collectorRecentFingerprints',[])]
        save_cache_history(cache_path,data.get('collectorHistoryIds',[]),merged_fps)
        print(f"LIVE: {len(data['videos'])}개 수집. API 요청 횟수: {json.dumps(api.calls)}")
        print("수집 경로: " + ", ".join(p["lane"] for p in data.get("discoveryPlan",[])))
        print("참고 출처 채널: " + str(len(data.get("referenceSummary",{}).get("channels",[]))))
        print("검색 언어: " + ", ".join(data.get("searchLanguages", [])))
        print("수집 언어 계획: " + json.dumps(data.get("collectionPlan",{}),ensure_ascii=False))
        print("중복 억제: " + str(data.get('collectionSummary',{}).get('duplicateCandidatesSuppressed',0)) + "개 / 캐시·이전 배포 ID 제외 " + str(data.get('collectionPlan',{}).get('excludedPreviousIds',0)) + "개")
        evidence_counts={kind:sum(v.get("screenKind")==kind for v in data['videos']) for kind in ['film','series','unknown','non_screen']}
        small=sum(isinstance(v.get('subscribers'),int) and v['subscribers']<=10000 for v in data['videos'])
        print("메타데이터 단서 분포: " + json.dumps(evidence_counts) + f" / 공개 구독 1만 이하: {small}개")
        print("원작 제작국은 자동 판정하지 않았습니다. 미확인 영상은 원작 확인 필요 탭에서 검토하세요.")
    encoded=json.dumps(data,ensure_ascii=False,indent=2)
    secret=os.environ.get("YOUTUBE_API_KEY","")
    if secret and secret in encoded:raise CollectionError("보안 검사 실패: 공개 출력에 비밀키가 포함되어 배포를 중단했습니다.")
    target.parent.mkdir(parents=True,exist_ok=True)
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
