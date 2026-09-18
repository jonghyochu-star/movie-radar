'use strict';
const C=MovieCore, $=s=>document.querySelector(s);
const prefix='movie-radar:v1:'+location.pathname.replace(/index\.html$/,'');
const key=prefix+':records', consentKey=prefix+':consent';
let storageBlocked=false;
const filterKey=prefix+':filters-v1.2';
let filters=C.defaultFilters();
let state=C.blank(), dataset={mode:'demo',videos:[],generatedAt:null,warnings:[]};
let tab='discover', view='card', page=0, skipped=new Set(), undo=null, editedId=null, toastTimer;
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
   if(target==='review')return C.needsReview(v,r)&&!skipped.has(v.id);
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
 const sort=$('#sort').value;
 items.sort((a,b)=>{if(sort==='ratio')return (C.ratio(b)??-1)-(C.ratio(a)??-1)||(b.views??-1)-(a.views??-1);if(sort==='recent')return (Date.parse(b.publishedAt)||0)-(Date.parse(a.publishedAt)||0);if(sort==='saved')return (Date.parse(historyRecord(b).updatedAt)||0)-(Date.parse(historyRecord(a).updatedAt)||0);return (b.views??-1)-(a.views??-1);});
 if(exploring&&filters.mixDiscovery)return C.mixRoutes(items,filters.languages,filters.balance);
 return exploring&&filters.balance?C.balanceVideos(items,filters.languages):items;
}
function loadFilters(){
 try {const saved=localStorage.getItem(filterKey);if(saved)filters=C.normalizeFilters(JSON.parse(saved));}catch{filters=C.defaultFilters();}
 syncFilterControls();
}
function syncFilterControls(){
 $('#max-subs').value=String(filters.maxSubscribers);$('#content-filter').value=filters.content;
 $('#min-seconds').value=String(filters.minSeconds);$('#max-seconds').value=String(filters.maxSeconds);
 $('#min-views').value=String(filters.minViews);$('#balance').checked=filters.balance;
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
 const n=C.filterCounts(baseVideosForTab(),state.records,filters);
 $('#filter-summary').textContent=`이 탭의 미검토 ${n.total}개 → 영상 종류 ${n.content}개 → 구독자 ${n.subscribers}개 → 언어 ${n.language}개 → 길이 ${n.duration}개 → 조회수 ${n.views}개 → 수집 경로 ${n.route}개 → 쇼츠 조건 ${n.format}개. ${filters.mixDiscovery?'경로도 골고루 배치. ':''}${filters.balance?'언어·채널 균형 표시 중.':'선택한 정렬순 그대로 표시 중.'}`;
}
function evidencePanel(v,r){
 if(sample(v))return '';
 const kind=C.screenKind(v,r),labels={film:'영화 단서',series:'드라마·시리즈 단서',unknown:'영상 종류 미확인',non_screen:'비영화 의심',user_screen:'사용자가 확인한 작품'};
 const li=C.languageInfo(v), language=li.badge;
 const audioLabel=C.LANGUAGE_LABELS[li.audio]||'언어 미확인',declaredLabel=C.LANGUAGE_LABELS[li.declared]||'언어 미확인';
 const manual=C.mediaOf(r)==='not_screen'?'사용자 제외 · 영화/드라마 아님':labels[kind];
 return `<div class="evidence"><div class="evidence-chips"><span>${esc(manual)}</span><span>${esc(language)}</span></div><details><summary>필터 판단 근거</summary><p>${esc(v.screenReason||'이전 수집 데이터에 종류 단서가 없습니다. 1.3 live 수집 후 갱신됩니다.')}<br>${esc(li.basis)}<br>업로더 음성 설정: ${esc(audioLabel)}<br>제목·설명 언어 설정: ${esc(declaredLabel)} (음성 언어와 별개)<br>실제 음성·자막·원작 제작국·감동결을 검증한 결과가 아닙니다.</p></details></div>`;
}
function discoveryPanel(v,r){
 if(sample(v))return '';
 const f=C.shortsInfo(v,r),manual=C.formatOf(r);
 const badges=C.routesOf(v).map(x=>`<span>${esc(C.ROUTE_LABELS[x])}</span>`).join('');
 let buttons='';
 if(manual!=='shorts')buttons+='<button data-action="format_yes">쇼츠 맞음 · 확인</button>';
 if(manual!=='not_short')buttons+='<button data-action="format_no">일반 영상 제외</button>';
 if(manual!=='unknown')buttons+='<button data-action="format_reset">쇼츠 확인 취소</button>';
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
 summary.innerHTML=`<summary>이번 수집 경로 보기 · 검색 ${plans.length}개 / 출처 채널 ${channels.length}개</summary><ul>${lines}</ul><p>채널 업로드 ${scanned}건을 조회했습니다. 중복·길이·공개 조건을 거친 뒤 화면 필터를 적용합니다. 채널이 같다고 감동결이 같다고 판단하지 않습니다.</p><p>첨부 영상과 닮지 않은 새 소재도 찾습니다. 좋아요 기록에 따른 수집 자동 학습은 아직 연결되지 않았습니다.</p>`;
}
function originPanel(v,r){
 if(sample(v))return '';
 const origin=C.originOf(r);
 const labels={unknown:'원작 확인 필요',non_korean:'한국 외 원작 · 내가 확인함',korean:'한국 영화 · 추천에서 제외됨'};
 const hints={unknown:'제목·채널 국가·사용 언어만으로 원작 제작국을 판정하지 않았습니다.',non_korean:'사용자가 확인해 남긴 분류입니다. 자동 영화 인식 결과가 아닙니다.',korean:'좋아요·메모는 삭제하지 않았습니다. 이 영상은 평가 기록에서 다시 찾을 수 있습니다.'};
 let buttons='';
 if(origin!=='non_korean')buttons+='<button data-action="origin_foreign">한국 외 원작 확인</button>';
 if(origin!=='korean')buttons+='<button data-action="origin_korean">한국 영화 제외</button>';
 if(origin!=='unknown')buttons+='<button data-action="origin_reset">원작 확인 취소</button>';
 return `<div class="origin-box ${origin}"><strong>${labels[origin]}</strong><p>${hints[origin]}</p><div class="origin-actions">${buttons}</div></div>`;
}
function renderCard(v){const r=historyRecord(v), ratio=C.ratio(v), duration=typeof v.durationSeconds==='number'?`${Math.floor(v.durationSeconds/60)}:${String(v.durationSeconds%60).padStart(2,'0')}`:'길이 미확인';
 let thumb=sample(v)?'<div class="demo-art"><b>◇</b><span>SAMPLE · 실제 영상 아님</span></div>':'<span>미리보기 없음 · 원본에서 확인</span>';
 if(v.thumbnail && /^https:\/\/(?:i\.ytimg\.com|img\.youtube\.com)\//.test(v.thumbnail))thumb=`<img src="${esc(v.thumbnail)}" alt="${esc(v.title)}" loading="lazy">`;
 const labels=[r.rating==='like'?'좋아요':r.rating==='dislike'?'별로':null,r.stage==='candidate'?'제작 후보':r.stage==='done'?'제작 완료':null].filter(Boolean).join(' · ');
 let buttons=sample(v)?'<button disabled>샘플 · 원본 없음</button>':`<a class="open-link" href="https://www.youtube.com/watch?v=${encodeURIComponent(v.id)}" target="_blank" rel="noopener noreferrer">YouTube 원본 열기 ↗</a>`;
 if(tab==='discover'||tab==='review')buttons+='<button class="like" data-action="like">♡ 좋아요 저장</button><button data-action="dislike">별로</button><button data-action="later">나중에</button>';
 else if(C.originOf(r)!=='korean'&&C.mediaOf(r)!=='not_screen'&&C.formatOf(r)!=='not_short'){if(r.stage!=='candidate'&&r.stage!=='done'&&C.ready(v,r))buttons+='<button class="primary" data-action="candidate">제작 후보로</button>';if(r.stage==='candidate')buttons+='<button class="primary" data-action="done">제작 완료</button><button data-action="uncandidate">후보 해제</button>';if(r.stage==='done'&&C.ready(v,r))buttons+='<button data-action="reopen">후보로 되돌리기</button>';if(r.rating!=='like')buttons+='<button class="like" data-action="like">좋아요 저장</button>';}
 const media=C.mediaOf(r);
 const sub=[];
 if(!sample(v)){
   if(media!=='not_screen')sub.push('<button data-action="media_no">영화·드라마 아님</button>');
   if(media!=='screen')sub.push('<button data-action="media_yes">영화·드라마 맞음</button>');
   if(media!=='unknown')sub.push('<button data-action="media_reset">종류 확인 취소</button>');
 }
 sub.push('<button data-action="memo">메모</button>');if(r.rating)sub.push('<button data-action="unrate">평가 취소</button>');if(r.stage!=='done')sub.push('<button data-action="done">이미 제작함</button>');
 return `<article class="card" data-id="${esc(v.id)}"><div class="thumb ${v.thumbnail?'':'empty'}">${thumb}</div><div class="body"><div class="meta"><span>${esc(v.channelTitle||'채널 미확인')}${labels?' · '+esc(labels):''}</span><span>${esc(duration)}</span></div><h4>${esc(v.title||'저장된 YouTube 링크')}</h4><div class="stats"><div><span>조회수</span><strong title="${esc(fmt(v.views))}">${short(v.views)}</strong></div><div><span>공개 구독자 수</span><strong title="${esc(fmt(v.subscribers))}">${short(v.subscribers)}</strong></div><div><span>조회 ÷ 구독</span><strong title="현재 조회수 ÷ 공개 구독자 수. 공개 구독자 수의 내림·미확인의 영향이 있으며 성공 점수가 아닙니다.">${ratio===null?'—':'약 '+ratio.toLocaleString('ko-KR',{maximumFractionDigits:1})+'배'}</strong></div></div><p class="reason">${sample(v)?'기능 확인용 가상 데이터입니다.':esc(v.source||'YouTube 공개 API 데이터')}<br>게시 ${dt(v.publishedAt)} · 수집 ${dt(v.fetchedAt)}</p>${discoveryPanel(v,r)}${evidencePanel(v,r)}${originPanel(v,r)}${r.label?`<div class="mynote"><strong>내 제목</strong> ${esc(r.label)}</div>`:''}${r.memo?`<div class="mynote">${esc(r.memo)}</div>`:''}<div class="buttons">${buttons}</div><div class="subbuttons">${sub.join('')}</div></div></article>`;
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
 $('#section-title').textContent={discover:'원작을 확인한 미평가 소재',review:'조회수를 비교하고, 한국 외 원작인지 확인하세요',likes:'마음에 남은 장면을 다시 고르세요',candidate:'이제 제작할 이야기',done:'제작을 마친 소재',history:'원작 확인·한국 영화 제외·평가 기록'}[tab];
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
 $('#views-label').hidden=!exploring;$('#revisit').hidden=!exploring||skipped.size===0;
}
function snapshot(){undo={state:JSON.parse(JSON.stringify(state)),skipped:new Set(skipped)};}
function handleAction(id,action){const v=allVideos().find(x=>x.id===id);if(!v)return;if(action==='memo'){editedId=id;$('#edit-label').value=historyRecord(v).label||'';$('#edit-memo').value=historyRecord(v).memo||'';$('#edit-dialog').showModal();return;}snapshot();if(action==='later'){skipped.add(id);render();toast('이번 탐색에서만 넘겼습니다. 취향 평가에는 쓰지 않습니다.',true);return;}if(['format_yes','format_no'].includes(action)&&!confirm(action==='format_yes'?'YouTube 원본에서 Shorts임을 확인하셨나요? 길이·태그만으로 판단하지 마세요.':'일반 영상으로 제외할까요? 좋아요·메모는 남기고 추천·보관함·후보에서 숨깁니다. 평가 기록에서 취소할 수 있습니다.'))return;if(action==='media_no'&&!confirm('영화·드라마 장면이 아닌 자료로 표시할까요? 추천·보관함·후보에서 숨기고 기존 메모·평가는 평가 기록에 남깁니다.'))return;if(['origin_foreign','origin_korean'].includes(action)&&!confirm(action==='origin_foreign'?'원작을 확인했고, 한국 영화가 아닌 작품이 맞나요? 영상 언어·채널 국가만으로 판단하지 마세요.':'원작이 한국 영화임을 확인했나요? 이 영상만 추천·보관함·제작 후보에서 숨기며, 메모와 기존 기록은 보존합니다.'))return;try{state=C.apply(state,v,action);}catch(error){toast(error.message);return;}const ok=persist();render();if(ok)toast({format_yes:'쇼츠로 확인했습니다. 원작과 감동결은 별도입니다.',format_no:'일반 영상으로 제외했습니다. 취향 평가는 바꾸지 않았습니다.',format_reset:'쇼츠 확인을 취소했습니다.',like:'좋아요 보관함에 저장했습니다.',dislike:'별로로 기록했습니다.',candidate:'제작 후보에 넣었습니다.',uncandidate:'후보만 해제했습니다. 좋아요는 유지됩니다.',done:'제작 완료로 기록했습니다.',reopen:'제작 후보로 되돌렸습니다.',unrate:'취향 평가를 취소했습니다.',origin_foreign:'한국 외 원작으로 기록했습니다. 소재 탐색에서 검토할 수 있습니다.',origin_korean:'한국 영화로 제외했습니다. 평가 기록에서 되돌릴 수 있습니다.',origin_reset:'원작 확인을 취소했습니다. 확인 필요 탭으로 분리합니다.',media_no:'영화·드라마가 아닌 영상으로 제외했습니다. 평가 기록에서 취소할 수 있습니다.',media_yes:'영화·드라마로 확인했습니다. 원작 제작국은 별도로 확인하세요.',media_reset:'영상 종류 확인을 취소했습니다. 원래 필터를 적용합니다.'}[action],true);}
async function refresh(){const button=$('#refresh');button.disabled=true;try{const response=await fetch('data/videos.json?t='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error(`목록 파일을 읽지 못했습니다 (${response.status}).`);const data=await response.json();if(!Array.isArray(data.videos)||!['live','demo'].includes(data.mode))throw Error('목록 파일 형식이 잘못되었습니다.');dataset=data;
 const stale=data.mode==='live'&&(!Number.isFinite(Date.parse(data.generatedAt))||Date.now()-Date.parse(data.generatedAt)>C.MAX_AGE);if(stale){dataset={...data,videos:[]};warn('수집 정보가 29일을 넘겨 표시하지 않습니다. GitHub Actions에서 live로 다시 수집해 주세요.');}else{$('#notice').classList.remove('error');$('#notice').textContent=data.mode==='demo'?'샘플 모드입니다. 제목·조회수는 기능 확인용 가상 데이터이며 실제 영상이 아닙니다. API 키를 등록하고 live로 실행하면 실제 목록으로 바뀝니다.':(data.warnings||[]).length?'수집 안내: '+data.warnings.join(' / '):'1.3 · 참고 채널·관계 이야기·다른 감동·새 소재를 함께 찾습니다. 발견 경로는 감동 판정이 아닙니다. 원작·쇼츠 여부는 별도 확인하며, 자동 취향 학습은 아직 연결하지 않았습니다.';}
 if(data.mode==='live'&&data.collectorVersion!=='1.3')warn('앱은 1.3이지만 수집 데이터는 이전 버전입니다. Actions에서 새 main / live 실행이 필요합니다.');
 for(const v of dataset.videos){if(state.records[v.id]&&v.fetchedAt)state.records[v.id].cache=v;}state=C.normalize(state);persist();$('#mode').textContent=data.mode==='live'?'YouTube 연결':'SAMPLE';$('#mode').classList.toggle('live',data.mode==='live');$('#updated').textContent=`목록 갱신: ${data.generatedAt?new Date(data.generatedAt).toLocaleString('ko-KR'):'샘플 초기 파일'} · 배포 수집량 ${data.videos.length}개`;if(data.mode==='live'&&tab==='discover'&&!dataset.videos.some(v=>C.ready(v,historyRecord(v))&&!historyRecord(v).rating&&!historyRecord(v).stage)&&allVideos().some(v=>C.needsReview(v,historyRecord(v))))tab='review';page=0;render();
 }catch(error){warn(error.message+' 보관함은 계속 사용할 수 있습니다.');render();}finally{button.disabled=false;}}
$('#tabs').onclick=e=>{const b=e.target.closest('[data-tab]');if(!b)return;tab=b.dataset.tab;page=0;$('#search').value='';$('#sort').value=['discover','review'].includes(tab)?'views':'saved';render();};$('#content').onclick=e=>{const b=e.target.closest('[data-action]');if(b)handleAction(b.closest('[data-id]').dataset.id,b.dataset.action);};
$('#layout').onclick=()=>{view=view==='card'?'grid':'card';page=0;render();};$('#next').onclick=()=>{page++;render();};$('#previous').onclick=()=>{page--;render();};$('#revisit').onclick=()=>{skipped.clear();page=0;render();};for(const id of ['#search','#sort'])$(id).addEventListener(id==='#search'?'input':'change',()=>{page=0;render();});$('#refresh').onclick=refresh;
$('#edit-form').onsubmit=e=>{e.preventDefault();snapshot();const v=allVideos().find(x=>x.id===editedId),r=state.records[editedId]||C.record(editedId);r.label=$('#edit-label').value.trim();r.memo=$('#edit-memo').value.trim();r.updatedAt=new Date().toISOString();if(v?.fetchedAt)r.cache=v;state.records[editedId]=r;const ok=persist();$('#edit-dialog').close();render();if(ok)toast('메모를 저장했습니다.',true);};$('#edit-cancel').onclick=()=>$('#edit-dialog').close();
$('#add-link').onclick=()=>$('#link-dialog').showModal();$('#link-cancel').onclick=()=>$('#link-dialog').close();$('#link-form').onsubmit=e=>{e.preventDefault();try{const id=C.parseLink($('#link-url').value);snapshot();state=C.apply(state,{id},'like');const label=$('#link-label').value.trim();if(label)state.records[id].label=label;const ok=persist();$('#link-dialog').close();$('#link-form').reset();tab='likes';page=0;render();if(ok)toast('링크를 보관함에 저장했습니다.',true);}catch(error){toast(error.message);}};
$('#backup').onclick=()=>{const data={...C.exportData(state),exportedAt:new Date().toISOString()},blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='movie-radar-backup-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);toast('사용자 기록만 백업합니다. API 수치·제목 사본은 포함하지 않습니다.');};
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
$('#preferred-languages').onclick=()=>{filters.languages=C.preferredLanguages();filters.includeUnknownLanguage=false;saveFilters();};
$('#all-languages').onclick=()=>{filters.languages=Object.keys(C.LANGUAGE_LABELS).filter(x=>x!=='unknown');filters.includeUnknownLanguage=true;saveFilters();};
$('#reset-filters').onclick=()=>{filters=C.defaultFilters();saveFilters();toast('구독자 1만 이하·10만 조회 이상·3분 이하·우선 언어·영화/드라마 단서로 돌아왔습니다.');};
function start(){loadState();loadFilters();render();refresh();}
$('#consent').onclick=()=>{try{localStorage.setItem(consentKey,'yes');}catch{}$('#consent-dialog').close();start();};
let consent=false;try{consent=localStorage.getItem(consentKey)==='yes';}catch{}if(consent)start();else $('#consent-dialog').showModal();
window.addEventListener('storage',e=>{if(e.key===key){try{state=e.newValue?C.normalize(JSON.parse(e.newValue)):C.blank();render();}catch{warn('다른 탭의 변경을 불러오지 못했습니다.');}}});
