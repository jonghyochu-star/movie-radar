import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=str(ROOT/'scripts')
if SCRIPT not in sys.path: sys.path.insert(0,SCRIPT)
import audience as a

class AudienceTests(unittest.TestCase):
    def test_age_floors_match_initial_creator_thresholds(self):
        self.assertEqual(a.floor_views(6),200000)
        self.assertEqual(a.floor_views(18),500000)
        self.assertEqual(a.floor_views(36),1000000)
        self.assertEqual(a.floor_views(60),2000000)
        self.assertEqual(a.floor_views(100),5000000)
        self.assertEqual(a.floor_views(150),5000000)
        self.assertEqual(a.floor_views(5000),5000000)

    def test_no_lifetime_average_is_used(self):
        m=a.audience_metrics('2025-09-23T00:00:00Z',5000000,[],datetime(2026,9,23,tzinfo=timezone.utc))
        self.assertTrue(m['validated'])
        self.assertTrue(m['cumulativeProven'])
        self.assertFalse(m['lifetimeAverageUsed'])
        self.assertNotIn('average',m)

    def test_observed_24h_delta_can_validate(self):
        now=datetime(2026,9,23,0,0,tzinfo=timezone.utc)
        snaps=[{'at':'2026-09-22T00:00:00Z','views':300000}]
        m=a.audience_metrics('2026-09-20T00:00:00Z',900000,snaps,now)
        self.assertTrue(m['surging'])
        self.assertTrue(m['validated'])
        self.assertEqual(m['deltas']['h24']['views'],600000)

    def test_old_proven_video_remains_proven_even_if_momentum_unknown(self):
        now=datetime(2026,9,23,0,0,tzinfo=timezone.utc)
        m=a.audience_metrics('2025-09-23T00:00:00Z',6000000,[],now)
        self.assertEqual(m['status'],'proven')
        self.assertTrue(m['validated'])
        self.assertFalse(m['surging'])

    def test_tracking_snapshot_roundtrip_shape(self):
        tracking={}
        now=datetime(2026,9,23,0,0,tzinfo=timezone.utc)
        a.add_observation(tracking,'AbCdEfGhI01','2026-09-22T00:00:00Z',500000,now,{'screenGate':['movie'],'discoveryRoutes':['open']})
        x=a.normalize_tracking(tracking)
        self.assertEqual(x['AbCdEfGhI01']['snapshots'][0]['views'],500000)
        self.assertEqual(x['AbCdEfGhI01']['screenGate'],['movie'])

if __name__=='__main__':
    unittest.main()
