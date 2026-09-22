import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class WorkflowSourceTests(unittest.TestCase):
    def test_history_cache_and_seed_input_present(self):
        text=(ROOT/'.github/workflows/movie-radar.yml').read_text(encoding='utf-8')
        self.assertIn('seed_video_ids:',text)
        self.assertIn('actions/cache@v4',text)
        self.assertIn('COLLECT_HISTORY_PATH: .cache/movie-radar/history.json',text)
        self.assertIn('--seed-video-ids "$SEED_VIDEO_IDS"',text)
    def test_config_expands_pool_but_bounded(self):
        import json
        c=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
        self.assertEqual(c['queries_per_run'],6)
        self.assertEqual(c['results_per_search'],50)
        self.assertEqual(c['max_videos'],500)

    def test_v16_review_pool_settings_are_bounded(self):
        import json
        d=json.loads((ROOT/'discovery.json').read_text(encoding='utf-8'))
        self.assertEqual(d['review_pool_limit'],48)
        self.assertEqual(d['per_channel_limit'],4)
        self.assertEqual(d['seed_pool_percent'],30)
        self.assertEqual(d['reference_pool_percent'],15)
        self.assertEqual(d['seed_pages_per_channel'],1)

if __name__=='__main__':unittest.main()
