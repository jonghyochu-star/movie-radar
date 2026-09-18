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
        for control in ['collect-preset','retry-round','max-subs','shorts-filter','no-harvest','find-more']:
            pos=html.find(f'id="{control}"')
            self.assertNotEqual(pos,-1,control)
            snippet=html[max(0,pos-160):pos+500]
            self.assertIn('title=',snippet,control)
    def test_version_is_142(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        self.assertIn('version">1.4.2<',html)

if __name__=='__main__':
    unittest.main()
