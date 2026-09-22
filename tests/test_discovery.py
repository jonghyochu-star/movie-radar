"""Offline tests: synthetic YouTube responses; never use a real API key."""
import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('collect13',ROOT/'scripts/collect.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from discovery import select_profiles,validate_discovery,shorts_hint,diverse_snapshot,select_review_pool,source_category,parse_collection_plan,language_slots,SCREEN_TOPIC_IDS
CID='UC'+'r'*22; LARGE='UC'+'s'*22
VID='DemoVideo01';ALT='DemoVideo02';REF='bTL6azhffzA'

def make_video(vid,cid=CID,seconds='PT1M20S'):
    title='A father gives her a second chance after a difficult day #shorts' if vid==VID else 'A teacher protects a struggling student and gives him hope #shorts'
    return {'id':vid,'snippet':{'title':title,'description':'Movie scene: a fictional test, not a real work.','channelId':cid,'channelTitle':'Synthetic fixture','categoryId':'1','defaultAudioLanguage':'en','liveBroadcastContent':'none','publishedAt':'2026-09-01T00:00:00Z'},'contentDetails':{'duration':seconds},'statistics':{'viewCount':'750000'},'status':{'privacyStatus':'public'}}

class Fake:
    def __init__(self):self.calls=[]
    def get(self,endpoint,**p):
        self.calls.append((endpoint,p))
        if endpoint=='search':return {'items':[{'id':{'videoId':VID}},{'id':{'videoId':REF}}]}
        if endpoint=='videos' and p['part']=='snippet':return {'items':[{'id':REF,'snippet':{'channelId':LARGE}}]}
        if endpoint=='videos':return {'items':[make_video(x,LARGE if x==ALT else CID) for x in p['id'].split(',')]}
        if endpoint=='channels' and 'contentDetails' in p['part']:
            return {'items':[{'id':c,'snippet':{'title':'Reference source'},'contentDetails':{'relatedPlaylists':{'uploads':'UU'+c[2:]}}} for c in p['id'].split(',')]}
        if endpoint=='playlistItems':return {'items':[{'contentDetails':{'videoId':ALT}}],'nextPageToken':'page2'}
        if endpoint=='channels':return {'items':[{'id':c,'statistics':{'subscriberCount':'900000' if c==LARGE else '2500','hiddenSubscriberCount':False}} for c in p['id'].split(',')]}
        raise AssertionError(endpoint)

class DiscoveryTests(unittest.TestCase):
    def config(self):return m.load_config(ROOT/'config.json')
    def test_new_plan_is_loaded(self):self.assertTrue(self.config()['discovery']['enabled'])
    def test_each_run_preserves_open_lane(self):
        for r in range(100):
            rows=select_profiles(self.config(),r)
            self.assertEqual(len(rows),6)
            self.assertTrue({'familiar','expand','work','open'}.issubset({x['lane'] for x in rows}))
    def test_english_focus_is_four_english_two_rotating_others(self):
        others=set()
        for r in range(7):
            langs=[x['language'] for x in select_profiles(self.config(),r,'english_focus','',1)]
            self.assertEqual(langs.count('en'),4);self.assertEqual(len(langs),6)
            others.update(x for x in langs if x!='en')
        self.assertEqual(others,{'ja','es','pt','fr','de','it','zh-Hans'})
    def test_english_only_is_strict_search_plan(self):
        for r in range(4):self.assertEqual([x['language'] for x in select_profiles(self.config(),r,'english_only','',1)],['en']*6)
    def test_balanced_rotates_languages(self):
        seen=set()
        for r in range(8):seen.update(language_slots(parse_collection_plan('balanced'),4,r))
        self.assertEqual(seen,{'en','ja','es','pt','fr','de','it','zh-Hans'})
    def test_custom_weights_validate(self):
        plan=parse_collection_plan('custom','en:50,es:30,fr:20');self.assertEqual(set(plan['allowed']),{'en','es','fr'})
        with self.assertRaises(ValueError):parse_collection_plan('custom','en:70,xx:30')
    def test_retry_round_changes_lane_emphasis(self):
        one=[x['lane'] for x in select_profiles(self.config(),0,'english_focus','',1)]
        two=[x['lane'] for x in select_profiles(self.config(),0,'english_focus','',2)]
        three=[x['lane'] for x in select_profiles(self.config(),0,'english_focus','',3)]
        self.assertNotEqual(one,two);self.assertNotEqual(two,three);self.assertIn('open',one);self.assertIn('open',two);self.assertIn('open',three)
    def test_topics_not_frozen_to_nine_examples(self):
        topics={x['label'] for r in range(128) for x in select_profiles(self.config(),r)}
        for term in ['유머 속 따뜻함','노력 끝의 인정','존엄과 인정','용서와 두 번째 기회']:self.assertIn(term,topics)
    def test_reference_ids_exact_no_guessed_channel(self):
        refs=self.config()['discovery']['reference_video_ids']
        self.assertEqual(refs,['bTL6azhffzA','sHEUBff9pEg','z_clVFgQEbE','je_xDVmXpvQ'])
        self.assertEqual(self.config()['channel_ids'],[])
    def test_search_stays_twelve(self):
        api=Fake();m.collect(api,self.config());self.assertEqual(sum(e=='search' for e,_ in api.calls),12)
    def test_search_is_movie_tv_topic_gated(self):
        api=Fake();m.collect(api,self.config());topics=[p.get('topicId') for e,p in api.calls if e=='search']
        self.assertTrue(topics);self.assertTrue(all(x in set(SCREEN_TOPIC_IDS.values()) for x in topics))
        self.assertEqual(set(topics),set(SCREEN_TOPIC_IDS.values()))
    def test_reference_channel_followed_even_large(self):
        api=Fake();data=m.collect(api,self.config())
        self.assertIn(ALT,[v['id'] for v in data['videos']])
        self.assertEqual(next(v for v in data['videos'] if v['id']==ALT)['subscribers'],900000)
        self.assertEqual(data['referenceSummary']['resolved'],1)
        self.assertTrue(data['warnings']) # remaining links missing, not fabricated
    def test_reference_video_not_new_candidate(self):
        data=m.collect(Fake(),self.config());self.assertNotIn(REF,[v['id'] for v in data['videos']])
    def test_provenance_is_not_content_score(self):
        data=m.collect(Fake(),self.config())
        v=next(v for v in data['videos'] if v['id']==VID)
        self.assertEqual(set(v['discoveryRoutes']),{'familiar','expand','work','open'})
        self.assertEqual(v['originalStatus'],'unverified');self.assertNotIn('score',v)
        self.assertNotIn('isShort',v);self.assertTrue(v['shortsHint'])
    def test_nonreferenced_new_work_is_not_excluded(self):
        class NewWork(Fake):
            def get(self,e,**p):
                data=super().get(e,**p)
                if e=='videos' and p['part']!='snippet':
                    for x in data['items']:x['snippet']['title']='Unlisted independent film scene #shorts'
                return data
        self.assertEqual(len(m.collect(NewWork(),self.config())['videos']),2)
    def test_hint_requires_explicit_marker_not_length(self):
        self.assertFalse(shorts_hint({'title':'movie scene','durationSeconds':30}))
        self.assertTrue(shorts_hint({'title':'hello #Shorts'}))
        self.assertTrue(shorts_hint({'tags':['shorts']}))
        self.assertFalse(shorts_hint({'title':'shortsword technique'}))
    def test_missing_references_no_crash(self):
        class Missing(Fake):
            def get(self,e,**p):
                if e=='videos' and p['part']=='snippet':return {'items':[]}
                return super().get(e,**p)
        data=m.collect(Missing(),self.config());self.assertEqual(data['referenceSummary']['resolved'],0)
        self.assertEqual(len(data['videos']),1);self.assertTrue(data['warnings'])
    def test_unavailable_playlist_is_warning(self):
        class Unavailable(Fake):
            def get(self,e,**p):
                if e=='playlistItems':raise m.CollectionError('safe','playlistNotFound')
                return super().get(e,**p)
        self.assertEqual(len(m.collect(Unavailable(),self.config())['videos']),1)
    def test_quota_failure_not_swallowed(self):
        class Quota(Fake):
            def get(self,e,**p):
                if e=='playlistItems':raise m.CollectionError('quota','quotaExceeded')
                return super().get(e,**p)
        with self.assertRaises(m.CollectionError):m.collect(Quota(),self.config())
    def test_default_playlist_one_page(self):
        api=Fake();m.collect(api,self.config());self.assertEqual(sum(e=='playlistItems' for e,p in api.calls),1)
    def test_bounded_pagination_and_dedup(self):
        c=self.config();c['discovery']['reference_pages_per_channel']=2
        api=Fake();data=m.collect(api,c)
        self.assertEqual(sum(e=='playlistItems' for e,p in api.calls),2)
        self.assertEqual(len(data['videos']),2)
    def test_cap_preserves_routes_without_small_channel_bias(self):
        rows=[{'id':str(i),'views':10000-i,'subscribers':100000,'discoveryRoutes':['work']} for i in range(50)]
        rows += [{'id':'small','views':1000,'subscribers':2000,'discoveryRoutes':['open']}, {'id':'small2','views':900,'subscribers':8000,'discoveryRoutes':['expand']}]
        out=diverse_snapshot(rows,5);ids=[v['id'] for v in out]
        self.assertEqual(len(out),5);self.assertIn('small',ids);self.assertIn('small2',ids)
        self.assertEqual(out[0]['id'],'0')
    def test_under_cap_keeps_everything(self):
        rows=[{'id':str(i),'views':i,'subscribers':100} for i in range(3)]
        self.assertEqual(len(diverse_snapshot(rows,400)),3)
    def test_invalid_plan_ref_rejected(self):
        raw=json.loads((ROOT/'discovery.json').read_text());raw['reference_video_ids']=['invalid!']
        with self.assertRaises(ValueError):validate_discovery(raw)
    def test_missing_open_lane_rejected(self):
        raw=json.loads((ROOT/'discovery.json').read_text());raw['profiles']=[p for p in raw['profiles'] if p['lane']!='open']
        with self.assertRaises(ValueError):validate_discovery(raw)
    def test_invalid_plan_file_does_not_silently_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'config.json').write_text(json.dumps({'queries':['movie scene']}));(p/'discovery.json').write_text('{}')
            with self.assertRaises(m.CollectionError):m.load_config(p/'config.json')
    def test_disabled_plan_returns_legacy(self):
        c=self.config();c['discovery']['enabled']=False
        self.assertEqual({p['lane'] for p in select_profiles(c,0)},{'legacy'})
    def test_lower_query_budget_still_explores(self):
        c=self.config()
        for n in [1,2,3]:
            c['queries_per_run']=n;out=select_profiles(c,0);self.assertEqual(len(out),n);self.assertIn('open',[p['lane'] for p in out])
    def test_snapshot_metadata_has_new_version(self):
        out=m.collect(Fake(),self.config());self.assertEqual(out['collectorVersion'],'1.8')
        self.assertEqual(out['collectionSummary']['kept'],len(out['videos']))
        self.assertLessEqual(len(out['videos']),40)

    def test_review_pool_limits_one_channel(self):
        rows=[]
        for i in range(30):
            rows.append({'id':f'g{i}','views':1000000-i,'subscribers':3000,'channelId':'same','discoveryRoutes':['familiar'],'sourceKinds':['search']})
        for i in range(30):
            rows.append({'id':f'x{i}','views':900000-i,'subscribers':4000,'channelId':f'other{i}','discoveryRoutes':['open'],'sourceKinds':['search']})
        out=select_review_pool(rows,48,4,30,15)
        self.assertEqual(len(out),34)
        self.assertLessEqual(sum(v['channelId']=='same' for v in out),4)

    def test_review_pool_caps_seed_and_reference_sources(self):
        rows=[]
        for i in range(40):
            rows.append({'id':f's{i}','views':800000-i,'subscribers':3000,'channelId':f'seed{i}','discoveryRoutes':['source'],'sourceKinds':['seed']})
        for i in range(30):
            rows.append({'id':f'r{i}','views':700000-i,'subscribers':3000,'channelId':f'ref{i}','discoveryRoutes':['source'],'sourceKinds':['reference']})
        for i in range(60):
            rows.append({'id':f'q{i}','views':600000-i,'subscribers':3000,'channelId':f'q{i}','discoveryRoutes':['familiar' if i%2 else 'open'],'sourceKinds':['search']})
        out=select_review_pool(rows,48,4,30,15)
        self.assertEqual(len(out),48)
        self.assertLessEqual(sum(source_category(v)=='seed' for v in out),14)
        self.assertLessEqual(sum(source_category(v)=='reference' for v in out),7)
        self.assertGreater(sum(source_category(v) in {'guided','explore'} for v in out),20)

    def test_search_hit_from_seed_channel_is_search_category(self):
        v={'id':'a','discoveryRoutes':['familiar','source'],'sourceKinds':['search','seed']}
        self.assertEqual(source_category(v),'guided')

    def test_english_focus_source_channel_respects_active_run_languages(self):
        class SpanishSource(Fake):
            def get(self,e,**p):
                data=super().get(e,**p)
                if e=='videos' and p.get('part')!='snippet':
                    for x in data['items']:
                        if x['id']==ALT:
                            x['snippet']['defaultAudioLanguage']='es';x['snippet']['title']='Una escena emotiva de una familia que se reconcilia #shorts'
                return data
        # rotation 0 uses en + ja/es as the non-English slots. Use Portuguese to verify a non-active source upload does not leak through.
        class PortugueseSource(Fake):
            def get(self,e,**p):
                data=super().get(e,**p)
                if e=='videos' and p.get('part')!='snippet':
                    for x in data['items']:
                        if x['id']==ALT:
                            x['snippet']['defaultAudioLanguage']='pt';x['snippet']['title']='Uma cena emocionante de uma família que se reconcilia #shorts'
                return data
        out=m.collect(PortugueseSource(),self.config(),rotation=0,collection_preset='english_focus')
        self.assertNotIn(ALT,[v['id'] for v in out['videos']])

    def test_liked_seed_video_resolves_channel_and_scans_bounded_page(self):
        seed='SeedVideo01';seed_channel='UC'+'s'*22;seed_alt='SeedResult1'
        class SeedFake(Fake):
            def get(self,e,**p):
                self.calls.append((e,p))
                if e=='search':return {'items':[{'id':{'videoId':VID}}]}
                if e=='videos' and p.get('part')=='snippet':
                    items=[]
                    for x in p['id'].split(','):
                        if x==REF:items.append({'id':x,'snippet':{'channelId':LARGE}})
                        if x==seed:items.append({'id':x,'snippet':{'channelId':seed_channel}})
                    return {'items':items}
                if e=='channels' and 'contentDetails' in p.get('part',''):
                    return {'items':[{'id':c,'snippet':{'title':'src'},'contentDetails':{'relatedPlaylists':{'uploads':'UU'+c[2:]}}} for c in p['id'].split(',')]}
                if e=='playlistItems':
                    vid=seed_alt if p['playlistId']=='UU'+seed_channel[2:] else ALT
                    return {'items':[{'contentDetails':{'videoId':vid}}], 'nextPageToken':'next'}
                if e=='videos':
                    return {'items':[make_video(x,seed_channel if x==seed_alt else CID) for x in p['id'].split(',')]}
                if e=='channels':return {'items':[{'id':c,'statistics':{'subscriberCount':'2500','hiddenSubscriberCount':False}} for c in p['id'].split(',')]}
                raise AssertionError(e)
        api=SeedFake();out=m.collect(api,self.config(),seed_video_ids=seed,collection_preset='english_only')
        self.assertEqual(out['referenceSummary']['seedResolved'],1)
        self.assertEqual(out['referenceSummary']['seedChannels'],1)
        self.assertNotIn(seed,[v['id'] for v in out['videos']])
        self.assertIn(seed_alt,[v['id'] for v in out['videos']])
        self.assertEqual(sum(e=='playlistItems' and p.get('playlistId')=='UU'+seed_channel[2:] for e,p in api.calls),1)
        seed_rows=[v for v in out['videos'] if v['id']==seed_alt]
        self.assertTrue(seed_rows);self.assertIn('seed',seed_rows[0].get('sourceKinds',[]))


    def test_profiles_alternate_movie_and_tv_topics(self):
        rows=select_profiles(self.config(),0,'english_focus','',1)
        self.assertEqual({r['screenTopic'] for r in rows},{'movie','tv'})
        self.assertEqual([r['screenTopic'] for r in rows[:4]],['movie','tv','movie','tv'])

    def test_source_only_non_screen_upload_is_rejected(self):
        class NonScreenSource(Fake):
            def get(self,e,**p):
                data=super().get(e,**p)
                if e=='videos' and p.get('part')!='snippet':
                    for x in data['items']:
                        if x['id']==ALT:
                            x['snippet']['title']='Camera lens review and unboxing #shorts'
                            x['snippet']['description']='Gear review'
                            x['snippet']['categoryId']='26'
                return data
        out=m.collect(NonScreenSource(),self.config())
        self.assertNotIn(ALT,[v['id'] for v in out['videos']])
        self.assertGreaterEqual(out['collectionSummary']['rejectedNonScreen'],1)

    def test_subscriber_count_not_used_in_review_priority(self):
        rows=[
            {'id':'big','views':900000,'subscribers':900000,'channelId':'big','discoveryRoutes':['familiar'],'sourceKinds':['search'],'screenGate':['movie'],'screenKind':'film'},
            {'id':'small','views':100000,'subscribers':1000,'channelId':'small','discoveryRoutes':['familiar'],'sourceKinds':['search'],'screenGate':['movie'],'screenKind':'film'}]
        out=select_review_pool(rows,2,3,25,10)
        self.assertEqual([v['id'] for v in out],['big','small'])

if __name__=='__main__':unittest.main()
