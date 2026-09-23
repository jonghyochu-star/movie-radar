const test=require('node:test');const assert=require('node:assert/strict');const C=require('../site/core.js');
const v={id:'AbCdEfGhI01',title:'test',views:1000,subscribers:100,fetchedAt:new Date().toISOString()};
test('like then candidate keeps like',()=>{let s=C.apply(C.apply(C.blank(),v,'origin_foreign'),v,'like');s=C.apply(s,v,'candidate');assert.equal(s.records[v.id].rating,'like');assert.equal(s.records[v.id].stage,'candidate');});
test('candidate removal not dislike',()=>{let s=C.apply(C.apply(C.apply(C.blank(),v,'origin_foreign'),v,'like'),v,'candidate');s=C.apply(s,v,'uncandidate');assert.equal(s.records[v.id].rating,'like');assert.equal(s.records[v.id].stage,null);});
test('done from discovery neutral rating',()=>{const s=C.apply(C.blank(),v,'done');assert.equal(s.records[v.id].rating,null);assert.equal(s.records[v.id].stage,'done');});
test('unrate clears active candidate because candidate implies tone match',()=>{let s=C.apply(C.apply(C.apply(C.blank(),v,'origin_foreign'),v,'like'),v,'candidate');s=C.apply(s,v,'unrate');assert.equal(s.records[v.id].rating,null);assert.equal(s.records[v.id].stage,null);});
test('state input remains immutable',()=>{const s=C.blank();C.apply(s,v,'like');assert.equal(Object.keys(s.records).length,0);});
test('ratio unknown and zero',()=>{assert.equal(C.ratio(v),10);assert.equal(C.ratio({...v,subscribers:0}),null);assert.equal(C.ratio({...v,subscribers:null}),null);});
test('backup removes API metadata',()=>{const b=C.exportData(C.apply(C.blank(),v,'like'));assert.equal(b.records[v.id].cache,undefined);assert.equal(b.records[v.id].rating,'like');});
test('expired metadata removed, notes retained',()=>{let s=C.apply(C.blank(),{...v,fetchedAt:'2020-01-01T00:00:00Z'},'like');s.records[v.id].memo='keep';s=C.normalize(s);assert.equal(s.records[v.id].cache,null);assert.equal(s.records[v.id].memo,'keep');});
test('bad schema rejected',()=>assert.throws(()=>C.normalize({schema:9,records:{}})));
test('merge newer wins',()=>{let a=C.apply(C.blank(),v,'like','2026-09-01T00:00:00Z'),b=C.apply(C.blank(),v,'dislike','2026-09-02T00:00:00Z');assert.equal(C.merge(a,b).records[v.id].rating,'dislike');});
test('YouTube links parsed',()=>{assert.equal(C.parseLink('https://youtu.be/AbCdEfGhI01?t=1'),v.id);assert.equal(C.parseLink('https://www.youtube.com/shorts/AbCdEfGhI01'),v.id);assert.equal(C.parseLink('https://www.youtube.com/watch?v=AbCdEfGhI01'),v.id);});
test('unsafe links rejected',()=>{for(const x of ['javascript:alert(1)','https://youtube.com.evil.com/watch?v=AbCdEfGhI01','http://youtu.be/AbCdEfGhI01'])assert.throws(()=>C.parseLink(x));});

test('unknown metadata never determines origin but no longer blocks evaluation',()=>{assert.equal(C.originOf({}), 'unknown');assert.equal(C.ready({...v,title:'Korean film',country:'US'},{}),true);});
test('candidate can be chosen immediately and implies tone match',()=>{const s=C.apply(C.blank(),v,'candidate');assert.equal(s.records[v.id].stage,'candidate');assert.equal(s.records[v.id].rating,'like');});
test('legacy record migration preserves rating, stage, memo',()=>{const old={schema:1,records:{[v.id]:{id:v.id,rating:'like',stage:'candidate',memo:'keep me'}}};const r=C.normalize(old).records[v.id];assert.equal(r.rating,'like');assert.equal(r.stage,'candidate');assert.equal(r.memo,'keep me');assert.equal(r.origin,'unknown');});
test('Korean exclusion preserves preference and notes',()=>{let s=C.apply(C.apply(C.apply(C.blank(),v,'origin_foreign'),v,'like'),v,'candidate');s.records[v.id].memo='unchanged';s=C.apply(s,v,'origin_korean');const r=s.records[v.id];assert.equal(r.rating,'like');assert.equal(r.stage,'candidate');assert.equal(r.memo,'unchanged');assert.equal(C.originOf(r),'korean');assert.equal(C.ready(v,r),false);assert.equal(C.needsReview(v,r),false);});
test('origin reset sends item to unknown review',()=>{let s=C.apply(C.blank(),v,'origin_foreign');s=C.apply(s,v,'origin_reset');assert.equal(C.needsReview(v,s.records[v.id]),true);});
test('origin review included in metadata-free backup',()=>{const s=C.apply(C.blank(),v,'origin_korean');const backup=C.exportData(s);assert.equal(backup.records[v.id].origin,'korean');assert.equal(backup.records[v.id].cache,undefined);assert.equal(C.normalize(backup).records[v.id].origin,'korean');});
test('origin decisions for one video do not label other clips',()=>{const s=C.apply(C.blank(),v,'origin_korean');const another={...v,id:'AbCdEfGhI02',title:'same film'};assert.equal(C.originOf(s.records[another.id]),'unknown');});
test('samples can test candidate behavior without a real country decision',()=>{const demo={id:'demo-1'};const s=C.apply(C.apply(C.blank(),demo,'like'),demo,'candidate');assert.equal(s.records[demo.id].stage,'candidate');});
test('rated and staged items do not clog pending review',()=>{assert.equal(C.needsReview(v,{rating:'dislike'}),false);assert.equal(C.needsReview(v,{rating:'like'}),false);assert.equal(C.needsReview(v,{stage:'done'}),false);assert.equal(C.needsReview(v,{stage:'candidate'}),false);});

const fvideo={...v,durationSeconds:90,language:'en',languageSource:'title',languageBasis:'제목 문장 단서 · 추정, 음성 미확인',screenKind:'film',views:100000,subscribers:5000};
const defaults=()=>C.defaultFilters();
test('default subscribers are unrestricted in 1.7',()=>assert.equal(defaults().maxSubscribers,0));
test('5000 subscriber boundary inclusive',()=>{const f={...defaults(),maxSubscribers:5000};assert(C.matchesFilters(fvideo,{},f));assert(!C.matchesFilters({...fvideo,subscribers:5001},{},f));});
test('10000 subscriber boundary inclusive',()=>{const f={...defaults(),maxSubscribers:10000};assert(C.matchesFilters({...fvideo,subscribers:10000},{},f));assert(!C.matchesFilters({...fvideo,subscribers:10001},{},f));});
test('unknown subscriber only rejected when cap is active',()=>{const f={...defaults(),maxSubscribers:10000};for(const sub of [null,undefined,NaN,'4000'])assert(!C.matchesFilters({...fvideo,subscribers:sub},{},f));});
test('unknown subscriber allowed only without cap',()=>assert(C.matchesFilters({...fvideo,subscribers:null},{},{...defaults(),maxSubscribers:0})));
test('zero subscribers valid but no ratio',()=>{assert(C.matchesFilters({...fvideo,subscribers:0},{},defaults()));assert.equal(C.ratio({...fvideo,subscribers:0}),null);});
test('duration range inclusive and editable',()=>{const f={...defaults(),minSeconds:30,maxSeconds:90};for(const d of [30,90])assert(C.matchesFilters({...fvideo,durationSeconds:d},{},f));for(const d of [29,91,null])assert(!C.matchesFilters({...fvideo,durationSeconds:d},{},f));});
test('minimum view boundary',()=>{const f={...defaults(),minViews:100000};assert(C.matchesFilters({...fvideo,views:100000},{},f));assert(!C.matchesFilters({...fvideo,views:99999},{},f));});
test('default languages remain multilingual',()=>{assert(C.matchesFilters({...fvideo,language:'es'},{},defaults()));assert(C.matchesFilters({...fvideo,language:'ja'},{},defaults()));});
test('Hindi Arabic not shown by default including scripts',()=>{for(const lang of ['hi','ar','ar-script','indic-script'])assert(!C.matchesFilters({...fvideo,language:lang},{},defaults()));});
test('explicitly enabling languages works',()=>{const f={...defaults(),languages:['ar','hi']};assert(C.matchesFilters({...fvideo,language:'ar'},{},f));assert(C.matchesFilters({...fvideo,language:'hi'},{},f));});
test('unknown language can still be hidden explicitly',()=>{assert(C.matchesFilters({...fvideo,language:'unknown'},{},defaults()));assert(!C.matchesFilters({...fvideo,language:'unknown'},{},{...defaults(),includeUnknownLanguage:false}));});
test('selecting no languages gives zero not all',()=>assert(!C.matchesFilters(fvideo,{},{...defaults(),languages:[]})));
test('recommended defaults require movie-tv collection gate',()=>{assert(C.matchesFilters({...fvideo,screenKind:'unknown',screenGate:['movie']},{},defaults()));assert(!C.matchesFilters({...fvideo,screenKind:'unknown',screenGate:[]},{},defaults()));assert(!C.matchesFilters({...fvideo,screenKind:'non_screen',screenGate:['movie']},{},defaults()));});
test('series included by default separate movie only',()=>{assert(C.matchesFilters({...fvideo,screenKind:'series'},{},defaults()));assert(!C.matchesFilters({...fvideo,screenKind:'series'},{},{...defaults(),content:'film'}));});
test('recommended defaults include unknown language',()=>assert(C.matchesFilters({...fvideo,language:'unknown'},{},defaults())));
test('broad filters remove display gates',()=>{const f=C.broadFilters();assert.equal(f.maxSubscribers,0);assert.equal(f.minViews,0);assert.equal(f.content,'all');assert.equal(f.minSeconds,0);assert.equal(f.maxSeconds,180);assert.equal(f.includeUnknownLanguage,true);});
test('show all content allows manual review',()=>assert(C.matchesFilters({...fvideo,screenKind:'unknown'},{},{...defaults(),content:'all'})));
test('manual movie confirmation overrides weak metadata',()=>assert(C.matchesFilters({...fvideo,screenKind:'unknown'},{media:'screen'},defaults())));
test('manual nonfilm mark is separate from taste and origin',()=>{let s=C.apply(C.apply(C.blank(),v,'origin_foreign'),v,'like');s.records[v.id].memo='keep';s=C.apply(s,v,'media_no');const r=s.records[v.id];assert.equal(r.rating,'like');assert.equal(r.memo,'keep');assert.equal(r.origin,'non_korean');assert(!C.ready(v,r));assert(!C.needsReview(v,r));assert.throws(()=>C.apply(s,v,'candidate'));});
test('manual nonfilm reset restores eligibility without taste mutation',()=>{let s=C.apply(C.apply(C.blank(),v,'origin_foreign'),v,'media_no');s=C.apply(s,v,'media_reset');assert(C.ready(v,s.records[v.id]));assert.equal(s.records[v.id].rating,null);});
test('media confirmation does not confirm original country and country confirmation is no longer required',()=>{const s=C.apply(C.blank(),v,'media_yes');assert.equal(s.records[v.id].origin,'unknown');assert(C.ready(v,s.records[v.id]));});
test('v11 migrations preserve candidates notes',()=>{const r={schema:1,records:{[v.id]:{rating:'like',origin:'non_korean',stage:'candidate',memo:'keep'}}};const x=C.normalize(r).records[v.id];assert.equal(x.media,'unknown');assert.equal(x.stage,'candidate');assert.equal(x.memo,'keep');assert(C.ready(v,x));});
test('backup includes media no metadata',()=>{const data=C.exportData(C.apply(C.blank(),v,'media_no'));assert.equal(data.records[v.id].media,'not_screen');assert.equal(data.records[v.id].cache,undefined);});
test('filter preferences sanitize',()=>{const f=C.normalizeFilters({maxSubscribers:NaN,minSeconds:180,maxSeconds:10,languages:['xx','en','en','__proto__'],balance:'yes'});assert.equal(f.maxSubscribers,0);assert.equal(f.minSeconds,0);assert.equal(f.maxSeconds,180);assert.deepEqual(f.languages,['en']);assert.equal(f.balance,true);});
test('funnel shows which restriction causes zero',()=>{const items=[fvideo,{...fvideo,id:'AbCdEfGhI02',subscribers:20000},{...fvideo,id:'AbCdEfGhI03',language:'hi'},{...fvideo,id:'AbCdEfGhI04',screenKind:'unknown'}];const n=C.filterCounts(items,{},defaults());assert.deepEqual(n,{total:4,content:3,audience:3,subscribers:3,language:2,duration:2,views:2,route:2,format:2});});
test('language balancing interleaves, does not lose or duplicate',()=>{const items=[{id:'1',language:'en',languageSource:'title',channelId:'a'},{id:'2',language:'en',languageSource:'title',channelId:'a'},{id:'3',language:'en',languageSource:'title',channelId:'b'},{id:'4',language:'ja',languageSource:'title',channelId:'c'},{id:'5',language:'ja',languageSource:'title',channelId:'c'}];const result=C.balanceVideos(items,['en','ja']);assert.deepEqual(result.map(v=>v.id),['1','4','3','5','2']);assert.equal(new Set(result.map(v=>v.id)).size,items.length);});
test('language balancing handles empty, unknown, missing channel',()=>{assert.deepEqual(C.balanceVideos([]),[]);const items=[{id:'1'},{id:'2',language:'ar'}];assert.equal(C.balanceVideos(items).length,2);});
test('display filters do not mutate records',()=>{const s=C.apply(C.blank(),v,'like');const before=JSON.stringify(s);C.matchesFilters(fvideo,s.records[v.id],defaults());C.filterCounts([fvideo],s.records,defaults());assert.equal(JSON.stringify(s),before);});

test('movie-only does not turn confirmed TV into film',()=>{assert(!C.matchesFilters({...fvideo,screenKind:'series'},{origin:'non_korean'}, {...defaults(),content:'film'}));});

// Regression: defaultLanguage describes metadata, not verified speech.
test('legacy uploader English alone is unknown',()=>{const x=C.languageInfo({language:'en',languageBasis:'업로더의 제목·설명 언어 설정',audioLanguage:'unknown'});assert.equal(x.code,'unknown');assert.equal(x.declared,'en');assert.equal(x.badge,'언어 미확인');});
test('untyped legacy English stays unknown but recommended view can include unknown',()=>{const x={...fvideo,languageSource:undefined,languageBasis:'업로더의 제목·설명 언어 설정',audioLanguage:'unknown'};assert.equal(C.languageInfo(x).code,'unknown');assert(C.matchesFilters(x,{},defaults()));assert(!C.matchesFilters(x,{},{...defaults(),includeUnknownLanguage:false}));});
test('audio Hindi overrides English title setting in legacy data',()=>{const x={...fvideo,languageSource:undefined,language:'en',languageBasis:'업로더의 제목·설명 언어 설정',audioLanguage:'hi'};assert.equal(C.languageInfo(x).code,'hi');assert(!C.matchesFilters(x,{},defaults()));assert(C.matchesFilters(x,{},{...defaults(),languages:['hi']}));});
test('audio English overrides Japanese title estimate',()=>{const x={...fvideo,language:'ja',audioLanguage:'en'};assert.equal(C.languageInfo(x).code,'en');assert.equal(C.languageInfo(x).badge,'영어 · 음성 설정');});
test('typed title estimate is labelled as estimate',()=>{const x=C.languageInfo({language:'es',languageSource:'title',audioLanguage:'unknown',declaredLanguage:'en'});assert.equal(x.code,'es');assert.equal(x.badge,'스페인어 · 제목 추정');assert.equal(x.declared,'en');});
test('new unknown stays unknown even if declared English',()=>{const x=C.languageInfo({language:'unknown',languageSource:'unknown',declaredLanguage:'en',audioLanguage:'unknown'});assert.equal(x.code,'unknown');assert.equal(x.declared,'en');});
test('old weak title rule not trusted after patch',()=>{assert.equal(C.languageInfo({language:'en',languageBasis:'제목 단어 규칙 · 추정',audioLanguage:'unknown'}).code,'unknown');});
test('malformed language strings fail closed',()=>{for(const x of ['__proto__','<script>','constructor',null])assert.equal(C.languageInfo({language:x,audioLanguage:x,declaredLanguage:x,languageSource:'title'}).code,'unknown');});
test('language info does not mutate source metadata',()=>{const x={language:'en',languageBasis:'업로더의 제목·설명 언어 설정',audioLanguage:'hi'};const before=JSON.stringify(x);C.languageInfo(x);assert.equal(JSON.stringify(x),before);});
test('language filtering is independent of original-country preference',()=>{const x={...fvideo,languageSource:undefined,languageBasis:'업로더의 제목·설명 언어 설정',audioLanguage:'unknown'};assert(C.matchesFilters(x,{origin:'non_korean'},defaults()));assert(!C.matchesFilters(x,{origin:'non_korean'},{...defaults(),includeUnknownLanguage:false}));assert.equal(C.originOf({}),'unknown');});
test('language rebalance groups by effective audio language',()=>{const items=[{id:'1',language:'en',audioLanguage:'hi',channelId:'a'},{id:'2',language:'en',audioLanguage:'en',channelId:'b'},{id:'3',language:'en',audioLanguage:'hi',channelId:'a'}];assert.deepEqual(C.balanceVideos(items,['en','hi']).map(x=>x.id),['2','1','3']);});
test('preferences keep user 65sec and subscriber limit through migration',()=>{const f=C.normalizeFilters({maxSubscribers:5000,minSeconds:65,maxSeconds:180,languages:['en','ja'],includeUnknownLanguage:false});assert.equal(f.minSeconds,65);assert.equal(f.maxSubscribers,5000);assert.deepEqual(f.languages,['en','ja']);});

test('format status is not a taste rating',()=>{let s=C.apply(C.apply(C.blank(),v,'like'),v,'format_no');assert.equal(s.records[v.id].rating,'like');assert.equal(C.formatOf(s.records[v.id]),'not_short');assert(!C.needsReview(v,s.records[v.id]));assert(!C.ready(v,s.records[v.id]));});
test('format exclusion preserves production state for restoration',()=>{let s=C.apply(C.apply(C.blank(),v,'origin_foreign'),v,'candidate');s.records[v.id].memo='Keep';s=C.apply(s,v,'format_no');assert.equal(s.records[v.id].stage,'candidate');assert.equal(s.records[v.id].memo,'Keep');assert.throws(()=>C.apply(s,v,'candidate'));s=C.apply(s,v,'format_reset');assert(C.ready(v,s.records[v.id]));});
test('short hashtag never proves shorts',()=>{assert.equal(C.shortsInfo({shortsHint:true},{}).status,'hint');assert.equal(C.shortsInfo({durationSeconds:30},{}).status,'unknown');});
test('shorts-only mode keeps explicit user confirmations',()=>{const f={...defaults(),shorts:'confirmed'};assert(!C.matchesFilters({...fvideo,shortsHint:true},{},f));assert(C.matchesFilters(fvideo,{format:'shorts'},f));assert.equal(C.originOf({format:'shorts'}),'unknown');});
test('hinted mode hides unknown but never confirms',()=>{const f={...defaults(),shorts:'hinted'};assert(C.matchesFilters({...fvideo,shortsHint:true},{},f));assert(!C.matchesFilters(fvideo,{},f));});
test('ordinary video never passes discovery',()=>{assert(!C.matchesFilters(fvideo,{format:'not_short'},defaults()));});
test('old records migrate without losing saved work',()=>{const x=C.normalize({schema:1,records:{[v.id]:{rating:'like',stage:'candidate',origin:'non_korean',memo:'keep'}}}).records[v.id];assert.equal(x.format,'unknown');assert.equal(x.stage,'candidate');assert.equal(x.memo,'keep');});
test('format status included in user backup without API cache',()=>{const s=C.apply(C.blank(),v,'format_yes');const r=C.exportData(s).records[v.id];assert.equal(r.format,'shorts');assert(!Object.hasOwn(r,'cache'));});
test('route all does not enforce a theme',()=>{const f=defaults();assert(C.matchesFilters({...fvideo,discoveryRoutes:['open']},{},f));assert(C.matchesFilters({...fvideo,discoveryRoutes:['work']},{},f));});
test('route filtering is provenance only',()=>{const f={...defaults(),route:'open'};assert(C.matchesFilters({...fvideo,discoveryRoutes:['open']},{},f));assert(!C.matchesFilters({...fvideo,discoveryRoutes:['work']},{},f));});
test('route labels reject injected values',()=>{assert.deepEqual(C.routesOf({discoveryRoutes:['__proto__','<script>','open','open']}),['open']);});
test('mixing does not duplicate or lose candidates',()=>{const rows=[{id:'a',discoveryRoutes:['open','familiar']},{id:'b',discoveryRoutes:['work']},{id:'c',discoveryRoutes:['expand']},{id:'d',discoveryRoutes:['open']}];const out=C.mixRoutes(rows);assert.equal(out.length,4);assert.equal(new Set(out.map(x=>x.id)).size,4);});
test('shorts preferences do not replace previous numeric criteria',()=>{const f=C.normalizeFilters({maxSubscribers:5000,minSeconds:65,maxSeconds:180,languages:['es'],shorts:'hinted',mixDiscovery:false});assert.equal(f.maxSubscribers,5000);assert.equal(f.minSeconds,65);assert.equal(f.shorts,'hinted');assert.equal(f.mixDiscovery,false);assert.deepEqual(f.languages,['es']);});
test('batch feedback is stored without changing video ratings',()=>{let s=C.blank();s=C.recordBatchFeedback(s,'2026-09-19T00:00:00Z','no_harvest',1,'2026-09-19T01:00:00Z');assert.equal(s.batchFeedback.length,1);assert.equal(Object.keys(s.records).length,0);assert.equal(s.batchFeedback[0].retryRound,1);});
test('batch feedback survives export normalize',()=>{let s=C.recordBatchFeedback(C.blank(),'2026-09-19T00:00:00Z','no_harvest',2,'2026-09-19T01:00:00Z');const x=C.normalize(C.exportData(s));assert.equal(x.batchFeedback[0].outcome,'no_harvest');assert.equal(x.batchFeedback[0].retryRound,2);});


test('candidate tiers are evidence labels not scores',()=>{
 assert.equal(C.candidateTier({...fvideo,screenKind:'film',screenGate:['movie']},{}),'priority');
 assert.equal(C.candidateTier({...fvideo,screenKind:'series',screenGate:['tv']},{}),'priority');
 assert.equal(C.candidateTier({...fvideo,screenKind:'unknown'},{}),'review');
 assert.equal(C.candidateTier({...fvideo,screenKind:'non_screen'},{}),'low');
 assert.equal(C.candidateTier({...fvideo,screenKind:'unknown'},{media:'screen'}),'priority');
});
test('taste profile uses likes only and available context',()=>{
 const videos=[{...fvideo,id:'LikeVideo01',channelId:'chan-a',discoveryRoutes:['familiar']},{...fvideo,id:'BadVideo0001',channelId:'chan-b',discoveryRoutes:['open']}];
 let records={};records['LikeVideo01']={rating:'like'};records['BadVideo0001']={rating:'dislike'};
 const p=C.buildTasteProfile(videos,records);assert.equal(p.likedCount,1);assert.equal(p.usableLikes,1);assert.equal(p.channelCounts['chan-a'],1);assert.equal(p.channelCounts['chan-b'],undefined);assert.equal(p.routeCounts.familiar,1);
});
test('taste match can use channel or discovery route without filtering',()=>{
 const profile={channelCounts:{'chan-a':1},routeCounts:{expand:2}};
 assert(C.tasteMatch({...fvideo,channelId:'chan-a',discoveryRoutes:['open']},profile).matched);
 assert(C.tasteMatch({...fvideo,channelId:'other',discoveryRoutes:['expand']},profile).matched);
 assert(!C.tasteMatch({...fvideo,channelId:'other',discoveryRoutes:['open']},profile).matched);
});
test('priority grouping nudges order but keeps review candidates',()=>{
 const profile={channelCounts:{'chan-a':1},routeCounts:{familiar:1}};
 assert.equal(C.candidatePriorityGroup({...fvideo,channelId:'chan-a',screenKind:'film'}, {}, profile, true),0);
 assert.equal(C.candidatePriorityGroup({...fvideo,channelId:'x',screenKind:'film'}, {}, profile, true),4);
 assert.equal(C.candidatePriorityGroup({...fvideo,channelId:'x',screenKind:'unknown',discoveryRoutes:['familiar']}, {}, profile, true),3);
 assert.equal(C.candidatePriorityGroup({...fvideo,channelId:'x',screenKind:'unknown',discoveryRoutes:['open']}, {}, profile, true),5);
});
test('taste assist preference survives filter normalization and does not change filter eligibility',()=>{
 const a=C.normalizeFilters({tasteAssist:false}),b=C.normalizeFilters({tasteAssist:true});
 assert.equal(a.tasteAssist,false);assert.equal(b.tasteAssist,true);assert.equal(C.matchesFilters(fvideo,{},a),C.matchesFilters(fvideo,{},b));
});

test('screen gate explains movie and tv retrieval without claiming verification',()=>{
 assert.equal(C.screenGateInfo({...fvideo,screenGate:['movie']},{}).label,'영화 주제 검색');
 assert.equal(C.screenGateInfo({...fvideo,screenGate:['tv']},{}).label,'TV·드라마 주제 검색');
 assert.equal(C.screenGateInfo({...fvideo,screenKind:'unknown',screenGate:[]},{}).ok,false);
});


test('preference profile uses likes and explicit tone dislikes but excludes structural exclusions',()=>{
 const a={...fvideo,id:'LikeVideo01',channelId:'chan-a',discoveryRoutes:['familiar'],discoveryLabels:['관계 회복']};
 const b={...fvideo,id:'BadVideo0001',channelId:'chan-b',discoveryRoutes:['open'],discoveryLabels:['새 작품']};
 const c={...fvideo,id:'SkipVideo001',channelId:'chan-c',discoveryRoutes:['expand'],discoveryLabels:['존엄']};
 const records={LikeVideo01:{rating:'like'},BadVideo0001:{rating:'dislike',dislikeReason:'not_my_tone'},SkipVideo001:{rating:'like',format:'not_short'}};
 const p=C.buildTasteProfile([a,b,c],records);assert.equal(p.likedCount,1);assert.equal(p.dislikedCount,1);assert.equal(p.excludedFromTaste,1);assert.equal(p.liked.themes['관계 회복'],1);assert.equal(p.disliked.themes['새 작품'],1);
});
test('1.8 preference classes are explainable and dislikes do not delete candidates',()=>{
 const profile={liked:{channels:{a:2},routes:{familiar:2},themes:{'관계 회복':2}},disliked:{channels:{b:3},routes:{open:3},themes:{'새 작품':3}},usableLikes:2,usableDislikes:3};
 assert.equal(C.preferenceClass({...fvideo,channelId:'a',discoveryLabels:['관계 회복']},profile).bucket,'close');
 assert.equal(C.preferenceClass({...fvideo,channelId:'x',discoveryRoutes:['familiar']},profile).bucket,'adjacent');
 assert.equal(C.preferenceClass({...fvideo,channelId:'x',discoveryRoutes:['expand']},profile).bucket,'explore');
 assert.equal(C.preferenceClass({...fvideo,channelId:'b',discoveryLabels:['새 작품'],discoveryRoutes:['open']},profile).bucket,'low');
});
test('1.8 personalized blend keeps every candidate once',()=>{
 const profile={liked:{channels:{a:1},routes:{familiar:1},themes:{}},disliked:{channels:{d:1},routes:{open:1},themes:{}},usableLikes:3,usableDislikes:3};
 const items=[{id:'a1',channelId:'a'},{id:'a2',channelId:'a'},{id:'b1',discoveryRoutes:['familiar']},{id:'c1',discoveryRoutes:['expand']},{id:'d1',channelId:'d',discoveryRoutes:['open']}];
 const out=C.personalizedBlend(items,profile,true);assert.equal(out.length,items.length);assert.equal(new Set(out.map(x=>x.id)).size,items.length);assert.equal(out.at(-1).id,'d1');
});


test('1.8.2 dislike reasons migrate without inventing reasons',()=>{
 const old=C.normalize({schema:1,records:{[v.id]:{rating:'dislike'}}}).records[v.id];
 assert.equal(old.rating,'dislike');assert.equal(old.dislikeReason,null);
 let s=C.apply(C.blank(),v,'dislike_not_tone');assert.equal(s.records[v.id].dislikeReason,'not_my_tone');
 s=C.apply(s,v,'unrate');assert.equal(s.records[v.id].rating,null);assert.equal(s.records[v.id].dislikeReason,null);
});
test('1.9.1 only explicit tone dislikes teach negative taste',()=>{
 const a={...fvideo,id:'LikeVideo01',channelId:'a',discoveryRoutes:['familiar']};
 const b={...fvideo,id:'BadVideo0001',channelId:'b',discoveryRoutes:['open']};
 const c={...fvideo,id:'Overused0001',channelId:'c',discoveryRoutes:['expand']};
 const d={...fvideo,id:'LegacyBad001',channelId:'d',discoveryRoutes:['work']};
 const records={
  LikeVideo01:{rating:'like'},
  BadVideo0001:{rating:'dislike',dislikeReason:'not_my_tone'},
  Overused0001:{rating:'dislike',dislikeReason:'overused'},
  LegacyBad001:{rating:'dislike'}
 };
 const p=C.buildTasteProfile([a,b,c,d],records);
 assert.equal(p.likedCount,1);assert.equal(p.dislikedCount,3);assert.equal(p.usableDislikes,1);
 assert.equal(p.disliked.channels.b,1);assert.equal(p.disliked.channels.c,undefined);assert.equal(p.disliked.channels.d,undefined);
 assert.equal(p.dislikeReasonCounts.overused,1);assert.equal(p.untypedDislikes,1);
});


test('1.9 audience filter uses collector validation and never lifetime average',()=>{
 const strong={...fvideo,audience:{status:'strong',validated:true,surging:false,fastStrong:true,cumulativeProven:false,mega:false,ageHours:20,floorViews:500000,deltas:{},lifetimeAverageUsed:false}};
 const weak={...fvideo,id:'AbCdEfGhI09',audience:{status:'watch',validated:false,surging:false,fastStrong:false,cumulativeProven:false,mega:false,ageHours:20,floorViews:500000,deltas:{},lifetimeAverageUsed:false}};
 assert(C.matchesFilters(strong,{},defaults()));
 assert(!C.matchesFilters(weak,{},defaults()));
 assert(C.matchesFilters(weak,{},{...defaults(),audience:'all'}));
 assert.equal(C.audienceInfo(strong).lifetimeAverageUsed,false);
});
test('1.9 audience modes separate surging and cumulative proof',()=>{
 const surge={...fvideo,audience:{status:'surging',validated:true,surging:true,cumulativeProven:false,mega:false}};
 const proven={...fvideo,id:'AbCdEfGhI08',views:6000000,audience:{status:'proven',validated:true,surging:false,cumulativeProven:true,mega:false}};
 assert(C.matchesFilters(surge,{},{...defaults(),audience:'surging'}));
 assert(!C.matchesFilters(proven,{},{...defaults(),audience:'surging'}));
 assert(C.matchesFilters(proven,{},{...defaults(),audience:'proven'}));
});


test('1.9.1 migrates overused dislike into tone match plus freshness flag',()=>{
 const r=C.normalize({schema:1,records:{[v.id]:{rating:'dislike',dislikeReason:'overused'}}}).records[v.id];
 assert.equal(r.rating,'like');assert.equal(r.dislikeReason,null);assert.equal(r.freshness,'overused');
});
test('1.9.1 migrates weak-story dislike into tone match plus story flag',()=>{
 const r=C.normalize({schema:1,records:{[v.id]:{rating:'dislike',dislikeReason:'weak_story'}}}).records[v.id];
 assert.equal(r.rating,'like');assert.equal(r.story,'weak');
});
test('1.9.1 quality flags toggle without becoming tone dislikes',()=>{
 let s=C.apply(C.blank(),v,'like');s=C.apply(s,v,'toggle_overused');s=C.apply(s,v,'toggle_weak_story');
 const r=s.records[v.id];assert.equal(r.rating,'like');assert.equal(r.freshness,'overused');assert.equal(r.story,'weak');assert.equal(r.dislikeReason,null);
 s=C.apply(s,v,'toggle_overused');assert.equal(s.records[v.id].freshness,null);
});
test('1.9.1 Korean and non-screen exclusions still block production candidates',()=>{
 let s=C.apply(C.blank(),v,'origin_korean');assert.throws(()=>C.apply(s,v,'candidate'));
 s=C.apply(C.blank(),v,'media_no');assert.throws(()=>C.apply(s,v,'candidate'));
});
