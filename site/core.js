/* Movie Radar: pure state helpers, usable in the browser and Node tests. */
(function(root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  else root.MovieCore = value;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';
  const MAX_AGE = 29 * 86400000;
  const validId = id => typeof id === 'string' && /^(?:[A-Za-z0-9_-]{11}|demo-[1-9][0-9]*)$/.test(id);
  const blank = () => ({schema:1, records:Object.create(null)});
  function record(id) {
    return {id,rating:null,stage:null,origin:'unknown',media:'unknown',memo:'',label:'',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),cache:null};
  }
  function normalize(raw, now=Date.now()) {
    if (!raw || raw.schema !== 1 || typeof raw.records !== 'object' || !raw.records || Array.isArray(raw.records)) throw Error('Movie Radar 백업 형식이 아닙니다.');
    const out=blank();
    if(Object.keys(raw.records).length>20000) throw Error('한 번에 20,000개를 초과해 복원할 수 없습니다.');
    for(const [id,r] of Object.entries(raw.records)) {
      if(!validId(id) || !r || typeof r !== 'object') continue;
      const x=record(id);
      x.rating=['like','dislike'].includes(r.rating)?r.rating:null;
      x.stage=['candidate','done'].includes(r.stage)?r.stage:null;
      x.origin=originOf(r);
      x.media=mediaOf(r);
      x.memo=String(r.memo||'').slice(0,5000);x.label=String(r.label||'').slice(0,150);
      for(const k of ['createdAt','updatedAt']) if(typeof r[k]==='string' && Number.isFinite(Date.parse(r[k]))) x[k]=r[k];
      const t=Date.parse(r.cache?.fetchedAt);
      if(r.cache?.id===id && Number.isFinite(t) && now-t<MAX_AGE && t<=now+60000) x.cache=r.cache;
      out.records[id]=x;
    }
    return out;
  }
  function apply(state, video, action, now=new Date().toISOString()) {
    if(!validId(video.id)) throw Error('영상 ID 형식이 잘못되었습니다.');
    const next=JSON.parse(JSON.stringify(state)); next.records=Object.assign(Object.create(null),next.records); const r=next.records[video.id]||record(video.id);
    switch(action) {
      case 'like': r.rating='like'; break;
      case 'dislike': r.rating='dislike'; break;
      case 'candidate':
        if (mediaOf(r)==='not_screen' || (!isSample(video) && originOf(r) !== 'non_korean')) throw Error('원작이 한국 외 작품인지 먼저 확인해 주세요.');
        r.stage='candidate'; break;
      case 'uncandidate': r.stage=null; break;
      case 'done': r.stage='done'; break;
      case 'reopen':
        if (mediaOf(r)==='not_screen' || (!isSample(video) && originOf(r) !== 'non_korean')) throw Error('원작이 한국 외 작품인지 먼저 확인해 주세요.');
        r.stage='candidate'; break;
      case 'unrate': r.rating=null; break;
      case 'origin_foreign': r.origin='non_korean'; break;
      case 'origin_korean': r.origin='korean'; break;
      case 'origin_reset': r.origin='unknown'; break;
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
  function ready(v,r) { return mediaOf(r)!=='not_screen' && (isSample(v) || originOf(r)==='non_korean'); }
  function needsReview(v,r={}) { return mediaOf(r)!=='not_screen' && !isSample(v) && originOf(r)==='unknown' && r.rating!=='dislike' && r.stage!=='done'; }
  function ratio(v) {
    const sub=v.subscribers, views=v.views;
    return typeof sub==='number' && sub>0 && typeof views==='number'?views/sub:null;
  }
  function exportData(state) {
    const result=blank();
    for(const [id,r] of Object.entries(normalize(state).records)) {
      // Preserve user-created data, not long-lived API metadata snapshots.
      const {cache,...userData}=r;result.records[id]=userData;
    }
    return result;
  }
  function merge(a,b) {
    const left=normalize(a),right=normalize(b);
    for(const [id,r] of Object.entries(right.records)) {
      if(!left.records[id] || Date.parse(r.updatedAt)>Date.parse(left.records[id].updatedAt))left.records[id]=r;
    }
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
  const preferredLanguages=()=>['en','ja','es','pt','fr','de','it','zh'];
  const defaultFilters=()=>({schema:1,maxSubscribers:10000,minSeconds:0,maxSeconds:180,minViews:100000,content:'screen',languages:preferredLanguages(),includeUnknownLanguage:false,balance:true});
  function normalizeFilters(raw={}) {
    const f=defaultFilters(), numberKeys={maxSubscribers:[0,1000000000],minSeconds:[0,180],maxSeconds:[0,180],minViews:[0,100000000000]};
    for(const [k,[lo,hi]] of Object.entries(numberKeys)) if(Number.isInteger(raw[k])&&raw[k]>=lo&&raw[k]<=hi)f[k]=raw[k];
    // Empty/invalid UI inputs never make NaN comparisons silently accept data.
    if(f.minSeconds>f.maxSeconds){f.minSeconds=0;f.maxSeconds=180;}
    if(['screen','film','all'].includes(raw.content))f.content=raw.content;
    if(Array.isArray(raw.languages))f.languages=[...new Set(raw.languages.filter(x=>typeof x==='string'&&x!=='unknown'&&Object.hasOwn(LANGUAGE_LABELS,x)))];
    for(const k of ['balance','includeUnknownLanguage'])if(typeof raw[k]==='boolean')f[k]=raw[k];
    return f;
  }
  function screenKind(v,r={}) {
    if(mediaOf(r)==='not_screen')return 'non_screen';
    if(['film','series'].includes(v.screenKind))return v.screenKind;
    if(mediaOf(r)==='screen'||originOf(r)==='non_korean'||isSample(v))return 'user_screen';
    return ['film','series','non_screen'].includes(v.screenKind)?v.screenKind:'unknown';
  }
  function filterReasons(v,r,f) {
    if(isSample(v))return []; // fictitious demo items are explicitly exempt from source checks
    const reasons=[],kind=screenKind(v,r);
    if(f.content==='screen'&&!['film','series','user_screen'].includes(kind))reasons.push('content');
    if(f.content==='film'&&kind!=='film')reasons.push('content');
    if(f.maxSubscribers>0&&!(Number.isFinite(v.subscribers)&&v.subscribers>=0&&v.subscribers<=f.maxSubscribers))reasons.push('subscribers');
    const lang=Object.hasOwn(LANGUAGE_LABELS,v.language)?v.language:'unknown';
    if(lang==='unknown'?!f.includeUnknownLanguage:!f.languages.includes(lang))reasons.push('language');
    if(!(Number.isFinite(v.durationSeconds)&&v.durationSeconds>=f.minSeconds&&v.durationSeconds<=f.maxSeconds))reasons.push('duration');
    if(f.minViews>0&&!(Number.isFinite(v.views)&&v.views>=f.minViews))reasons.push('views');
    return reasons;
  }
  function matchesFilters(v,r,f) { return filterReasons(v,r,f).length===0; }
  function filterCounts(items,records,f) {
    const result={total:items.length};let remaining=items;
    for(const reason of ['content','subscribers','language','duration','views']){
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
    for(const v of items){const lang=v.language||'unknown';if(!languages.has(lang))languages.set(lang,[]);languages.get(lang).push(v);}
    const order=[...languageOrder.filter(x=>languages.has(x)),...[...languages.keys()].filter(x=>!languageOrder.includes(x))];
    const queues=order.map(lang=>{const channels=new Map();for(const v of languages.get(lang)){const id=v.channelId||v.id;if(!channels.has(id))channels.set(id,[]);channels.get(id).push(v);}return roundRobin([...channels.values()]);});
    return roundRobin(queues);
  }
  return {MAX_AGE, validId, blank, record, normalize, apply, ratio, exportData, merge, parseLink, originOf, isSample, ready, needsReview, mediaOf, LANGUAGE_LABELS, preferredLanguages, defaultFilters, normalizeFilters, screenKind, filterReasons, matchesFilters, filterCounts, balanceVideos};
});
