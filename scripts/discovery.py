"""Bounded discovery routes. Query labels describe OUR retrieval plan, not video content.
No ML scores, channel country inference, scraping, transcripts, or video downloads.
"""
from __future__ import annotations
import re
from collections import OrderedDict

VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
LANGUAGE = re.compile(r'^(?:[a-z]{2}|zh-Hans|zh-Hant)$')
LANES = ('familiar', 'expand', 'work', 'open')
LABELS = {'familiar':'참고 결에서 출발', 'expand':'다른 감동 이야기 탐색',
          'work':'참고 작품에서 출발', 'open':'새로운 소재 탐색',
          'source':'참고 채널에서 발견', 'direct':'직접 지정', 'legacy':'기존 검색'}


def validate_discovery(raw):
    if not isinstance(raw, dict) or raw.get('schema') != 1:
        raise ValueError('discovery.json의 schema는 1이어야 합니다.')
    if not isinstance(raw.get('enabled', True), bool):
        raise ValueError('discovery.json enabled는 true/false여야 합니다.')
    rows = raw.get('profiles')
    if not isinstance(rows, list) or not 4 <= len(rows) <= 128:
        raise ValueError('profiles는 4~128개 목록이어야 합니다.')
    profiles=[]
    for row in rows:
        if not isinstance(row, dict) or row.get('lane') not in LANES:
            raise ValueError('탐색 경로 lane이 잘못되었습니다.')
        q, lang, label = row.get('q'), row.get('language'), row.get('label')
        if not isinstance(q,str) or not 1<=len(q.strip())<=150:
            raise ValueError('q는 1~150자 문자열이어야 합니다.')
        if not isinstance(lang,str) or not LANGUAGE.fullmatch(lang):
            raise ValueError('language는 en, ja, zh-Hans 등의 코드여야 합니다.')
        if not isinstance(label,str) or not 1<=len(label.strip())<=80:
            raise ValueError('label은 1~80자 문자열이어야 합니다.')
        item={'lane':row['lane'],'q':q.strip(),'language':lang,'label':label.strip()}
        if item not in profiles:profiles.append(item)
    if set(row['lane'] for row in profiles)!=set(LANES):
        raise ValueError('familiar/expand/work/open 탐색 경로를 모두 남겨야 합니다.')
    refs=raw.get('reference_video_ids',[])
    if not isinstance(refs,list) or len(refs)>8 or not all(isinstance(v,str) and VIDEO_ID.fullmatch(v) for v in refs):
        raise ValueError('reference_video_ids는 영상 ID 8개 이하 목록이어야 합니다.')
    pages=raw.get('reference_pages_per_channel',1)
    if type(pages) is not int or not 1<=pages<=2:
        raise ValueError('reference_pages_per_channel은 1 또는 2여야 합니다.')
    limit=raw.get('reference_channel_limit',4)
    if type(limit) is not int or not 1<=limit<=4:
        raise ValueError('reference_channel_limit는 1~4여야 합니다.')
    return {'schema':1,'enabled':raw.get('enabled',True),'profiles':profiles,
            'reference_video_ids':list(dict.fromkeys(refs)),
            'reference_pages_per_channel':pages,'reference_channel_limit':limit}


def select_profiles(c, rotation=0):
    """Reserve broad exploration every run, under the pre-existing 4-query budget.
    Languages and stories rotate; no theme is mandatory for a returned video.
    Legacy config remains usable when discovery.json is absent/disabled.
    """
    plan=c.get('discovery')
    rotation=max(0,int(rotation))
    if plan and plan['enabled']:
        count=min(c['queries_per_run'],4)
        # Under a smaller budget still keep discovery; 4 is the shipped setting.
        lane_order=list(LANES) if count==4 else (['open'] if count==1 else ['familiar','open'] if count==2 else ['familiar','expand','open'])
        langs=[x for x in dict.fromkeys(p['language'] for p in plan['profiles']) if x!='en']
        anchor_slot=rotation%count
        selected=[];non_en_index=0
        for i,lane in enumerate(lane_order):
            options=[p for p in plan['profiles'] if p['lane']==lane]
            lang='en' if i==anchor_slot or not langs else langs[(rotation*(count-1)+non_en_index)%len(langs)]
            if i!=anchor_slot:non_en_index+=1
            preferred=[p for p in options if p['language']==lang] or options
            selected.append(preferred[(rotation//count)%len(preferred)])
        return selected
    pool=c['queries'];count=min(c['queries_per_run'],len(pool))
    anchor=next((e for e in pool if e['language']==c.get('anchor_language') and e['language']),None)
    if anchor:
        others=[e for e in pool if e is not anchor];take=count-1
        selected=[anchor]+([others[(rotation*take+i)%len(others)] for i in range(take)] if others else [])
    else:
        selected=[pool[(rotation*count+i)%len(pool)] for i in range(count)] if pool else []
    return [{**p,'lane':'legacy','label':'기존 검색'} for p in selected]


def shorts_hint(snippet):
    """A publisher's hashtag is a clue only, never a Shorts verification."""
    title=str(snippet.get('title',''))
    tags=snippet.get('tags',[])
    if re.search(r'#(?:shorts|youtubeshorts|ytshorts)\b',title,re.I):
        return True
    return isinstance(tags,list) and any(str(t).lower().strip().lstrip('#') in {'shorts','youtubeshorts','ytshorts'} for t in tags)


def diverse_snapshot(items, limit):
    """Keep candidate routes AND small-channel bands when a public snapshot is full.
    No extra filter/score: all items are kept when under the configured cap.
    """
    ordered=sorted(items,key=lambda v:v['views'] if v.get('views') is not None else -1,reverse=True)
    if len(ordered)<=limit:return ordered
    groups=OrderedDict()
    for v in ordered:
        n=v.get('subscribers')
        band='unknown' if n is None else 'under5k' if n<=5000 else 'under10k' if n<=10000 else 'larger'
        route=(v.get('discoveryRoutes') or ['legacy'])[0]
        groups.setdefault((route,band),[]).append(v)
    result=[];index=0
    while len(result)<limit:
        added=False
        for group in groups.values():
            if index<len(group):
                result.append(group[index]);added=True
                if len(result)==limit:break
        if not added:break
        index+=1
    return result
