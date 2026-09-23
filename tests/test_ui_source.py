import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class UiSourceTests(unittest.TestCase):
    def test_version_is_192(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        self.assertIn('version">1.9.2<',html)
        self.assertIn('styles.css?v=1.9.2',html)
        self.assertIn('app.js?v=1.9.2',html)

    def test_primary_navigation_is_simple_workflow(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        for token in ['data-tab="review"','새 후보','data-tab="likes"','결 맞음','data-tab="candidate"','제작 후보','data-tab="done"','제작 완료']:
            self.assertIn(token,html)
        self.assertNotIn('data-tab="discover"',html)

    def test_card_has_four_primary_decisions(self):
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        for token in ['♡ 결 맞음','결 아님','☆ 제작 후보','영화·드라마 아님']:
            self.assertIn(token,app)
        self.assertIn('toggle_overused',app)
        self.assertIn('toggle_weak_story',app)

    def test_like_followup_stays_on_same_card(self):
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        css=(ROOT/'site/styles.css').read_text(encoding='utf-8')
        self.assertIn('followupId',app)
        self.assertIn('결 맞음 · 이어서 판단',app)
        self.assertIn('해당 없거나 선택 완료 → 다음',app)
        self.assertIn("C.needsReview(v,r)||v.id===followupId",app)
        self.assertIn('.quality-row.followup',css)

    def test_candidate_is_immediately_available(self):
        core=(ROOT/'site/core.js').read_text(encoding='utf-8')
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        self.assertIn("r.rating='like';r.dislikeReason=null;r.stage='candidate'",core)
        self.assertIn('실제로 만들고 싶은 소재',app)

    def test_advanced_controls_are_collapsed(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        css=(ROOT/'site/styles.css').read_text(encoding='utf-8')
        self.assertIn('수집 · 필터 · 백업 설정',html)
        self.assertIn('class="utility-panel"',html)
        self.assertIn('.advanced-hidden-controls{display:none!important}',css)

    def test_refresh_waits_for_new_pages_deployment(self):
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        self.assertIn('data.generatedAt!==before',app)
        self.assertIn('새 배포 확인',app)
        self.assertIn('새 수집 결과 확인',html)

    def test_backup_folder_feature_remains(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        for token in ['id="backup-folder"','id="backup-location"','id="backup"','id="restore"']:
            self.assertIn(token,html)
        for token in ['showDirectoryPicker','indexedDB.open','getDirectoryHandle','getFileHandle','createWritable','backupFallback']:
            self.assertIn(token,app)

    def test_audience_layer_remains_visible_but_compact(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        core=(ROOT/'site/core.js').read_text(encoding='utf-8')
        collect=(ROOT/'scripts/collect.py').read_text(encoding='utf-8')
        self.assertIn('id="audience-filter"',html)
        self.assertIn('검증 영상',html)
        self.assertIn('audiencePanel',app)
        self.assertIn('audienceInfo',core)
        self.assertIn('audience_metrics',collect)
        self.assertIn('load_view_tracking',collect)

    def test_movie_tv_gate_and_full_history_remain(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        core=(ROOT/'site/core.js').read_text(encoding='utf-8')
        self.assertIn('value="screen_gate" selected',html)
        self.assertIn('data-tab="history"',html)
        self.assertIn('screenGateInfo',core)

    def test_collection_controls_still_exist_without_cluttering_main_screen(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        for control in ['collect-preset','retry-round','open-actions','find-more','copy-seeds','no-harvest']:
            self.assertIn(f'id="{control}"',html)
        self.assertIn('class="legacy-control" hidden',html)

if __name__=='__main__':
    unittest.main()
