import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class UiSourceTests(unittest.TestCase):
    def test_like_saved_visual_exists(self):
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        css=(ROOT/'site/styles.css').read_text(encoding='utf-8')
        self.assertIn('♥ 좋아요 저장됨',app)
        self.assertIn('is-liked',app)
        self.assertIn('.card.is-liked',css)
    def test_review_queue_is_current_deployment_only(self):
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        self.assertIn("if(target==='review')return collected.has(v.id)&&C.needsReview(v,r)",app)

    def test_key_controls_have_hover_help(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        for control in ['collect-preset','retry-round','max-subs','shorts-filter','no-harvest','find-more','copy-seeds']:
            pos=html.find(f'id="{control}"')
            self.assertNotEqual(pos,-1,control)
            snippet=html[max(0,pos-160):pos+500]
            self.assertIn('title=',snippet,control)
    def test_version_is_18(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        self.assertIn('version">1.8<',html)


    def test_broad_candidate_button_exists(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        self.assertIn('id="broad-filters"',html)
        self.assertIn('전체 후보 보기',html)
        self.assertIn("C.broadFilters()",app)

    def test_seed_copy_and_quota_summary_present(self):
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        self.assertIn('seed_video_ids:',app)
        self.assertIn('likedSeedIds',app)
        self.assertIn('searchListCalls',app)


    def test_refresh_waits_for_new_pages_deployment(self):
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        self.assertIn('data.generatedAt!==before',app)
        self.assertIn('새 배포 확인',app)
        self.assertIn('아직 이전 배포가 보입니다',app)
        self.assertIn('새 수집 결과 확인',html)

    def test_seed_not_passed_warning_exists(self):
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        self.assertIn('이번 배포에는 좋아요 씨앗 ID가 전달되지 않음',app)

    def test_review_pool_summary_is_visible(self):
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        self.assertIn('검토 풀',app)
        self.assertIn('한 채널 최대',app)
        self.assertIn('씨앗 출처 최대',app)


    def test_priority_and_taste_assist_ui_exists(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        app=(ROOT/'site/app.js').read_text(encoding='utf-8')
        css=(ROOT/'site/styles.css').read_text(encoding='utf-8')
        self.assertIn('value="priority"',html)
        self.assertIn('id="taste-assist"',html)
        self.assertIn('내 취향 반영',html)
        self.assertIn('personalizedBlend',app)
        self.assertIn('preferenceClass',app)
        self.assertIn('priorityPanel',app)
        self.assertIn('.priority-strip',css)


    def test_v17_movie_tv_gate_defaults(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        core=(ROOT/'site/core.js').read_text(encoding='utf-8')
        self.assertIn('value="screen_gate" selected',html)
        self.assertIn('value="0" selected>제한 없음 · 참고만',html)
        self.assertIn("maxSubscribers:0",core)
        self.assertIn("screenGateInfo",core)

if __name__=='__main__':
    unittest.main()

# 1.8 regression checks
def _v18_extra(self):
    core=(ROOT/'site/core.js').read_text(encoding='utf-8')
    app=(ROOT/'site/app.js').read_text(encoding='utf-8')
    html=(ROOT/'site/index.html').read_text(encoding='utf-8')
    self.assertIn('usableDislikes',core)
    self.assertIn('personalizedBlend',core)
    self.assertIn('취향 데이터 좋아요',app)
    self.assertIn('내 취향 우선',html)
UiSourceTests.test_v18_like_dislike_learning=_v18_extra
