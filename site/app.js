'use strict';
const C=MovieCore, $=s=>document.querySelector(s);
const prefix='movie-radar:v1:'+location.pathname.replace(/index\.html$/,'');
const key=prefix+':records', consentKey=prefix+':consent';
let storageBlocked=false;
const filterKey=prefix+':filters-v1.8', collectionKey=prefix+':collection-v1.4';
let filters=C.defaultFilters();
const defaultCollectionPrefs=()=>({preset:'english_focus',customWeights:'en:70,ja:5,es:5,pt:5,fr:5,de:4,it:3,zh-Hans:3',retryRound:1});
let collectionPrefs=defaultCollectionPrefs();
let state=C.blank(), dataset={mode:'demo',videos:[],generatedAt:null,warnings:[]};
let tab='discover', view='card', page=0, skipped=new Set(), undo=null, editedId=null, toastTimer;
const backupDbName='movie-radar-local-backups-v1',backupStore='handles',backupHandleKey='backup-directory',backupLabelKey=prefix+':backup-label';
const hasFolderAccess=()=>typeof window.showDirectoryPicker==='function'&&typeof indexedDB!=='undefined';
function backupFilename(now=new Date()){
 const pad=n=>String(n).padStart(2,'0');
 return `movie-radar-backup-${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}.json`;
}
function backupPayload(){return {...C.exportData(state),exportedAt:new Date().toISOString()};}
function openBackupDb(){return new Promise((resolve,reject)=>{const req=indexedDB.open(backupDbName,1);req.onupgradeneeded=()=>{if(!req.result.objectStoreNames.contains(backupStore))req.result.createObjectStore(backupStore);};req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error||Error('백업 폴더 정보를 열지 못했습니다.'));});}
async function readBackupFolder(){if(!hasFolderAccess())return null;const db=await openBackupDb();try{return await new Promise((resolve,reject)=>{const tx=db.transaction(backupStore,'readonly'),req=tx.objectStore(backupStore).get(backupHandleKey);req.onsuccess=()=>resolve(req.result||null);req.onerror=()=>reject(req.error);});}finally{db.close();}}
async function storeBackupFolder(handle,label){const db=await openBackupDb();try{await new Promise((resolve,reject)=>{const tx=db.transaction(backupStore,'readwrite');tx.objectStore(backupStore).put({handle,label},backupHandleKey);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||Error('백업 폴더 정보를 저장하지 못했습니다.'));});}finally{db.close();}try{localStorage.setItem(backupLabelKey,label);}catch{}}
async function folderPermission(handle,request=false){if(!handle)return false;const opts={mode:'readwrite'};try{if(await handle.queryPermission(opts)==='granted')return true;if(request&&await handle.requestPermission(opts)==='granted')return true;}catch{}return false;}
function backupFallback(data,filename){const blob=new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);}
async function updateBackupLocation(){const el=$('#backup-location');if(!el)return;if(!hasFolderAccess()){el.textContent='백업 위치: 브라우저 폴더 저장 미지원 · 기본 다운로드 폴더 사용';return;}try{const entry=await readBackupFolder();if(!entry?.handle){el.textContent='백업 위치: 미지정 · 기본 다운로드 폴더 사용';return;}const label=entry.label||localStorage.getItem(backupLabelKey)||entry.handle.name;const granted=await folderPermission(entry.handle,false);el.textContent=`백업 위치: ${label}${granted?'':' · 다음 저장 때 권한 확인'}`;}catch{el.textContent='백업 위치: 확인 실패 · 기본 다운로드 폴더 사용 가능';}}
async function chooseBackupFolder(){if(!hasFolderAccess()){toast('이 브라우저는 폴더 직접 저장을 지원하지 않습니다. 내 기록 백업은 기존처럼 다운로드 폴더에 저장됩니다.');return;}try{const root=await window.showDirectoryPicker({id:'movie-radar-backups',mode:'readwrite',startIn:'documents'});if(!(await folderPermission(root,true))){toast('선택한 폴더에 쓰기 권한을 허용해야 자동 백업 폴더를 사용할 수 있습니다.');return;}const movie=await root.getDirectoryHandle('Movie Radar',{create:true}),backups=await movie.getDirectoryHandle('Backups',{create:true});const label=`${root.name}/Movie Radar/Backups`;await storeBackupFolder(backups,label);await updateBackupLocation();toast(`백업 폴더를 지정했습니다: ${label}`);}catch(error){if(error?.name!=='AbortError')toast('백업 폴더 지정에 실패했습니다. 다운로드 폴더 백업은 계속 사용할 수 있습니다.');}}
async function saveBackup(){const data=backupPayload(),filename=backupFilename();if(hasFolderAccess()){try{const entry=await readBackupFolder();if(entry?.handle&&await folderPermission(entry.handle,true)){const file=await entry.handle.getFileHandle(filename,{create:true}),writer=await file.createWritable();await writer.write(JSON.stringify(data,null,2)+'\n');await writer.close();await updateBackupLocation();toast(`${entry.label||entry.handle.name}에 백업했습니다: ${filename}`);return;}}catch{toast('지정한 백업 폴더에 저장하지 못해 다운로드 폴더 방식으로 전환합니다.');}}backupFallback(data,filename);toast(`다운로드 폴더에 백업했습니다: ${filename}`);}

const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>typeof x==='number'?x.toLocaleString('ko-KR'):'확인 불가';
const short=x=>typeof x==='number'?(x>=10000?(x/10000).toLocaleString('ko-KR',{maximumFractionDigits:1})+'만':fmt(x)):'—';
const dt=x=>x&&Number.isFinite(Date.parse(x))?new Date(x).toLocaleDateString('ko-KR'):'미확인';
const sample=v=>v.id.startsWith('demo-');
function toast(message, allowUndo=false){clearTimeout(toastTimer);$('#toast').innerHTML=esc(message)+(allowUndo?' <button id="undo">되돌리기</button>':'');$('#toast').hidden=false;if(allowUndo)$('#undo').onclick=()=>{if(undo){state=undo.state;skipped=undo.skipped;undo=null;persist();render();toast('되돌렸습니다.');}};toastTimer=setTimeout(()=>$('#toast').hidden=true,6000);}
function warn(message){$('#notice').textContent=message;$('#notice').classList.add('error');}
function persist(){if(storageBlocked){warn('기존 저장 내용이 손상되어 덮어쓰기를 막았습니다. 백업 복원 또는 내 기록 삭제 후 다시 저장하세요.');return false;}try{localStorage.setItem(key,JSON.stringify(state));return true;}catch{warn('브라우저 저장에 실패했습니다. 시크릿 모드·저장 공간을 확인하고, 닫기 전에 내 기록 백업을 실행하세요.');return false;}}
function loadState(){try{storageBlocked=false;const raw=localStorage.getItem(key);if(raw)state=C.normalize(JSON.parse(raw));persist();}catch{warn('기존 저장 내용을 읽지 못했습니다. 자동 덮어쓰기를 멈췄습니다. 백업 복원 또는 사이트 저장 공간을 확인하세요.');storageBlocked=true;state=C.blank();}}
function historyRecord(v){return state.records[v.id]||{};}
function allVideos(){const map=new Map();for(const v of dataset.videos)map.set(v.id,v);for(const [id,r] of Object.entries(state.records)){if(!map.has(id))map.set(id,r.cache||{id,title:r.label||'저장된 YouTube 링크',channelTitle:'최신 정보 없음',source:'직접 저장 또는 현재 수집 목록 외 소재'});}return [...map.values()];}
function visibleRecords(){return Object.entries(state.records).filter(([id])=>dataset.mode==='demo'||!id.startsWith('demo-'));}
function baseVideosForTab(target=tab){
 const collected=new Set(dataset.videos.map(v=>v.id));
 return allVideos().filter(v=>dataset.mode==='demo'||!sample(v)).filter(v=>{
   const r=historyRecord(v),origin=C.originOf(r);
   if(target==='history')return Boolean(r.rating||r.stage||r.memo||r.label||origin!=='unknown'||C.mediaOf(r)!=='unknown'||C.formatOf(r)!=='unknown');
   if(target==='done')return r.stage==='done';
   if(origin==='korean'||C.mediaOf(r)==='not_screen'||C.formatOf(r)==='not_short')return false;
   if(target==='review')return collected.has(v.id)&&C.needsReview(v,r)&&!skipped.has(v.id);
   if(target==='discover')return collected.has(v.id)&&C.ready(v,r)&&!r.rating&&!r.stage&&!skipped.has(v.id);
   if(target==='likes')return r.rating==='like';
   if(target==='candidate')return r.stage==='candidate'&&C.ready(v,r);
   return false;
 });
}
function videosForTab(){
 const exploring=['discover','review'].includes(tab),q=$('#search').value.trim().toLowerCase();
 let items=baseVideosForTab();
 if(exploring)items=items.filter(v=>C.matchesFilters(v,historyRecord(v),filters));
 if(q)items=items.filter(v=>{const r=historyRecord(v);return [v.title,r.label,r.memo,v.channelTitle].join(' ').toLowerCase().includes(q);});
 const sort=$('#sort').value, profile=C.buildTasteProfile(allVideos(),state.records);
 const ordinarySort=rows=>rows.sort((a,b)=>{if(sort==='ratio')return (C.ratio(b)??-1)-(C.ratio(a)??-1)||(b.views??-1)-(a.views??-1);if(sort==='recent')return (Date.parse(b.publishedAt)||0)-(Date.parse(a.publishedAt)||0);if(sort==='saved')return (Date.parse(historyRecord(b).updatedAt)||0)-(Date.parse(historyRecord(a).updatedAt)||0);return (b.views??-1)-(a.views??-1);});
 if(exploring&&sort==='priority'){
   // Preserve movie/TV evidence first, then learn from BOTH likes and dislikes without hiding candidates.
   const tiers=['priority','review','low'];let ordered=[];
   for(const tier of tiers){let group=items.filter(v=>C.candidateTier(v,historyRecord(v))===tier);ordinarySort(group);group=C.personalizedBlend(group,profile,filters.tasteAssist);if(filters.balance)group=C.balanceVideos(group,filters.languages);ordered.push(...group);}
   return ordered;
 }
 ordinarySort(items);
 if(exploring&&filters.mixDiscovery)return C.mixRoutes(items,filters.languages,filters.balance);
 return exploring&&filters.balance?C.balanceVideos(items,filters.languages):items;
}
function normalizeCollectionPrefs(raw={}){
 const d=defaultCollectionPrefs(), presets=['english_focus','english_only','balanced','custom'];
 if(presets.includes(raw.preset))d.preset=raw.preset;
 if(typeof raw.customWeights==='string'&&raw.customWeights.length<=300)d.customWeights=raw.customWeights.trim()||d.customWeights;
 if([1,2,3].includes(Number(raw.retryRound)))d.retryRound=Number(raw.retryRound);
 return d;
}
function loadCollectionPrefs(){try{const saved=localStorage.getItem(collectionKey);if(saved)collectionPrefs=normalizeCollectionPrefs(JSON.parse(saved));}catch{collectionPrefs=defaultCollectionPrefs();}syncCollectionControls();}
function saveCollectionPrefs(){collectionPrefs=normalizeCollectionPrefs(collectionPrefs);try{localStorage.setItem(collectionKey,JSON.stringify(collectionPrefs));}catch{toast('다음 수집 설정을 저장하지 못했습니다.');}syncCollectionControls();updateCollectionCurrent();}
function syncCollectionControls(){
 $('#collect-preset').value=collectionPrefs.preset;$('#custom-weights').value=collectionPrefs.customWeights;$('#retry-round').value=String(collectionPrefs.retryRound);
 $('#custom-weights-wrap').hidden=collectionPrefs.preset!=='custom';
}
function repoActionsUrl(){
 const owner=location.hostname.endsWith('.github.io')?location.hostname.slice(0,-10):'';
 const repo=location.pathname.split('/').filter(Boolean)[0]||'';
 return owner&&repo?`https://github.com/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/actions/workflows/movie-radar.yml`:'';
}
function likedSeedIds(limit=8){
 return Object.values(state.records).filter(r=>r&&r.rating==='like'&&/^[A-Za-z0-9_-]{11}$/.test(r.id||'')&&!String(r.id).startsWith('demo-'))
  .sort((a,b)=>(Date.parse(b.updatedAt)||0)-(Date.parse(a.updatedAt)||0)).slice(0,limit).map(r=>r.id);
}
function seedVideoText(){return likedSeedIds().join(',');}
function collectionInstruction(){
 const custom=collectionPrefs.preset==='custom'?collectionPrefs.customWeights:'';
 return `Movie Radar 다음 수집\nmode: live\ncollect_preset: ${collectionPrefs.preset}\ncustom_weights: ${custom||'(비움)'}\nretry_round: ${collectionPrefs.retryRound}\nseed_video_ids: ${seedVideoText()||'(비움)'}`;
}
async function copyCollectionInstruction(){try{await navigator.clipboard.writeText(collectionInstruction());toast('다음 수집 실행값을 복사했습니다. Actions 화면에서 같은 값으로 실행하세요.');}catch{toast('클립보드 복사에 실패했습니다. 수집 설정을 Actions 화면에서 직접 선택하세요.');}}
async function copySeedIds(){const text=seedVideoText();if(!text){toast('아직 좋아요 씨앗이 없습니다. 씨앗 없이도 검색 경로로 수집할 수 있습니다.');return;}try{await navigator.clipboard.writeText(text);toast(`좋아요 씨앗 ${likedSeedIds().length}개 ID를 복사했습니다. Actions의 seed_video_ids 칸에 붙여넣으세요.`);}catch{toast('씨앗 ID 복사에 실패했습니다. 실행값 전체 복사를 이용하세요.');}}
function updateCollectionCurrent(){
 const p=dataset.collectionPlan||{}, labels={english_focus:'영어 중심',english_only:'영어만',balanced:'다국어 균형',custom:'직접 비중'};
 const ref=dataset.referenceSummary||{},api=dataset.apiUsage||{},seeds=likedSeedIds();
 const quota=api.searchListCalls?` · 이번 실행 search.list ${api.searchListCalls}회`:'';
 const deployedAt=dataset.generatedAt&&Number.isFinite(Date.parse(dataset.generatedAt))?new Date(dataset.generatedAt).toLocaleString('ko-KR'):'시각 미확인';
 const seedWarning=seeds.length>0&&Number(ref.seedRequested||0)===0?' · ⚠ 이번 배포에는 좋아요 씨앗 ID가 전달되지 않음':'';
 const current=p.preset?`현재 배포: ${labels[p.preset]||p.preset} · ${p.retryRound||1}차 · ${deployedAt} · 이전 수집 ID ${p.excludedPreviousIds||0}개 제외 · 좋아요 씨앗 ${ref.seedResolved||0}/${ref.seedRequested||0}${quota}${seedWarning}`:'현재 배포의 수집 언어 계획 정보가 없습니다.';
 const next=`다음 실행 준비: ${labels[collectionPrefs.preset]} · ${collectionPrefs.retryRound}차 · 좋아요 씨앗 ${seeds.length}개${collectionPrefs.preset==='custom'?' · '+collectionPrefs.customWeights:''}`;
 $('#collection-current').textContent=current+' / '+next;
}
function loadFilters(){
 try {const saved=localStorage.getItem(filterKey);if(saved)filters=C.normalizeFilters(JSON.parse(saved));}catch{filters=C.defaultFilters();}
 syncFilterControls();
}
function syncFilterControls(){
 $('#max-subs').value=String(filters.maxSubscribers);$('#content-filter').value=filters.content;
 $('#min-seconds').value=String(filters.minSeconds);$('#max-seconds').value=String(filters.maxSeconds);
 $('#min-views').value=String(filters.minViews);$('#balance').checked=filters.balance;$('#taste-assist').checked=filters.tasteAssist;
 $('#include-unknown-language').checked=filters.includeUnknownLanguage;
 $('#route-filter').value=filters.route;$('#shorts-filter').value=filters.shorts;$('#mix-discovery').checked=filters.mixDiscovery;
 const pair=`${filters.minSeconds}:${filters.maxSeconds}`;
 $('#duration-preset').value=[...$('#duration-preset').options].some(x=>x.value===pair)?pair:'custom';
 $('#language-checks').innerHTML=Object.entries(C.LANGUAGE_LABELS).filter(([code])=>code!=='unknown').map(([code,label])=>`<label><input type="checkbox" data-language="${esc(code)}" ${filters.languages.includes(code)?'checked':''}>${esc(label)}</label>`).join('');
 $('#language-summary').textContent=`${filters.languages.length}개 선택${filters.includeUnknownLanguage?' · 미확인 포함':''}`;
}
function saveFilters(){
 filters=C.normalizeFilters(filters);try{localStorage.setItem(filterKey,JSON.stringify(filters));}catch{toast('필터 설정을 저장하지 못했습니다. 현재 화면에만 적용됩니다.');}
 syncFilterControls();page=0;render();
}
function updateFilterSummary(){
 const exploring=['discover','review'].includes(tab);$('#filter-panel').hidden=!exploring;
 if(!exploring)return;
 const base=baseVideosForTab(),n=C.filterCounts(base,state.records,filters),shown=base.filter(v=>C.matchesFilters(v,historyRecord(v),filters));
 const profile=C.buildTasteProfile(allVideos(),state.records);
 const priority=shown.filter(v=>C.candidateTier(v,historyRecord(v))==='priority').length;
 const review=shown.filter(v=>C.candidateTier(v,historyRecord(v))==='review').length;
 const prefCounts={close:0,adjacent:0,explore:0,low:0};for(const v of shown)prefCounts[C.preferenceClass(v,profile).bucket]++;
 const learned=profile.usableLikes+profile.usableDislikes;
 $('#filter-summary').textContent=`이 탭의 미검토 ${n.total}개 → 영화·드라마 게이트 ${n.content}개 → 언어 ${n.language}개 → 길이 ${n.duration}개 → 조회수 ${n.views}개. 표시 후보 중 영화·드라마 우선 ${priority}개 · 확인 필요 ${review}개. 취향 데이터 좋아요 ${profile.likedCount} / 별로 ${profile.dislikedCount} · 활용 가능 ${learned}개. 현재 후보: 취향 가까움 ${prefCounts.close} · 인접한 새 결 ${prefCounts.adjacent} · 새로운 결 ${prefCounts.explore} · 낮은 적중 경로 ${prefCounts.low}. ${filters.tasteAssist?'좋아요·별로는 순서에만 반영하고 후보를 숨기지 않습니다. ':''}`;
}
function priorityPanel(v,r){
 const tier=C.candidateTier(v,r),profile=C.buildTasteProfile(allVideos(),state.records),pref=C.preferenceClass(v,profile),gate=C.screenGateInfo(v,r);
 const labels={priority:'영화·드라마 우선',review:'게이트 확인 필요',low:'비영화 의심'};
 const notes={priority:`${gate.label}. YouTube 주제/메타데이터 근거이며 실제 장면을 AI가 본 결과는 아닙니다.`,review:'영화·드라마 수집 게이트가 확인되지 않아 직접 확인이 필요합니다.',low:'제품·게임·기타 비영화 자료 단서가 강합니다.'};
 const prefLabels={close:'♥ 취향 가까움',adjacent:'↗ 인접한 새 결',explore:'✦ 새로운 결',low:'↓ 낮은 적중 경로'};
 const reason=[...pref.positives,...pref.negatives].join(' · ')||'좋아요/별로 기록과 직접 겹치는 단서가 없어 새로운 탐색으로 남겼습니다.';
 const taste=filters.tasteAssist?`<span class="taste pref-${esc(pref.bucket)}" title="${esc(reason)}. 좋아요·별로는 순서 참고 신호일 뿐 후보를 자동 제외하지 않습니다.">${esc(prefLabels[pref.bucket])}</span>`:'';
 const gateBadge=tier==='priority'?`<span title="수집 게이트: ${esc(gate.label)}">${esc(gate.label)}</span>`:'';
 return `<div class="priority-strip ${esc(tier)}"><span title="${esc(notes[tier])}">${esc(labels[tier])}</span>${gateBadge}${taste}</div>`;
}
function evidencePanel(v,r){
 if(sample(v))return '';
 const kind=C.screenKind(v,r),labels={film:'영화 단서',series:'드라마·시리즈 단서',unknown:'영상 종류 미확인',non_screen:'비영화 의심',user_screen:'사용자가 확인한 작품'};
 const li=C.languageInfo(v), language=li.badge;
 const audioLabel=C.LANGUAGE_LABELS[li.audio]||'언어 미확인',declaredLabel=C.LANGUAGE_LABELS[li.declared]||'언어 미확인';
 const manual=C.mediaOf(r)==='not_screen'?'사용자 제외 · 영화/드라마 아님':labels[kind],gate=C.screenGateInfo(v,r);
 return `<div class="evidence"><div class="evidence-chips"><span>${esc(manual)}</span><span>${esc(language)}</span></div><details><summary>필터 판단 근거</summary><p>수집 게이트: ${esc(gate.label)}<br>${esc(v.screenReason||'메타데이터 영상 종류 단서가 없습니다.')}<br>${esc(li.basis)}<br>업로더 음성 설정: ${esc(audioLabel)}<br>제목·설명 언어 설정: ${esc(declaredLabel)} (음성 언어와 별개)<br>실제 음성·자막·원작 제작국·감동결을 검증한 결과가 아닙니다.</p></details></div>`;
}
function discoveryPanel(v,r){
 if(sample(v))return '';
 const f=C.shortsInfo(v,r),manual=C.formatOf(r);
 const badges=C.routesOf(v).map(x=>`<span>${esc(C.ROUTE_LABELS[x])}</span>`).join('');
 let buttons='';
 if(manual!=='shorts')buttons+='<button data-action="format_yes" title="YouTube 원본을 열어 실제 Shorts임을 확인했을 때 누릅니다.">쇼츠 맞음 · 확인</button>';
 if(manual!=='not_short')buttons+='<button data-action="format_no" title="YouTube Shorts가 아닌 일반 영상으로 확인했을 때 후보에서 제외합니다.">일반 영상 제외</button>';
 if(manual!=='unknown')buttons+='<button data-action="format_reset" title="내가 남긴 쇼츠/일반 영상 확인을 취소합니다.">쇼츠 확인 취소</button>';
 return `<div class="discovery-evidence"><div class="route-chips">${badges}</div><small>발견 경로입니다. 감동 분석·원작 확인 결과가 아닙니다.</small><details class="format-details"><summary>${esc(f.label)} · 확인/수정</summary><p>${esc(f.reason)}</p><p>원본을 확인한 뒤 표시하세요. 일반 영상 제외는 좋아요·메모를 지우지 않으며 평가 기록에서 되돌릴 수 있습니다.</p><div class="origin-actions">${buttons}</div></details></div>`;
}
function updateDiscoverySummary(){
 const plans=Array.isArray(dataset.discoveryPlan)?dataset.discoveryPlan:[];
 const summary=$('#discovery-summary');
 if(dataset.mode!=='live'||!plans.length){summary.hidden=true;return;}
 summary.hidden=false;
 const channels=dataset.referenceSummary?.channels||[];
 const lines=plans.map(p=>`<li><strong>${esc(C.ROUTE_LABELS[p.lane]||'검색')}</strong> · ${esc(p.label)} · ${esc(p.language)}</li>`).join('');
 const scanned=channels.reduce((a,c)=>a+(Number(c.scannedUploads)||0),0);
 const cp=dataset.collectionPlan||{};const labels={english_focus:'영어 중심',english_only:'영어만',balanced:'다국어 균형',custom:'직접 비중'};
 const summaryData=dataset.collectionSummary||{},active=(cp.activeLanguages||[]).join(', ')||'미표시',dup=Number(summaryData.duplicateCandidatesSuppressed)||0;
 const ref=dataset.referenceSummary||{},api=dataset.apiUsage||{},cats=summaryData.sourceCategoryCounts||{},gates=summaryData.screenGateCounts||{};
 const raw=Number(summaryData.rawAfterSafetyCap??summaryData.eligibleBeforeCap??dataset.videos.length)||0,kept=Number(summaryData.kept??dataset.videos.length)||0,reserve=Number(summaryData.reserveCount)||0;
 const pool=`원본 후보 ${raw}개 → 이번 검토 풀 ${kept}개${reserve?` · 예비 ${reserve}개`:''}`;
 const policy=summaryData.perChannelLimit?`한 채널 최대 ${summaryData.perChannelLimit}개 · 씨앗 출처 최대 ${summaryData.seedPoolPercent}% · 참고 출처 최대 ${summaryData.referencePoolPercent}%`:'';
 const mix=`검색 ${Number(cats.guided||0)+Number(cats.explore||0)} · 씨앗 ${Number(cats.seed||0)} · 참고 ${Number(cats.reference||0)} · 기타 ${Number(cats.configured||0)+Number(cats.other||0)}`;
 const gateSummary=`영화 주제 ${Number(gates.movie||0)} · TV 주제 ${Number(gates.tv||0)} · 메타데이터 보강 ${Number(gates.metadata||0)}`;
 const rejected=`비영화 강한 단서 ${Number(summaryData.rejectedNonScreen||0)}개 · 채널 업로드 중 영화/드라마 근거 부족 ${Number(summaryData.rejectedSourceWithoutScreenEvidence||0)}개 제외`;
 summary.innerHTML=`<summary>이번 수집 경로 보기 · ${esc(pool)}</summary><p><strong>검토 풀:</strong> ${esc(pool)}${policy?' · '+esc(policy):''}<br><strong>영화·드라마 게이트:</strong> ${esc(gateSummary)}<br><strong>출처 구성:</strong> ${esc(mix)}. 씨앗/참고 비중은 상한입니다.</p><p><strong>수집 언어:</strong> ${esc(labels[cp.preset]||'이전 방식')} · 이번 실행 언어 ${esc(active)} · ${esc(cp.retryRound||1)}차 탐색 · 최근 수집 ID ${esc(cp.excludedPreviousIds||0)}개 제외</p><p><strong>좋아요 반영:</strong> 씨앗 영상 ${esc(ref.seedResolved||0)}/${esc(ref.seedRequested||0)}개 확인 · 씨앗 채널 ${esc(ref.seedChannels||0)}개. 좋아요는 출처 힌트이며 채널 전체를 영화로 간주하지 않습니다.</p><ul>${lines}</ul><p>채널 업로드 ${scanned}건을 조회했고, ${esc(rejected)}했습니다. 정확한 영상 ID와 제목이 거의 같은 재업로드 후보 <strong>${esc(dup)}개</strong>도 중복 억제했습니다.</p><p><strong>API 사용:</strong> 이번 실행 search.list ${esc(api.searchListCalls??'—')}회 · 기타 조회 ${esc(api.otherCalls??'—')}회. 전체 일일 잔여량은 Google Cloud에서 확인해야 합니다.</p><p>1.8은 YouTube Movies/TV 주제에서 먼저 검색하고, 브라우저의 좋아요·별로 기록은 후보의 표시 순서에만 반영합니다.</p>`;
}
function originPanel(v,r){
 if(sample(v))return '';
 const origin=C.originOf(r);
 const labels={unknown:'원작 확인 필요',non_korean:'한국 외 원작 · 내가 확인함',korean:'한국 영화 · 추천에서 제외됨'};
 const hints={unknown:'제목·채널 국가·사용 언어만으로 원작 제작국을 판정하지 않았습니다.',non_korean:'사용자가 확인해 남긴 분류입니다. 자동 영화 인식 결과가 아닙니다.',korean:'좋아요·메모는 삭제하지 않았습니다. 이 영상은 평가 기록에서 다시 찾을 수 있습니다.'};
 let buttons='';
 if(origin!=='non_korean')buttons+='<button data-action="origin_foreign" title="원작을 직접 확인했고 한국 영화가 아닐 때 누릅니다. 영상 언어만으로 판단하지 않습니다.">한국 외 원작 확인</button>';
 if(origin!=='korean')buttons+='<button data-action="origin_korean" title="원작이 한국 영화임을 직접 확인했을 때 추천 목록에서 제외합니다.">한국 영화 제외</button>';
 if(origin!=='unknown')buttons+='<button data-action="origin_reset" title="내가 남긴 원작 제작국 확인을 취소하고 다시 미확인 상태로 돌립니다.">원작 확인 취소</button>';
 return `<div class="origin-box ${origin}"><strong>${labels[origin]}</strong><p>${hints[origin]}</p><div class="origin-actions">${buttons}</div></div>`;
}
function renderCard(v){const r=historyRecord(v), ratio=C.ratio(v), duration=typeof v.durationSeconds==='number'?`${Math.floor(v.durationSeconds/60)}:${String(v.durationSeconds%60).padStart(2,'0')}`:'길이 미확인';
 let thumb=sample(v)?'<div class="demo-art"><b>◇</b><span>SAMPLE · 실제 영상 아님</span></div>':'<span>미리보기 없음 · 원본에서 확인</span>';
 if(v.thumbnail && /^https:\/\/(?:i\.ytimg\.com|img\.youtube\.com)\//.test(v.thumbnail))thumb=`<img src="${esc(v.thumbnail)}" alt="${esc(v.title)}" loading="lazy">`;
 const labels=[r.rating==='like'?'좋아요':r.rating==='dislike'?'별로':null,r.stage==='candidate'?'제작 후보':r.stage==='done'?'제작 완료':null].filter(Boolean).join(' · ');
 let buttons=sample(v)?'<button disabled>샘플 · 원본 없음</button>':`<a class="open-link" title="YouTube 원본을 새 탭에서 열어 실제 장면·쇼츠 여부·원작을 확인합니다." href="https://www.youtube.com/watch?v=${encodeURIComponent(v.id)}" target="_blank" rel="noopener noreferrer">YouTube 원본 열기 ↗</a>`;
 if(tab==='discover'||tab==='review')buttons+=(r.rating==='like'?'<button class="like saved" disabled title="이미 좋아요 보관함에 저장된 소재입니다. 취소는 아래 평가 취소를 사용하세요.">♥ 좋아요 저장됨</button>':'<button class="like" data-action="like" title="마음에 남는 소재를 좋아요 보관함에 저장합니다. 바로 제작 후보가 되는 것은 아닙니다.">♡ 좋아요 저장</button>')+(r.rating==='dislike'?'<button class="dislike saved" disabled title="이미 별로로 기록했습니다. 취소는 아래 평가 취소를 사용하세요.">별로 저장됨</button>':'<button data-action="dislike" title="소재의 내용이 내 취향과 맞지 않을 때 기록합니다. 한국 영화·일반 영상 제외와는 별개입니다.">별로</button>')+'<button data-action="later" title="취향 판단 없이 이번 탐색에서만 잠시 넘깁니다.">나중에</button>';
 else if(C.originOf(r)!=='korean'&&C.mediaOf(r)!=='not_screen'&&C.formatOf(r)!=='not_short'){if(r.stage!=='candidate'&&r.stage!=='done'&&C.ready(v,r))buttons+='<button class="primary" data-action="candidate" title="좋아요 소재 중 실제 제작할 후보로 한 단계 더 선별합니다.">제작 후보로</button>';if(r.stage==='candidate')buttons+='<button class="primary" data-action="done" title="이 소재로 제작을 마쳤다고 표시합니다.">제작 완료</button><button data-action="uncandidate" title="제작 후보 표시만 해제합니다. 좋아요는 유지됩니다.">후보 해제</button>';if(r.stage==='done'&&C.ready(v,r))buttons+='<button data-action="reopen" title="제작 완료 상태를 다시 제작 후보 상태로 되돌립니다.">후보로 되돌리기</button>';if(r.rating!=='like')buttons+='<button class="like" data-action="like" title="마음에 남는 소재를 좋아요 보관함에 저장합니다.">좋아요 저장</button>';}
 const media=C.mediaOf(r);
 const sub=[];
 if(!sample(v)){
   if(media!=='not_screen')sub.push('<button data-action="media_no" title="영화·드라마 장면이 아닌 영상으로 확인했을 때 제외합니다.">영화·드라마 아님</button>');
   if(media!=='screen')sub.push('<button data-action="media_yes" title="영화·드라마 장면임을 직접 확인했을 때 표시합니다.">영화·드라마 맞음</button>');
   if(media!=='unknown')sub.push('<button data-action="media_reset" title="내가 남긴 영화·드라마 여부 확인을 취소합니다.">종류 확인 취소</button>');
 }
 sub.push('<button data-action="memo" title="작품명·감동 포인트·편집 아이디어 등 내 메모를 남깁니다.">메모</button>');if(r.rating)sub.push('<button data-action="unrate" title="좋아요 또는 별로 기록만 취소합니다. 원작·쇼츠 확인은 유지됩니다.">평가 취소</button>');if(r.stage!=='done')sub.push('<button data-action="done" title="이미 제작한 소재로 표시해 다시 제작 후보로 고르는 일을 줄입니다.">이미 제작함</button>');
 return `<article class="card${r.rating==='like'?' is-liked':''}${r.rating==='dislike'?' is-disliked':''}" data-id="${esc(v.id)}"><div class="thumb ${v.thumbnail?'':'empty'}">${thumb}</div><div class="body"><div class="meta"><span>${esc(v.channelTitle||'채널 미확인')}${labels?' · '+esc(labels):''}</span><span>${esc(duration)}</span></div><h4>${esc(v.title||'저장된 YouTube 링크')}</h4><div class="stats"><div><span>조회수</span><strong title="${esc(fmt(v.views))}">${short(v.views)}</strong></div><div><span>공개 구독자 수</span><strong title="${esc(fmt(v.subscribers))}">${short(v.subscribers)}</strong></div><div><span>조회 ÷ 구독</span><strong title="현재 조회수 ÷ 공개 구독자 수. 공개 구독자 수의 내림·미확인의 영향이 있으며 성공 점수가 아닙니다.">${ratio===null?'—':'약 '+ratio.toLocaleString('ko-KR',{maximumFractionDigits:1})+'배'}</strong></div></div><p class="reason">${sample(v)?'기능 확인용 가상 데이터입니다.':esc(v.source||'YouTube 공개 API 데이터')}<br>게시 ${dt(v.publishedAt)} · 수집 ${dt(v.fetchedAt)}</p>${priorityPanel(v,r)}${discoveryPanel(v,r)}${evidencePanel(v,r)}${originPanel(v,r)}${r.label?`<div class="mynote"><strong>내 제목</strong> ${esc(r.label)}</div>`:''}${r.memo?`<div class="mynote">${esc(r.memo)}</div>`:''}<div class="buttons">${buttons}</div><div class="subbuttons">${sub.join('')}</div></div></article>`;
}
function render(){
 const active=visibleRecords().map(([id,r])=>({id,...r}));
 const canList=r=>C.originOf(r)!=='korean'&&C.mediaOf(r)!=='not_screen'&&C.formatOf(r)!=='not_short';
 $('#n-discover').textContent=baseVideosForTab('discover').filter(v=>C.matchesFilters(v,historyRecord(v),filters)).length;
 $('#n-review').textContent=baseVideosForTab('review').filter(v=>C.matchesFilters(v,historyRecord(v),filters)).length;
 $('#n-likes').textContent=active.filter(r=>canList(r)&&r.rating==='like').length;
 $('#n-candidate').textContent=active.filter(r=>canList(r)&&r.stage==='candidate'&&C.ready(r,r)).length;
 $('#n-done').textContent=active.filter(r=>r.stage==='done').length;
 for(const b of document.querySelectorAll('[data-tab]'))b.classList.toggle('active',b.dataset.tab===tab);
 $('#section-title').textContent={discover:'원작을 확인한 미평가 소재',review:'이번 수집의 새 후보를 확인하세요',likes:'마음에 남은 장면을 다시 고르세요',candidate:'이제 제작할 이야기',done:'제작을 마친 소재',history:'원작 확인·한국 영화 제외·평가 기록'}[tab];
 const exploring=['discover','review'].includes(tab), isCard=exploring&&view==='card';
 const size=isCard?1:20,items=videosForTab(),pages=Math.max(1,Math.ceil(items.length/size));
 page=Math.max(0,Math.min(page,pages-1));const slice=items.slice(page*size,(page+1)*size);
 $('#content').className=isCard?'review':'grid';
 $('#content').innerHTML=slice.length?slice.map(renderCard).join(''):'<div class="empty-state" style="grid-column:1/-1"><h3>이 조건의 소재가 없습니다.</h3><p>처음 수집한 영상은 원작 확인 필요 탭에 있습니다.<br>위의 조건별 남은 개수를 확인하세요. ‘1만 이하’·‘언어 미확인 포함’·‘전체 영상 종류’를 직접 바꿀 수 있습니다. 조건을 자동으로 완화하지 않습니다.<br>새 수집은 GitHub Actions에서 실행합니다. 목록 새로고침은 배포된 목록만 다시 읽습니다.</p></div>';
 $('#result-count').textContent=`현재 조건 ${items.length}개 · ${isCard?'한 장씩':'20개씩 목록'}`;
 $('#page-label').textContent=`${page+1} / ${pages}`;
 $('#previous').disabled=page===0;$('#next').disabled=page>=pages-1;
 $('#previous').textContent=isCard?'이전 소재':'이전 묶음';$('#next').textContent=isCard?'다음 소재':'다음 20개';
 $('#layout').hidden=!exploring;$('#layout').textContent=view==='card'?'목록으로 보기':'한 장씩 보기';
 updateFilterSummary();
 updateDiscoverySummary();
 updateCollectionCurrent();
 $('#views-label').hidden=!exploring;$('#revisit').hidden=!exploring||skipped.size===0;
}
function snapshot(){undo={state:JSON.parse(JSON.stringify(state)),skipped:new Set(skipped)};}
function handleAction(id,action){const v=allVideos().find(x=>x.id===id);if(!v)return;if(action==='memo'){editedId=id;$('#edit-label').value=historyRecord(v).label||'';$('#edit-memo').value=historyRecord(v).memo||'';$('#edit-dialog').showModal();return;}snapshot();if(action==='later'){skipped.add(id);render();toast('이번 탐색에서만 넘겼습니다. 취향 평가에는 쓰지 않습니다.',true);return;}if(['format_yes','format_no'].includes(action)&&!confirm(action==='format_yes'?'YouTube 원본에서 Shorts임을 확인하셨나요? 길이·태그만으로 판단하지 마세요.':'일반 영상으로 제외할까요? 좋아요·메모는 남기고 추천·보관함·후보에서 숨깁니다. 평가 기록에서 취소할 수 있습니다.'))return;if(action==='media_no'&&!confirm('영화·드라마 장면이 아닌 자료로 표시할까요? 추천·보관함·후보에서 숨기고 기존 메모·평가는 평가 기록에 남깁니다.'))return;if(['origin_foreign','origin_korean'].includes(action)&&!confirm(action==='origin_foreign'?'원작을 확인했고, 한국 영화가 아닌 작품이 맞나요? 영상 언어·채널 국가만으로 판단하지 마세요.':'원작이 한국 영화임을 확인했나요? 이 영상만 추천·보관함·제작 후보에서 숨기며, 메모와 기존 기록은 보존합니다.'))return;try{state=C.apply(state,v,action);}catch(error){toast(error.message);return;}const ok=persist();render();if(ok)toast({format_yes:'쇼츠로 확인했습니다. 원작과 감동결은 별도입니다.',format_no:'일반 영상으로 제외했습니다. 취향 평가는 바꾸지 않았습니다.',format_reset:'쇼츠 확인을 취소했습니다.',like:'좋아요 보관함에 저장했습니다.',dislike:'별로로 기록했습니다.',candidate:'제작 후보에 넣었습니다.',uncandidate:'후보만 해제했습니다. 좋아요는 유지됩니다.',done:'제작 완료로 기록했습니다.',reopen:'제작 후보로 되돌렸습니다.',unrate:'취향 평가를 취소했습니다.',origin_foreign:'한국 외 원작으로 기록했습니다. 소재 탐색에서 검토할 수 있습니다.',origin_korean:'한국 영화로 제외했습니다. 평가 기록에서 되돌릴 수 있습니다.',origin_reset:'원작 확인을 취소했습니다. 확인 필요 탭으로 분리합니다.',media_no:'영화·드라마가 아닌 영상으로 제외했습니다. 평가 기록에서 취소할 수 있습니다.',media_yes:'영화·드라마로 확인했습니다. 원작 제작국은 별도로 확인하세요.',media_reset:'영상 종류 확인을 취소했습니다. 원래 필터를 적용합니다.'}[action],true);}
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function fetchDeployment(){
 const response=await fetch('data/videos.json?t='+Date.now(),{cache:'no-store'});
 if(!response.ok)throw Error(`목록 파일을 읽지 못했습니다 (${response.status}).`);
 const data=await response.json();
 if(!Array.isArray(data.videos)||!['live','demo'].includes(data.mode))throw Error('목록 파일 형식이 잘못되었습니다.');
 return data;
}
function applyDeployment(data){
 dataset=data;
 const stale=data.mode==='live'&&(!Number.isFinite(Date.parse(data.generatedAt))||Date.now()-Date.parse(data.generatedAt)>C.MAX_AGE);
 if(stale){dataset={...data,videos:[]};warn('수집 정보가 29일을 넘겨 표시하지 않습니다. GitHub Actions에서 live로 다시 수집해 주세요.');}
 else{$('#notice').classList.remove('error');$('#notice').textContent=data.mode==='demo'?'샘플 모드입니다. 제목·조회수는 기능 확인용 가상 데이터이며 실제 영상이 아닙니다. API 키를 등록하고 live로 실행하면 실제 목록으로 바뀝니다.':(data.warnings||[]).length?'수집 안내: '+data.warnings.join(' / '):'1.8.1 · 1.8 추천 구조를 유지하면서 백업 폴더를 지정해 기록을 찾기 쉽게 보관할 수 있습니다.';}
 if(data.mode==='live'&&data.collectorVersion!=='1.8')warn('앱은 1.8이지만 수집 데이터는 이전 버전입니다. Actions에서 새 main / live 실행이 필요합니다.');
 for(const v of dataset.videos){if(state.records[v.id]&&v.fetchedAt)state.records[v.id].cache=v;}
 state=C.normalize(state);persist();$('#mode').textContent=data.mode==='live'?'YouTube 연결':'SAMPLE';$('#mode').classList.toggle('live',data.mode==='live');
 const round=data.collectionPlan?.retryRound||'—';
 $('#updated').textContent=`목록 갱신: ${data.generatedAt?new Date(data.generatedAt).toLocaleString('ko-KR'):'샘플 초기 파일'} · ${round}차 배포 · 수집량 ${data.videos.length}개`;
 updateCollectionCurrent();if(data.mode==='live'&&tab==='discover'&&!dataset.videos.some(v=>C.ready(v,historyRecord(v))&&!historyRecord(v).rating&&!historyRecord(v).stage)&&allVideos().some(v=>C.needsReview(v,historyRecord(v))))tab='review';page=0;render();
}
async function refresh(waitForNew=false){
 const button=$('#refresh'),before=dataset.generatedAt||null;button.disabled=true;
 const original=button.textContent;
 try{
  const attempts=waitForNew&&before?12:1;
  for(let attempt=1;attempt<=attempts;attempt++){
   if(waitForNew&&before)button.textContent=`새 배포 확인 ${attempt}/${attempts}`;
   const data=await fetchDeployment();
   const changed=!before||data.generatedAt!==before||data.mode!==dataset.mode;
   if(changed||!waitForNew){applyDeployment(data);if(waitForNew&&before)toast(`새 배포를 확인했습니다: ${data.collectionPlan?.retryRound||'—'}차 · ${data.generatedAt?new Date(data.generatedAt).toLocaleString('ko-KR'):''}`);return;}
   if(attempt<attempts)await wait(5000);
  }
  toast('아직 이전 배포가 보입니다. Actions가 성공했어도 GitHub Pages 반영에 시간이 걸릴 수 있습니다. 잠시 뒤 다시 확인하세요.');
 }catch(error){warn(error.message+' 보관함은 계속 사용할 수 있습니다.');render();}
 finally{button.disabled=false;button.textContent=original;}
}
$('#tabs').onclick=e=>{const b=e.target.closest('[data-tab]');if(!b)return;tab=b.dataset.tab;page=0;$('#search').value='';$('#sort').value=['discover','review'].includes(tab)?'priority':'saved';render();};$('#content').onclick=e=>{const b=e.target.closest('[data-action]');if(b)handleAction(b.closest('[data-id]').dataset.id,b.dataset.action);};
$('#layout').onclick=()=>{view=view==='card'?'grid':'card';page=0;render();};$('#next').onclick=()=>{page++;render();};$('#previous').onclick=()=>{page--;render();};$('#revisit').onclick=()=>{skipped.clear();page=0;render();};for(const id of ['#search','#sort'])$(id).addEventListener(id==='#search'?'input':'change',()=>{page=0;render();});$('#refresh').onclick=()=>refresh(true);
$('#edit-form').onsubmit=e=>{e.preventDefault();snapshot();const v=allVideos().find(x=>x.id===editedId),r=state.records[editedId]||C.record(editedId);r.label=$('#edit-label').value.trim();r.memo=$('#edit-memo').value.trim();r.updatedAt=new Date().toISOString();if(v?.fetchedAt)r.cache=v;state.records[editedId]=r;const ok=persist();$('#edit-dialog').close();render();if(ok)toast('메모를 저장했습니다.',true);};$('#edit-cancel').onclick=()=>$('#edit-dialog').close();
$('#add-link').onclick=()=>$('#link-dialog').showModal();$('#link-cancel').onclick=()=>$('#link-dialog').close();$('#link-form').onsubmit=e=>{e.preventDefault();try{const id=C.parseLink($('#link-url').value);snapshot();state=C.apply(state,{id},'like');const label=$('#link-label').value.trim();if(label)state.records[id].label=label;const ok=persist();$('#link-dialog').close();$('#link-form').reset();tab='likes';page=0;render();if(ok)toast('링크를 보관함에 저장했습니다.',true);}catch(error){toast(error.message);}};
$('#backup-folder').onclick=chooseBackupFolder;$('#backup').onclick=saveBackup;
$('#restore').onclick=()=>$('#import-file').click();$('#import-file').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>10000000)throw Error('10MB 이하의 백업 파일을 선택하세요.');const imported=C.normalize(JSON.parse(await f.text()));if(!confirm(`백업의 ${Object.keys(imported.records).length}개 기록을 합칠까요? 같은 소재는 더 최근 기록을 유지합니다.`))return;snapshot();storageBlocked=false;state=C.merge(state,imported);for(const v of dataset.videos){if(state.records[v.id])state.records[v.id].cache=v;}const ok=persist();render();if(ok)toast('백업을 복원했습니다.',true);}catch(error){toast('복원 실패: '+error.message);}finally{e.target.value='';}};
$('#clear').onclick=()=>{if(!confirm('이 Movie Radar의 좋아요·제작 상태·메모를 모두 삭제할까요? 먼저 백업을 권장합니다. 기존 Shorts Radar는 삭제하지 않습니다.'))return;storageBlocked=false;state=C.blank();undo=null;skipped.clear();persist();render();toast('이 앱의 내 기록을 삭제했습니다.');};

$('#route-filter').onchange=()=>{filters.route=$('#route-filter').value;saveFilters();};
$('#shorts-filter').onchange=()=>{filters.shorts=$('#shorts-filter').value;saveFilters();};
$('#mix-discovery').onchange=()=>{filters.mixDiscovery=$('#mix-discovery').checked;saveFilters();};
$('#max-subs').onchange=()=>{filters.maxSubscribers=Number($('#max-subs').value);saveFilters();};
$('#content-filter').onchange=()=>{filters.content=$('#content-filter').value;saveFilters();};
$('#min-views').onchange=()=>{filters.minViews=Number($('#min-views').value);saveFilters();};
$('#duration-preset').onchange=()=>{const v=$('#duration-preset').value;if(v==='custom'){$('#min-seconds').focus();return;}[filters.minSeconds,filters.maxSeconds]=v.split(':').map(Number);saveFilters();};
for(const id of ['#min-seconds','#max-seconds'])$(id).onchange=()=>{
 const lo=Number($('#min-seconds').value),hi=Number($('#max-seconds').value);
 if($('#min-seconds').value===''||$('#max-seconds').value===''||!Number.isInteger(lo)||!Number.isInteger(hi)||lo<0||hi>180||lo>hi){toast('최소~최대를 0~180초 범위로 입력하세요. 최소는 최대보다 클 수 없습니다.');syncFilterControls();return;}
 filters.minSeconds=lo;filters.maxSeconds=hi;saveFilters();
};
$('#language-checks').onchange=()=>{filters.languages=[...document.querySelectorAll('[data-language]:checked')].map(x=>x.dataset.language);saveFilters();};
$('#include-unknown-language').onchange=()=>{filters.includeUnknownLanguage=$('#include-unknown-language').checked;saveFilters();};
$('#balance').onchange=()=>{filters.balance=$('#balance').checked;saveFilters();};
$('#taste-assist').onchange=()=>{filters.tasteAssist=$('#taste-assist').checked;saveFilters();};
$('#preferred-languages').onclick=()=>{filters.languages=C.preferredLanguages();filters.includeUnknownLanguage=false;saveFilters();};
$('#all-languages').onclick=()=>{filters.languages=Object.keys(C.LANGUAGE_LABELS).filter(x=>x!=='unknown');filters.includeUnknownLanguage=true;saveFilters();};
$('#collect-preset').onchange=()=>{collectionPrefs.preset=$('#collect-preset').value;saveCollectionPrefs();};
$('#custom-weights').onchange=()=>{collectionPrefs.customWeights=$('#custom-weights').value;saveCollectionPrefs();};
$('#retry-round').onchange=()=>{collectionPrefs.retryRound=Number($('#retry-round').value);saveCollectionPrefs();};
$('#open-actions').onclick=()=>{const u=repoActionsUrl();if(u)window.open(u,'_blank','noopener');else toast('GitHub Actions 주소를 자동으로 만들지 못했습니다. 저장소의 Actions 탭을 여세요.');};
$('#copy-seeds').onclick=copySeedIds;
$('#find-more').onclick=async()=>{const current=Number(dataset.collectionPlan?.retryRound)||collectionPrefs.retryRound||1;collectionPrefs.retryRound=Math.min(3,current+1);saveCollectionPrefs();const u=repoActionsUrl();if(u)window.open(u,'_blank','noopener');await copyCollectionInstruction();};
$('#no-harvest').onclick=()=>{if(dataset.mode!=='live'||!dataset.generatedAt){toast('실제 수집 목록에서만 수확 없음 기록을 남길 수 있습니다.');return;}const current=Number(dataset.collectionPlan?.retryRound)||collectionPrefs.retryRound||1;state=C.recordBatchFeedback(state,dataset.generatedAt,'no_harvest',current);persist();collectionPrefs.retryRound=Math.min(3,current+1);saveCollectionPrefs();toast(`이번 수집을 ‘수확 없음’으로 기록했습니다. 다음은 ${collectionPrefs.retryRound}차 재탐색을 추천합니다.`);};
$('#reset-filters').onclick=()=>{filters=C.defaultFilters();saveFilters();toast('1.8 추천 기준으로 돌아왔습니다. 구독자 제한 없이 영화·드라마 게이트 후보 중 조회수 10만 이상을 우선 봅니다.');};
$('#broad-filters').onclick=()=>{filters=C.broadFilters();saveFilters();toast('전체 후보 보기로 전환했습니다. 수집된 후보를 진단할 때 쓰며, 다음 수집 설정은 바뀌지 않습니다.');};
function start(){loadState();loadFilters();loadCollectionPrefs();render();refresh(false);void updateBackupLocation();}
$('#consent').onclick=()=>{try{localStorage.setItem(consentKey,'yes');}catch{}$('#consent-dialog').close();start();};
let consent=false;try{consent=localStorage.getItem(consentKey)==='yes';}catch{}if(consent)start();else $('#consent-dialog').showModal();
window.addEventListener('storage',e=>{if(e.key===key){try{state=e.newValue?C.normalize(JSON.parse(e.newValue)):C.blank();render();}catch{warn('다른 탭의 변경을 불러오지 못했습니다.');}}});
