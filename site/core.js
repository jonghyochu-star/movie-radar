/* Movie Radar: pure state helpers, usable in the browser and Node tests. */
(function(root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  else root.MovieCore = value;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';
  const MAX_AGE = 29 * 86400000;
  const validId = id => typeof id === 'string' && /^(?:[A-Za-z0-9_-]{11}|demo-[1-9][0-9]*)$/.test(id);
  const blank = () => ({schema:1, records:Object.create(null), batchFeedback:[]});
  function record(id) {
    return {id,rating:null,dislikeReason:null,stage:null,origin:'unknown',media:'unknown',format:'unknown',memo:'',label:'',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),cache:null};
  }
  function normalize(raw, now=Date.now()) {
    if (!raw || raw.schema !== 1 || typeof raw.records !== 'object' || !raw.records || Array.isArray(raw.records)) throw Error('Movie Radar 백업 형식이 아닙니다.');
    const out=blank();
    if(Object.keys(raw.records).length>20000) throw Error('한 번에 20,000개를 초과해 복원할 수 없습니다.');
    for(const [id,r] of Object.entries(raw.records)) {
      if(!validId(id) || !r || typeof r !== 'object') continue;
      const x=record(id);
      x.rating=['like','dislike'].includes(r.rating)?r.rating:null;
      x.dislikeReason=['not_my_tone','overused','weak_story','other'].includes(r.dislikeReason)?r.dislikeReason:null;
      x.stage=['candidate','done'].includes(r.stage)?r.stage:null;
      x.origin=originOf(r);
      x.media=mediaOf(r);
      x.format=formatOf(r);
      x.memo=String(r.memo||'').slice(0,5000);x.label=String(r.label||'').slice(0,150);
      for(const k of ['createdAt','updatedAt']) if(typeof r[k]==='string' && Number.isFinite(Date.parse(r[k]))) x[k]=r[k];
      const t=Date.parse(r.cache?.fetchedAt);
      if(r.cache?.id===id && Number.isFinite(t) && now-t<MAX_AGE && t<=now+60000) x.cache=r.cache;
      out.records[id]=x;
    }
    if(Array.isArray(raw.batchFeedback)){
      out.batchFeedback=raw.batchFeedback.filter(x=>x&&typeof x==='object'&&typeof x.generatedAt==='string'&&Number.isFinite(Date.parse(x.generatedAt))&&['no_harvest','useful'].includes(x.outcome)).slice(-200).map(x=>({generatedAt:x.generatedAt,outcome:x.outcome,at:typeof x.at==='string'&&Number.isFinite(Date.parse(x.at))?x.at:new Date().toISOString(),retryRound:Number.isInteger(x.retryRound)?Math.min(3,Math.max(1,x.retryRound)):1}));
    }
    return out;
  }
  function apply(state, video, action, now=new Date().toISOString()) {
    if(!validId(video.id)) throw Error('영상 ID 형식이 잘못되었습니다.');
    const next=JSON.parse(JSON.stringify(state)); next.records=Object.assign(Object.create(null),next.records); const r=next.records[video.id]||record(video.id);
    switch(action) {
      case 'like': r.rating='like'; r.dislikeReason=null; break;
      case 'dislike': r.rating='dislike'; break;
      case 'dislike_not_tone': r.rating='dislike'; r.dislikeReason='not_my_tone'; break;
      case 'dislike_overused': r.rating='dislike'; r.dislikeReason='overused'; break;
      case 'dislike_weak_story': r.rating='dislike'; r.dislikeReason='weak_story'; break;
      case 'dislike_other': r.rating='dislike'; r.dislikeReason='other'; break;
      case 'candidate':
        if(formatOf(r)==='not_short') throw Error('일반 영상으로 표시되어 있습니다. 쇼츠 여부를 먼저 확인해 주세요.');
        if (mediaOf(r)==='not_screen' || (!isSample(video) && originOf(r) !== 'non_korean')) throw Error('원작이 한국 외 작품인지 먼저 확인해 주세요.');
        r.stage='candidate'; break;
      case 'uncandidate': r.stage=null; break;
      case 'done': r.stage='done'; break;
      case 'reopen':
        if(formatOf(r)==='not_short') throw Error('일반 영상으로 표시되어 있습니다. 쇼츠 여부를 먼저 확인해 주세요.');
        if (mediaOf(r)==='not_screen' || (!isSample(video) && originOf(r) !== 'non_korean')) throw Error('원작이 한국 외 작품인지 먼저 확인해 주세요.');
        r.stage='candidate'; break;
      case 'unrate': r.rating=null; r.dislikeReason=null; break;
      case 'origin_foreign': r.origin='non_korean'; break;
      case 'origin_korean': r.origin='korean'; break;
      case 'origin_reset': r.origin='unknown'; break;
      case 'format_yes': r.format='shorts'; break;
      case 'format_no': r.format='not_short'; break;
      case 'format_reset': r.format='unknown'; break;
      case 'media_no': r.media='not_screen'; break;
      case 'media_yes': r.media='screen'; break;
      case 'media_reset': r.media='unknown'; break;
      default: throw Error('지원하지 않는 동작입니다.');
    }
    if(video.fetchedAt)r.cache=video;
    r.updatedAt=now;next.records[video.id]=r;return next;
  }
  // Origin is an explicit local user decision, never inferred from video language.
  function originOf(r) {
    return r && ['non_korean','korean'].includes(r.origin) ? r.origin : 'unknown';
  }
  function isSample(v) { return typeof v?.id==='string' && /^demo-/.test(v.id); }
  function ready(v,r) { return formatOf(r)!=='not_short' && mediaOf(r)!=='not_screen' && (isSample(v) || originOf(r)==='non_korean'); }
  function needsReview(v,r={}) { return formatOf(r)!=='not_short' && mediaOf(r)!=='not_screen' && !isSample(v) && originOf(r)==='unknown' && !r.rating && !r.stage; }
  function ratio(v) {
    const sub=v.subscribers, views=v.views;
    return typeof sub==='number' && sub>0 && typeof views==='number'?views/sub:null;
  }
  function exportData(state) {
    const result=blank();
    const normalized=normalize(state);
    for(const [id,r] of Object.entries(normalized.records)) {
      // Preserve user-created data, not long-lived API metadata snapshots.
      const {cache,...userData}=r;result.records[id]=userData;
    }
    result.batchFeedback=normalized.batchFeedback.slice(-200);
    return result;
  }
  function merge(a,b) {
    const left=normalize(a),right=normalize(b);
    for(const [id,r] of Object.entries(right.records)) {
      if(!left.records[id] || Date.parse(r.updatedAt)>Date.parse(left.records[id].updatedAt))left.records[id]=r;
    }
    const feedback=[...(left.batchFeedback||[]),...(right.batchFeedback||[])];
    const seen=new Set();left.batchFeedback=[];
    for(const x of feedback.sort((a,b)=>Date.parse(a.at||0)-Date.parse(b.at||0))){const k=x.generatedAt+'|'+x.outcome;if(seen.has(k))continue;seen.add(k);left.batchFeedback.push(x);}
    left.batchFeedback=left.batchFeedback.slice(-200);
    return left;
  }
  function parseLink(text) {
    let u;try{u=new URL(text.trim());}catch{throw Error('YouTube 영상 주소를 붙여 넣어 주세요.');}
    if(u.protocol!=='https:' || !['youtube.com','www.youtube.com','m.youtube.com','youtu.be'].includes(u.hostname)) throw Error('https:// 형식의 YouTube 영상 주소만 지원합니다.');
    let id = u.hostname==='youtu.be'?u.pathname.split('/')[1]:(u.pathname==='/watch'?u.searchParams.get('v'):(/^\/(shorts|embed|live)\//.test(u.pathname)?u.pathname.split('/')[2]:null));
    if(!id || !/^[\w-]{11}$/.test(id))throw Error('영상 ID를 찾지 못했습니다. 채널이 아닌 영상 주소를 입력해 주세요.');
    return id;
  }

  function mediaOf(r) { return r && ['screen','not_screen'].includes(r.media)?r.media:'unknown'; }
  const LANGUAGE_LABELS=Object.freeze({en:'영어',ja:'일본어',es:'스페인어',pt:'포르투갈어',fr:'프랑스어',de:'독일어',it:'이탈리아어',zh:'중국어',vi:'베트남어',th:'태국어',id:'인도네시아어',ru:'러시아어',tr:'튀르키예어',hi:'힌디어',ar:'아랍어',fa:'페르시아어',ur:'우르두어',bn:'벵골어',ta:'타밀어',te:'텔루구어',ko:'한국어','ar-script':'아랍 문자권(추정)','indic-script':'인도계 문자권(추정)',cyrillic:'키릴 문자권(추정)',other:'기타 언어',unknown:'언어 미확인'});
  // v1.2.1: use exactly the same effective language for labels, filtering and balancing.
  // Legacy snapshots/caches must not leak a defaultLanguage-only English label.
  function languageInfo(v={}) {
    const recognized=x=>typeof x==='string'&&x!=='unknown'&&Object.hasOwn(LANGUAGE_LABELS,x);
    const label=x=>LANGUAGE_LABELS[x]||LANGUAGE_LABELS.unknown;
    const audio=recognized(v.audioLanguage)?v.audioLanguage:'unknown';
    let code='unknown',source='unknown',basis='음성 설정 또는 제목의 언어 단서가 부족합니다.';
    if(audio!=='unknown'){
      code=audio;source='audio';basis='업로더의 기본 음성 언어 설정 · 실제 음성 자동 검증 아님';
    }else if(v.languageSource==='title'&&recognized(v.language)){
      code=v.language;source='title';basis=v.languageBasis||'제목 단서 · 추정, 음성 미확인';

    }else{
      basis=v.languageSource==='unknown' ? (v.languageBasis||basis) : '음성 설정 없음 · 제목·설명 언어 설정만으로 통과시키지 않음';
    }
    let declared=recognized(v.declaredLanguage)?v.declaredLanguage:'unknown';
    if(declared==='unknown'&&!v.languageSource&&v.languageBasis==='업로더의 제목·설명 언어 설정'&&recognized(v.language))declared=v.language;
    const badge=source==='audio'?`${label(code)} · 음성 설정`:source==='title'?`${label(code)} · 제목 추정`:label('unknown');
    return {code,source,basis,badge,audio,declared};
  }
  const preferredLanguages=()=>['en','ja','es','pt','fr','de','it','zh'];
  const defaultFilters=()=>({schema:1,maxSubscribers:0,minSeconds:0,maxSeconds:180,minViews:100000,content:'screen_gate',languages:preferredLanguages(),includeUnknownLanguage:true,balance:true,route:'all',mixDiscovery:true,shorts:'any',tasteAssist:true});
  const broadFilters=()=>({schema:1,maxSubscribers:0,minSeconds:0,maxSeconds:180,minViews:0,content:'all',languages:Object.keys(LANGUAGE_LABELS).filter(x=>x!=='unknown'),includeUnknownLanguage:true,balance:true,route:'all',mixDiscovery:true,shorts:'any',tasteAssist:true});
  function normalizeFilters(raw={}) {
    const f=defaultFilters(), numberKeys={maxSubscribers:[0,1000000000],minSeconds:[0,180],maxSeconds:[0,180],minViews:[0,100000000000]};
    for(const [k,[lo,hi]] of Object.entries(numberKeys)) if(Number.isInteger(raw[k])&&raw[k]>=lo&&raw[k]<=hi)f[k]=raw[k];
    // Empty/invalid UI inputs never make NaN comparisons silently accept data.
    if(f.minSeconds>f.maxSeconds){f.minSeconds=0;f.maxSeconds=180;}
    if(['screen_gate','review','screen','film','all'].includes(raw.content))f.content=raw.content==='review'?'screen_gate':raw.content;
    if(Array.isArray(raw.languages))f.languages=[...new Set(raw.languages.filter(x=>typeof x==='string'&&x!=='unknown'&&Object.hasOwn(LANGUAGE_LABELS,x)))];
    if(raw.route==='all'||Object.hasOwn(ROUTE_LABELS,raw.route))f.route=raw.route;
    if(['any','hinted','confirmed'].includes(raw.shorts))f.shorts=raw.shorts;
    for(const k of ['balance','includeUnknownLanguage','mixDiscovery','tasteAssist'])if(typeof raw[k]==='boolean')f[k]=raw[k];
    return f;
  }
  function screenKind(v,r={}) {
    if(mediaOf(r)==='not_screen')return 'non_screen';
    if(['film','series'].includes(v.screenKind))return v.screenKind;
    if(mediaOf(r)==='screen'||originOf(r)==='non_korean'||isSample(v))return 'user_screen';
    return ['film','series','non_screen'].includes(v.screenKind)?v.screenKind:'unknown';
  }
  function screenGateInfo(v={},r={}) {
    if(mediaOf(r)==='screen')return {ok:true,label:'내가 영화·드라마로 확인',topics:[]};
    const gates=Array.isArray(v.screenGate)?[...new Set(v.screenGate.filter(x=>['movie','tv','metadata','direct'].includes(x)))]:[];
    if(gates.includes('movie')&&gates.includes('tv'))return {ok:true,label:'영화·TV 주제 검색',topics:['movie','tv']};
    if(gates.includes('movie'))return {ok:true,label:'영화 주제 검색',topics:['movie']};
    if(gates.includes('tv'))return {ok:true,label:'TV·드라마 주제 검색',topics:['tv']};
    if(gates.includes('metadata')||['film','series'].includes(screenKind(v,r)))return {ok:true,label:'영화·드라마 메타데이터 단서',topics:[]};
    if(gates.includes('direct'))return {ok:true,label:'직접 지정 후보',topics:[]};
    return {ok:false,label:'영화·드라마 게이트 미확인',topics:[]};
  }
  function filterReasons(v,r,f) {
    if(isSample(v))return []; // fictitious demo items are explicitly exempt from source checks
    const reasons=[],kind=screenKind(v,r),format=shortsInfo(v,r).status;
    if(f.route&&f.route!=='all'&&!routesOf(v).includes(f.route))reasons.push('route');
    if(format==='not_short'||(f.shorts==='hinted'&&!['hint','confirmed'].includes(format))||(f.shorts==='confirmed'&&format!=='confirmed'))reasons.push('format');
    if(f.content==='screen_gate'&&(kind==='non_screen'||!screenGateInfo(v,r).ok))reasons.push('content');
    if(f.content==='screen'&&!['film','series','user_screen'].includes(kind))reasons.push('content');
    if(f.content==='film'&&kind!=='film')reasons.push('content');
    if(f.maxSubscribers>0&&!(Number.isFinite(v.subscribers)&&v.subscribers>=0&&v.subscribers<=f.maxSubscribers))reasons.push('subscribers');
    const lang=languageInfo(v).code;
    if(lang==='unknown'?!f.includeUnknownLanguage:!f.languages.includes(lang))reasons.push('language');
    if(!(Number.isFinite(v.durationSeconds)&&v.durationSeconds>=f.minSeconds&&v.durationSeconds<=f.maxSeconds))reasons.push('duration');
    if(f.minViews>0&&!(Number.isFinite(v.views)&&v.views>=f.minViews))reasons.push('views');
    return reasons;
  }
  function matchesFilters(v,r,f) { return filterReasons(v,r,f).length===0; }
  function filterCounts(items,records,f) {
    const result={total:items.length};let remaining=items;
    for(const reason of ['content','subscribers','language','duration','views','route','format']){
      remaining=remaining.filter(v=>!filterReasons(v,records[v.id]||{},f).includes(reason));result[reason]=remaining.length;
    }
    return result;
  }
  // Interleave available groups only. This is not a global descending-view sort.
  // Every input video is returned exactly once; scarce languages are never fabricated.
  function roundRobin(groups) {
    const out=[];let i=0,added=true;
    while(added){added=false;for(const group of groups)if(i<group.length){out.push(group[i]);added=true;}i++;}
    return out;
  }
  function balanceVideos(items, languageOrder=preferredLanguages()) {
    const languages=new Map();
    for(const v of items){const lang=languageInfo(v).code;if(!languages.has(lang))languages.set(lang,[]);languages.get(lang).push(v);}
    const order=[...languageOrder.filter(x=>languages.has(x)),...[...languages.keys()].filter(x=>!languageOrder.includes(x))];
    const queues=order.map(lang=>{const channels=new Map();for(const v of languages.get(lang)){const id=v.channelId||v.id;if(!channels.has(id))channels.set(id,[]);channels.get(id).push(v);}return roundRobin([...channels.values()]);});
    return roundRobin(queues);
  }

  const ROUTE_LABELS=Object.freeze({familiar:'참고 결에서 출발',expand:'다른 감동 이야기 탐색',work:'참고 작품에서 출발',open:'새로운 소재 탐색',source:'참고 채널에서 발견',direct:'직접 지정',legacy:'기존 검색'});
  function formatOf(r={}) {return ['shorts','not_short'].includes(r?.format)?r.format:'unknown';}
  function shortsInfo(v={},r={}) {
    const f=formatOf(r);
    if(f==='shorts')return {status:'confirmed',label:'쇼츠 · 내가 확인',reason:'사용자가 원본에서 확인한 기록입니다. 자동 판정이 아닙니다.'};
    if(f==='not_short')return {status:'not_short',label:'일반 영상 · 내가 제외',reason:'취향 평가와 별도로 제외했습니다. 확인 취소로 복구할 수 있습니다.'};
    if(v.shortsHint===true)return {status:'hint',label:'쇼츠 표기 단서 · 미확인',reason:'제목/태그의 Shorts 표기만 있습니다. 길이·태그로 실제 Shorts 여부를 확정하지 않습니다.'};
    return {status:'unknown',label:'쇼츠 여부 미확인',reason:'3분 이하라는 이유만으로 Shorts로 확정하지 않았습니다.'};
  }
  function routesOf(v={}) {const a=Array.isArray(v.discoveryRoutes)?v.discoveryRoutes.filter(x=>typeof x==='string'&&Object.hasOwn(ROUTE_LABELS,x)):[];return a.length?[...new Set(a)]:['legacy'];}

  const TASTE_ROUTES=new Set(['familiar','expand','work','open']);
  function themesOf(v={}) {
    const direct=Array.isArray(v.discoveryLabels)?v.discoveryLabels.filter(x=>typeof x==='string'&&x.trim()).map(x=>x.trim().slice(0,80)):[];
    if(direct.length)return [...new Set(direct)];
    const text=String(v.source||'');
    const out=[];
    const re=/(?:참고 결에서 출발|다른 감동 이야기 탐색|참고 작품에서 출발|새로운 소재 탐색)\s*\/\s*([^·\/\n]{1,80})/g;
    for(const m of text.matchAll(re)){const x=String(m[1]||'').trim();if(x&&!out.includes(x))out.push(x);}
    return out;
  }
  function _bump(map,key){if(typeof key==='string'&&key)map[key]=(map[key]||0)+1;}
  function _signal(pos={},neg={},key){const a=Number(pos[key]||0),b=Number(neg[key]||0);return a>b?1:b>a?-1:0;}
  function buildTasteProfile(videos=[],records={}) {
    const byId=new Map((Array.isArray(videos)?videos:[]).filter(v=>v&&typeof v.id==='string').map(v=>[v.id,v]));
    const liked={channels:Object.create(null),routes:Object.create(null),themes:Object.create(null)};
    const disliked={channels:Object.create(null),routes:Object.create(null),themes:Object.create(null)};
    let likedCount=0,dislikedCount=0,usableLikes=0,usableDislikes=0,excludedFromTaste=0,untypedDislikes=0;
    const dislikeReasonCounts={not_my_tone:0,overused:0,weak_story:0,other:0};
    for(const [id,r] of Object.entries(records||{})){
      if(!r||!['like','dislike'].includes(r.rating))continue;
      // Country/format/content exclusions are not preference signals.
      if(originOf(r)==='korean'||formatOf(r)==='not_short'||mediaOf(r)==='not_screen'){excludedFromTaste++;continue;}
      const isLike=r.rating==='like'; if(isLike)likedCount++; else dislikedCount++;
      // Only an explicit "내 결 아님" is a negative taste signal.
      // Legacy dislikes and "많이 봄/전개 약함/기타" remain useful records but do not teach the model that the emotional tone itself is unwanted.
      if(!isLike){
        const reason=['not_my_tone','overused','weak_story','other'].includes(r.dislikeReason)?r.dislikeReason:null;
        if(reason)dislikeReasonCounts[reason]++;else untypedDislikes++;
        if(reason!=='not_my_tone')continue;
      }
      const v=byId.get(id)||r.cache;if(!v||typeof v!=='object')continue;
      const bag=isLike?liked:disliked;let used=false;
      if(typeof v.channelId==='string'&&v.channelId){_bump(bag.channels,v.channelId);used=true;}
      for(const route of routesOf(v))if(TASTE_ROUTES.has(route)){_bump(bag.routes,route);used=true;}
      for(const theme of themesOf(v)){_bump(bag.themes,theme);used=true;}
      if(used){if(isLike)usableLikes++;else usableDislikes++;}
    }
    return {likedCount,dislikedCount,usableLikes,usableDislikes,excludedFromTaste,untypedDislikes,dislikeReasonCounts,liked,disliked,
      // Legacy aliases retained for older UI/tests.
      channelCounts:liked.channels,routeCounts:liked.routes};
  }
  function preferenceClass(v={},profile={}) {
    const liked=profile.liked||{channels:profile.channelCounts||{},routes:profile.routeCounts||{},themes:{}};
    const disliked=profile.disliked||{channels:{},routes:{},themes:{}};
    const positives=[],negatives=[];
    const channel=typeof v.channelId==='string'?v.channelId:'';
    const cs=channel?_signal(liked.channels,disliked.channels,channel):0;
    if(cs>0)positives.push('좋아요가 더 많았던 채널');else if(cs<0)negatives.push('별로가 더 많았던 채널');
    let themePos=false,themeNeg=false,routePos=false,routeNeg=false;
    for(const theme of themesOf(v)){const x=_signal(liked.themes,disliked.themes,theme);if(x>0)themePos=true;else if(x<0)themeNeg=true;}
    for(const route of routesOf(v)){if(!TASTE_ROUTES.has(route))continue;const x=_signal(liked.routes,disliked.routes,route);if(x>0)routePos=true;else if(x<0)routeNeg=true;}
    if(themePos)positives.push('좋아요가 더 많았던 이야기 유형');if(themeNeg)negatives.push('별로가 더 많았던 이야기 유형');
    if(routePos)positives.push('좋아요가 더 많았던 탐색 경로');if(routeNeg)negatives.push('별로가 더 많았던 탐색 경로');
    let bucket='explore';
    if(cs>0||themePos)bucket='close';
    else if(routePos)bucket='adjacent';
    else if((cs<0||themeNeg||routeNeg)&&!positives.length)bucket='low';
    return {bucket,positives,negatives,matched:bucket==='close'||bucket==='adjacent'};
  }
  function tasteMatch(v={},profile={}) {
    const p=preferenceClass(v,profile);return {matched:p.matched,channel:p.positives.includes('좋아요가 더 많았던 채널'),routes:routesOf(v).filter(route=>TASTE_ROUTES.has(route)&&_signal((profile.liked||{}).routes||profile.routeCounts||{},(profile.disliked||{}).routes||{},route)>0),bucket:p.bucket};
  }
  function candidateTier(v={},r={}) {
    const kind=screenKind(v,r);
    if(kind==='non_screen')return 'low';
    if(screenGateInfo(v,r).ok)return 'priority';
    return 'review';
  }
  function candidatePriorityGroup(v={},r={},profile={},tasteAssist=true) {
    const tier=candidateTier(v,r),pref=tasteAssist?preferenceClass(v,profile):{bucket:'explore'};
    if(tier==='low')return 6;
    const tierOffset=tier==='review'?1:0;
    const base={close:0,adjacent:2,explore:4,low:5}[pref.bucket]??4;
    return Math.min(5,base+tierOffset);
  }
  function personalizedBlend(items=[],profile={},tasteAssist=true) {
    const rows=Array.isArray(items)?items.slice():[];
    if(!tasteAssist||Number(profile.usableLikes||0)+Number(profile.usableDislikes||0)<5)return rows;
    const buckets={close:[],adjacent:[],explore:[],low:[]};
    for(const v of rows)buckets[preferenceClass(v,profile).bucket].push(v);
    // 50% close / 30% adjacent / 20% exploration is a display target, not a hard quota.
    // Missing buckets are backfilled; negative-evidence items stay last but are never hidden.
    const pattern=['close','close','close','close','close','adjacent','adjacent','adjacent','explore','explore'];
    const out=[];let progress=true;
    while(progress){progress=false;for(const key of pattern){if(buckets[key].length){out.push(buckets[key].shift());progress=true;}}}
    for(const key of ['close','adjacent','explore','low'])out.push(...buckets[key]);
    return out;
  }

  function recordBatchFeedback(state,generatedAt,outcome,retryRound=1,at=new Date().toISOString()) {
    if(!['no_harvest','useful'].includes(outcome))throw Error('지원하지 않는 수집 피드백입니다.');
    if(typeof generatedAt!=='string'||!Number.isFinite(Date.parse(generatedAt)))throw Error('현재 수집 시각을 확인할 수 없습니다.');
    const next=normalize(state);next.batchFeedback=next.batchFeedback.filter(x=>!(x.generatedAt===generatedAt&&x.outcome===outcome));
    next.batchFeedback.push({generatedAt,outcome,retryRound:Math.min(3,Math.max(1,Number(retryRound)||1)),at});next.batchFeedback=next.batchFeedback.slice(-200);return next;
  }

  function mixRoutes(items,languageOrder=preferredLanguages(),balanceLanguage=false) {
    const groups=new Map();
    for(const v of items){
      const options=routesOf(v);
      // An item found by several routes appears once in the least populated lane.
      const route=options.reduce((a,b)=>(groups.get(a)?.length||0)<=(groups.get(b)?.length||0)?a:b);
      if(!groups.has(route))groups.set(route,[]);groups.get(route).push(v);
    }
    return roundRobin([...groups.values()].map(g=>balanceLanguage?balanceVideos(g,languageOrder):g));
  }

  return {formatOf, shortsInfo, routesOf, themesOf, ROUTE_LABELS, mixRoutes, recordBatchFeedback, buildTasteProfile, preferenceClass, personalizedBlend, tasteMatch, candidateTier, candidatePriorityGroup, screenGateInfo, MAX_AGE, validId, blank, record, normalize, apply, ratio, exportData, merge, parseLink, originOf, isSample, ready, needsReview, mediaOf, LANGUAGE_LABELS, languageInfo, preferredLanguages, defaultFilters, broadFilters, normalizeFilters, screenKind, filterReasons, matchesFilters, filterCounts, balanceVideos};
});
