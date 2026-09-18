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
                items.append({'id':vid,'snippet':{'title':'Original <script> title','channelTitle':'Source','channelId':CID2 if vid==HIDDEN else CID,'liveBroadcastContent':'none','publishedAt':'2026-01-01T00:00:00Z','thumbnails':{'high':{'url':'https://i.ytimg.com/vi/'+vid+'/hqdefault.jpg'}}},'statistics':{'viewCount':str(100000+i)},'contentDetails':{'duration':'PT5M' if vid==LONG else 'PT1M20S'},'status':{'privacyStatus':'private' if vid==PRIVATE else 'public'}})
            return {'items':items}
        if endpoint=='channels':return {'items':[{'id':CID,'statistics':{'subscriberCount':'2000','hiddenSubscriberCount':False}},{'id':CID2,'statistics':{'hiddenSubscriberCount':True}}]}
        raise AssertionError(endpoint)
class TestCollect(unittest.TestCase):
    def config(self):return m.load_config(ROOT/'config.json')
    def test_config_valid(self):self.assertEqual(self.config()['queries_per_run'],4)
    def test_duration(self):
        for raw,val in [('PT1M30S',90),('PT1H2M3S',3723),('PT0S',0),('P1D',None),('',None),('PT',None)]:self.assertEqual(m.duration_seconds(raw),val)
    def test_number(self):
        self.assertEqual(m.number('100'),100);self.assertIsNone(m.number('no'));self.assertIsNone(m.number(-1));self.assertIsNone(m.number(None))
    def test_dedup_filter_and_hidden(self):
        api=FakeAPI();result=m.collect(api,self.config(),0,datetime(2026,9,18,tzinfo=timezone.utc))
        self.assertEqual({v['id'] for v in result['videos']},{GOOD,HIDDEN})
        self.assertIsNone(next(v for v in result['videos'] if v['id']==HIDDEN)['subscribers'])
        self.assertEqual(len([x for x in api.calls if x[0]=='search']),8)
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
if __name__=='__main__':unittest.main()
