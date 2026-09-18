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

SEARCH_LANGS=('en','ja','es','pt','fr','de','it','zh-Hans')
PRESET_WEIGHTS={
    'english_only': {'en':100},
    'english_focus': {'en':70,'ja':5,'es':5,'pt':5,'fr':5,'de':4,'it':3,'zh-Hans':3},
    'balanced': {'en':13,'ja':13,'es':13,'pt':13,'fr':12,'de':12,'it':12,'zh-Hans':12},
}

def parse_collection_plan(preset='english_focus', custom_weights=''):
    preset = preset if preset in {*PRESET_WEIGHTS, 'custom'} else 'english_focus'
    if preset!='custom':
        weights=dict(PRESET_WEIGHTS[preset])
    else:
        weights={}
        text=str(custom_weights or '').strip()
        for piece in text.split(','):
            if not piece.strip(): continue
            if ':' not in piece: raise ValueError('직접 비중은 en:70,ja:10 형식이어야 합니다.')
            lang,raw=(x.strip() for x in piece.split(':',1))
            if lang not in SEARCH_LANGS: raise ValueError('지원하지 않는 수집 언어 코드입니다: '+lang)
            try:value=int(raw)
            except ValueError: raise ValueError('언어 비중은 정수여야 합니다.') from None
            if value<0 or value>100: raise ValueError('언어 비중은 0~100이어야 합니다.')
            if value: weights[lang]=value
        if not weights: raise ValueError('직접 수집 언어를 하나 이상 지정하세요.')
    total=sum(weights.values())
    if total<=0: raise ValueError('수집 언어 비중 합계는 0보다 커야 합니다.')
    normalized={k:v/total for k,v in weights.items() if v>0}
    return {'preset':preset,'weights':weights,'normalized':normalized,'allowed':tuple(normalized)}

def language_slots(plan,count,rotation=0):
    """Deterministic language allocation for the tiny per-run query budget."""
    count=max(0,int(count)); rotation=max(0,int(rotation))
    if not count:return []
    preset=plan.get('preset')
    if preset=='english_only': return ['en']*count
    if preset=='english_focus':
        # 4 queries -> 3 English + 1 rotating non-English language.
        english=min(count, max(1, round(count*0.70)))
        others=[x for x in plan['allowed'] if x!='en']
        slots=['en']*english
        while len(slots)<count:
            slots.append(others[(rotation+len(slots)-english)%len(others)] if others else 'en')
        return slots
    if preset=='balanced':
        order=list(plan['allowed']); shift=rotation%len(order);order=order[shift:]+order[:shift]
        return [order[i%len(order)] for i in range(count)]
    # Custom: largest-remainder allocation, ties rotate between runs.
    items=list(plan['normalized'].items())
    base={lang:int(weight*count) for lang,weight in items}
    remain=count-sum(base.values())
    residual={lang:(weight*count)-base[lang] for lang,weight in items}
    for _ in range(remain):
        best=max(residual.values())
        tied=[lang for lang,_ in items if abs(residual[lang]-best)<1e-12]
        lang=tied[rotation%len(tied)];base[lang]+=1;residual[lang]=-1;rotation+=1
    slots=[]; pools=dict(base); order=[lang for lang,_ in items]
    while len(slots)<count:
        candidates=[l for l in order if pools.get(l,0)>0]
        if not candidates:break
        lang=max(candidates,key=lambda l:(pools[l],plan['normalized'].get(l,0)))
        slots.append(lang);pools[lang]-=1
        idx=order.index(lang);order=order[idx+1:]+order[:idx+1]
    return slots


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


def select_profiles(c, rotation=0, preset='english_focus', custom_weights='', retry_round=1):
    """Select a bounded set of routes and languages for one collection run.
    retry_round changes the discovery emphasis, but never relaxes hard UI criteria.
    """
    plan=c.get('discovery')
    rotation=max(0,int(rotation)); retry_round=min(3,max(1,int(retry_round)))
    if plan and plan['enabled']:
        count=min(c['queries_per_run'],4)
        lane_sets={
            1:['familiar','expand','work','open'],
            2:['expand','open','familiar','open'],
            3:['open','expand','open','work'],
        }
        full=lane_sets[retry_round]
        if count==1: lane_order=['open']
        elif count==2: lane_order=[full[0],'open']
        elif count==3: lane_order=[full[0],full[1],'open']
        else: lane_order=full
        collection=parse_collection_plan(preset,custom_weights)
        langs=language_slots(collection,count,rotation+retry_round-1)
        selected=[]
        for i,lane in enumerate(lane_order):
            options=[p for p in plan['profiles'] if p['lane']==lane]
            lang=langs[i] if i<len(langs) else 'en'
            preferred=[p for p in options if p['language']==lang]
            if not preferred:
                # This can only happen with a malformed future discovery file; keep route exploration.
                preferred=options
            index=(rotation + (retry_round-1)*3 + i)//max(1,count)
            selected.append(preferred[index%len(preferred)])
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
