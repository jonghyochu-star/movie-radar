import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from screen_rules import infer_language, screen_evidence, language_base

def video(title,description='',tags=None,category='24'):
    return {'snippet':{'title':title,'description':description,'tags':tags or [],'categoryId':category}}

class ScreenRulesTest(unittest.TestCase):
    def test_film_scene(self):
        self.assertEqual(screen_evidence(video('The father returns - movie scene'))['kind'],'film')
    def test_title_description_original_label(self):
        self.assertEqual(screen_evidence(video('He gives her a second chance','Movie: Example (2014)'))['kind'],'film')
    def test_independent_short(self):
        self.assertEqual(screen_evidence(video('A gift - independent short film'))['kind'],'film')
    def test_tv_preserved(self):
        self.assertEqual(screen_evidence(video('TV series scene: he forgives his son'))['kind'],'series')
    def test_spanish(self):
        self.assertEqual(screen_evidence(video('Una escena de película emocionante'))['kind'],'film')
    def test_french(self):
        self.assertEqual(screen_evidence(video('Scène du film un cadeau'))['kind'],'film')
    def test_japanese(self):
        self.assertEqual(screen_evidence(video('映画のワンシーン - お父さん'))['kind'],'film')
    def test_gameplay_not_saved_by_hashtag(self):
        self.assertEqual(screen_evidence(video('Minecraft gameplay #movie #film','movie scene'))['kind'],'non_screen')
    def test_vlog_not_saved_by_hashtag(self):
        self.assertEqual(screen_evidence(video('My daily vlog #movie'))['kind'],'non_screen')
    def test_music_video_separated(self):
        self.assertEqual(screen_evidence(video('Official music video - singer','movie scene'))['kind'],'non_screen')
    def test_single_hashtag_not_proof(self):
        self.assertEqual(screen_evidence(video('He helps her #movie'))['kind'],'unknown')
    def test_category_not_proof(self):
        self.assertEqual(screen_evidence(video('A surprise at home',category='1'))['kind'],'unknown')
    def test_search_query_not_available_as_proof(self):
        self.assertEqual(screen_evidence(video('A surprise #viral'))['kind'],'unknown')
    def test_generic_movie_word_alone_not_proof(self):
        self.assertEqual(screen_evidence(video('We buy movie tickets'))['kind'],'unknown')
    def test_tag_and_title_clues(self):
        self.assertEqual(screen_evidence(video('A movie moment with her father',tags=['film']))['kind'],'film')
    def test_topic_evidence(self):
        v=video('He forgives #movie');v['topicDetails']={'topicCategories':['https://en.wikipedia.org/wiki/Film']}
        self.assertEqual(screen_evidence(v)['kind'],'film')
    def test_arabic_script_not_country(self):
        x=infer_language({'title':'مشهد رائع من فيلم','defaultAudioLanguage':'en'})
        self.assertEqual(x['code'],'ar-script');self.assertEqual(x['audio'],'en')
    def test_indic_script_not_assumed_hindi(self):
        x=infer_language({'title':'फिल्म का सबसे अच्छा दृश्य'})
        self.assertEqual(x['code'],'indic-script')
    def test_registered_hindi(self):
        x=infer_language({'title':'फिल्म का दृश्य','defaultLanguage':'hi'})
        self.assertEqual(x['code'],'hi')
    def test_urdu_not_arabic(self):
        x=infer_language({'title':'یہ فلم بہت اچھی ہے','defaultLanguage':'ur'})
        self.assertEqual(x['code'],'ur')
    def test_japanese_mixed_script(self):
        self.assertEqual(infer_language({'title':'映画のお父さん名場面'})['code'],'ja')
    def test_korean_text_not_production_country(self):
        x=infer_language({'title':'한국어 자막 외국 영화'})
        self.assertEqual(x['code'],'ko');self.assertNotIn('country',x)
    def test_default_language(self):
        self.assertEqual(infer_language({'title':'...','defaultLanguage':'es-MX'})['code'],'es')
    def test_audio_fallback(self):
        self.assertEqual(infer_language({'title':'...','defaultAudioLanguage':'fr'})['code'],'fr')
    def test_unknown_not_english(self):
        self.assertEqual(infer_language({'title':'wow #viral #shorts'})['code'],'unknown')
    def test_query_language_never_proof(self):
        self.assertEqual(infer_language({'title':'wow','searchLanguage':'en'})['code'],'unknown')
    def test_language_sanitized(self):
        self.assertEqual(language_base('<script>'),'')
    def test_simple_english_title(self):
        self.assertEqual(infer_language({'title':'The father helps his daughter'})['code'],'en')
if __name__=='__main__':unittest.main()
