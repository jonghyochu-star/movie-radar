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
    return {id,rating:null,stage:null,origin:'unknown',memo:'',label:'',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),cache:null};
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
        if (!isSample(video) && originOf(r) !== 'non_korean') throw Error('원작이 한국 외 작품인지 먼저 확인해 주세요.');
        r.stage='candidate'; break;
      case 'uncandidate': r.stage=null; break;
      case 'done': r.stage='done'; break;
      case 'reopen':
        if (!isSample(video) && originOf(r) !== 'non_korean') throw Error('원작이 한국 외 작품인지 먼저 확인해 주세요.');
        r.stage='candidate'; break;
      case 'unrate': r.rating=null; break;
      case 'origin_foreign': r.origin='non_korean'; break;
      case 'origin_korean': r.origin='korean'; break;
      case 'origin_reset': r.origin='unknown'; break;
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
  function ready(v,r) { return isSample(v) || originOf(r)==='non_korean'; }
  function needsReview(v,r={}) { return !isSample(v) && originOf(r)==='unknown' && r.rating!=='dislike' && r.stage!=='done'; }
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
  return {MAX_AGE, validId, blank, record, normalize, apply, ratio, exportData, merge, parseLink, originOf, isSample, ready, needsReview};
});
