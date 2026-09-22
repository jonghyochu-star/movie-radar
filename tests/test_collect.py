import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('collect',ROOT/'scripts/collect.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
GOOD='AbCdEfGhI01';LONG='AbCdEfGhI02';PRIVATE='AbCdEfGhI03';HIDDEN='AbCdEfGhI04'
CID='UC'+'a'*22;CID2='UC'+'b'*22
class FakeAPI:
    def __init__(self):self.calls=[]
    def get(self,endpoint,**params):
        self.calls.append((endpoint,params))
        if endpoint=='search':return {'items':[{'id':{'videoId':x}} for x in [GOOD,LONG,PRIVATE,HIDDEN]]}
        if endpoint=='videos':
            items=[]
            for i,vid in enumerate([GOOD,LONG,PRIVATE,HIDDEN]):
                items.append({'id':vid,'snippet':{'title':'Original <script> title '+vid,'channelTitle':'Source','channelId':CID2 if vid==HIDDEN else CID,'liveBroadcastContent':'none','publishedAt':'2026-01-01T00:00:00Z','thumbnails':{'high':{'url':'https://i.ytimg.com/vi/'+vid+'/hqdefault.jpg'}}},'statistics':{'viewCount':str(100000+i)},'contentDetails':{'duration':'PT5M' if vid==LONG else 'PT1M20S'},'status':{'privacyStatus':'private' if vid==PRIVATE else 'public'}})
            return {'items':items}
        if endpoint=='channels':return {'items':[{'id':CID,'statistics':{'subscriberCount':'2000','hiddenSubscriberCount':False}},{'id':CID2,'statistics':{'hiddenSubscriberCount':True}}]}
        raise AssertionError(endpoint)
class TestCollect(unittest.TestCase):
    def config(self):
        # Legacy behavior regression; discovery routes have separate tests.
        c=m.load_config(ROOT/'config.json');c.pop('discovery',None);return c
    def test_config_valid(self):self.assertEqual(self.config()['queries_per_run'],6)
    def test_duration(self):
        for raw,val in [('PT1M30S',90),('PT1H2M3S',3723),('PT0S',0),('P1D',None),('',None),('PT',None)]:self.assertEqual(m.duration_seconds(raw),val)
    def test_number(self):
        self.assertEqual(m.number('100'),100);self.assertIsNone(m.number('no'));self.assertIsNone(m.number(-1));self.assertIsNone(m.number(None))
    def test_dedup_filter_and_hidden(self):
        api=FakeAPI();result=m.collect(api,self.config(),0,datetime(2026,9,18,tzinfo=timezone.utc))
        self.assertEqual({v['id'] for v in result['videos']},{GOOD,HIDDEN})
        self.assertIsNone(next(v for v in result['videos'] if v['id']==HIDDEN)['subscribers'])
        self.assertEqual(len([x for x in api.calls if x[0]=='search']),12)
        self.assertEqual(result['mode'],'live')
        self.assertIn('<script>',result['videos'][0]['title']) # preserve raw API title; escape in browser
    def test_rotation(self):
        c=self.config();a=m.collect(FakeAPI(),c,0);b=m.collect(FakeAPI(),c,1)
        self.assertNotEqual(a['searchQueries'],b['searchQueries'])
    def test_search_scope(self):
        api=FakeAPI();m.collect(api,self.config());search=[p for e,p in api.calls if e=='search']
        self.assertIn('publishedAfter',search[0]);self.assertNotIn('publishedAfter',search[1]);self.assertEqual(search[0]['relevanceLanguage'],'en')
    def test_missing_key(self):
        with self.assertRaises(m.CollectionError):m.YouTube('')
    def test_secret_not_in_url_or_message(self):
        secret='NEVER-PRINT-THIS'
        err=HTTPError('https://invalid/?key='+secret,403,'denied',{},BytesIO(b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}'))
        with patch.object(m,'urlopen',side_effect=err) as mocked:
            with self.assertRaises(m.CollectionError) as got:m.YouTube(secret).get('search',part='snippet')
            self.assertNotIn(secret,str(got.exception));self.assertNotIn(secret,mocked.call_args.args[0].full_url)
    def test_output_schema(self):
        data=m.collect(FakeAPI(),self.config());v=data['videos'][0]
        for key in ['id','title','views','subscribers','durationSeconds','fetchedAt','source']:self.assertIn(key,v)
        self.assertNotIn('score',v)
    def test_invalid_config(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';p.write_text('{"queries_per_run":999}')
            with self.assertRaises(m.CollectionError):m.load_config(p)
    def test_query_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';p.write_text('{"queries":[]}')
            with self.assertRaises(m.CollectionError):m.load_config(p)
    def test_empty_results(self):
        class Empty:
            def get(self,*a,**kw):return {'items':[]}
        r=m.collect(Empty(),self.config());self.assertEqual(r['videos'],[]);self.assertTrue(r['warnings'])
    def test_priority_profiles_rotate_with_anchor(self):
        c=self.config();seen=set()
        for rotation in range(4):
            api=FakeAPI();result=m.collect(api,c,rotation)
            seen.update(result['searchLanguages'])
            searches=[params for name,params in api.calls if name=='search']
            self.assertEqual(len(searches),12)
            self.assertTrue(all('regionCode' not in p for p in searches))
            self.assertEqual(searches[0]['relevanceLanguage'],'en')
            self.assertEqual(searches[0].get('topicId'),'/m/02vxn')
            self.assertNotIn('topicId',searches[1])
            self.assertEqual(searches[1]['order'],'viewCount')
        self.assertEqual(len(seen),8)
        self.assertNotIn('hi',seen);self.assertNotIn('ar',seen)
        self.assertNotIn('ko',seen)
    def test_every_output_is_unverified_not_guessed(self):
        result=m.collect(FakeAPI(),self.config())
        self.assertEqual(result['reviewPolicy'],'manual-original-country-v1')
        self.assertTrue(all(v['originalStatus']=='unverified' for v in result['videos']))
    def test_korean_text_does_not_prove_korean_original(self):
        class KoreanText(FakeAPI):
            def get(self,endpoint,**params):
                data=super().get(endpoint,**params)
                if endpoint=='videos':
                    for v in data['items']:
                        v['snippet']['title']='한국어 자막 외국 영화 테스트 '+v['id']
                        v['snippet']['defaultAudioLanguage']='ko'
                return data
        result=m.collect(KoreanText(),self.config())
        self.assertEqual(len(result['videos']),2)
        self.assertTrue(all(v['originalStatus']=='unverified' for v in result['videos']))
    def test_legacy_string_queries_still_work(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';p.write_text(json.dumps({'queries':['film scene'],'relevance_language':'en','region_code':'US'}))
            c=m.load_config(p);api=FakeAPI();m.collect(api,c)
            search=next(params for name,params in api.calls if name=='search')
            self.assertEqual(search['q'],'film scene');self.assertEqual(search['regionCode'],'US')
    def test_invalid_language_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';p.write_text(json.dumps({'queries':[{'q':'film','language':'en&key=oops'}]}))
            with self.assertRaises(m.CollectionError):m.load_config(p)
    def test_no_language_preference_supported(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';p.write_text(json.dumps({'queries':[{'q':'film','language':''}]}))
            c=m.load_config(p);api=FakeAPI();m.collect(api,c)
            search=next(params for name,params in api.calls if name=='search')
            self.assertNotIn('relevanceLanguage',search);self.assertNotIn('regionCode',search)
    def test_language_fields_exported_separately(self):
        class Mixed(FakeAPI):
            def get(self,endpoint,**params):
                data=super().get(endpoint,**params)
                if endpoint=='videos':
                    for i,v in enumerate(data['items']):
                        v['snippet'].update(title='Yodha movie scene bhik mangne ka tarika '+v['id']+' #explore #viral',defaultLanguage='en')
                        if v['id']==HIDDEN:v['snippet']['defaultAudioLanguage']='hi'
                return data
        out=m.collect(Mixed(),self.config())
        self.assertEqual(out['collectorVersion'],'1.8')
        missing=next(v for v in out['videos'] if v['id']==GOOD)
        audio=next(v for v in out['videos'] if v['id']==HIDDEN)
        self.assertEqual((missing['language'],missing['declaredLanguage'],missing['languageSource']),('unknown','en','unknown'))
        self.assertEqual((audio['language'],audio['audioLanguage'],audio['declaredLanguage']),('hi','hi','en'))
        self.assertEqual(missing['originalStatus'],'unverified')
        self.assertIn('movie scene',missing['screenReason'])
    def test_english_only_filters_known_non_english_in_discovery_mode(self):
        class Japanese(FakeAPI):
            def get(self,endpoint,**params):
                data=super().get(endpoint,**params)
                if endpoint=='videos':
                    for v in data['items']:
                        v['snippet']['defaultAudioLanguage']='ja';v['snippet']['title']='映画 シーン 感動'
                return data
        c=m.load_config(ROOT/'config.json')
        out=m.collect(Japanese(),c,collection_preset='english_only')
        self.assertEqual(out['videos'],[])
    def test_seed_video_ids_parse_and_limit(self):
        self.assertEqual(m.parse_seed_video_ids('AbCdEfGhI01, AbCdEfGhI02 AbCdEfGhI01'),['AbCdEfGhI01','AbCdEfGhI02'])
        with self.assertRaises(m.CollectionError):m.parse_seed_video_ids('not-a-youtube-id')
        with self.assertRaises(m.CollectionError):m.parse_seed_video_ids(','.join(f'AbCdEfGh{i:02d}' for i in range(9)))
    def test_previous_ids_are_excluded(self):
        c=m.load_config(ROOT/'config.json')
        out=m.collect(FakeAPI(),c,excluded_ids={GOOD})
        self.assertNotIn(GOOD,[v['id'] for v in out['videos']])
        self.assertIn(GOOD,out['collectorHistoryIds'])
    def test_prior_pages_url_is_bounded(self):
        self.assertEqual(m.prior_pages_url('owner/repo'),'https://owner.github.io/repo/data/videos.json')
        self.assertIsNone(m.prior_pages_url('bad/../../repo'))
    def test_title_fingerprint_is_irreversible_and_bounded(self):
        fp=m.title_token_hashes('Escena de película: una segunda oportunidad #shorts viral')
        self.assertTrue(fp);self.assertTrue(all(len(x)==12 for x in fp))
        self.assertNotIn('segunda',fp)
    def test_near_duplicate_requires_strong_overlap(self):
        a=m.title_token_hashes('Una familia recibe una segunda oportunidad inesperada')
        b=m.title_token_hashes('Una familia recibe una segunda oportunidad inesperada #shorts')
        c=m.title_token_hashes('Un maestro ayuda a un alumno con su futuro')
        self.assertTrue(m.near_duplicate(a,[b]));self.assertFalse(m.near_duplicate(a,[c]))
    def test_cache_history_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'history.json';fp=m.title_token_hashes('A father gives her a second chance tonight')
            m.save_cache_history(p,[GOOD],[fp]);ids,fps=m.load_cache_history(p)
            self.assertIn(GOOD,ids);self.assertEqual(fps,[fp])
    def test_recent_history_is_bounded_and_ordered(self):
        ids=[('A'+format(i,'010d'))[-11:] for i in range(450)]
        kept=m.ordered_video_ids(ids)
        self.assertEqual(len(kept),m.RECENT_HISTORY_LIMIT)
        self.assertEqual(kept,ids[-m.RECENT_HISTORY_LIMIT:])

if __name__=='__main__':unittest.main()


class V18MetadataTests(unittest.TestCase):
    def test_discovery_labels_field_supported_in_output_contract(self):
        text=(ROOT/'scripts/collect.py').read_text(encoding='utf-8')
        self.assertIn("'discoveryLabels':discovery_labels.get(vid,[])",text)
        self.assertIn("'collectorVersion':'1.8'",text)
