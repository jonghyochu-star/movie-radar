import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("gemini_lab_batch",ROOT/"scripts"/"gemini_lab_batch.py")
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

class GeminiBatchTests(unittest.TestCase):
    def test_parse_urls(self):
        x=M.parse_urls("https://youtu.be/AbCdEfGhI01,\nhttps://www.youtube.com/shorts/AbCdEfGhI02")
        self.assertEqual(len(x),2)
        self.assertTrue(x[0].endswith("AbCdEfGhI01"))
    def test_parse_labels(self):
        self.assertEqual(M.parse_labels("",2),["unknown","unknown"])
        self.assertEqual(M.parse_labels("movie_drama,not_movie_drama",2),["movie_drama","not_movie_drama"])
        with self.assertRaises(M.LabError): M.parse_labels("movie_drama",2)
    def test_summary(self):
        rows=[
          {"analysis":{"screen_scene_decision":"yes"},"comparison":{"expected":"movie_drama","comparable":True,"correct":True},"costEstimate":{"input_tokens":10,"tool_use_tokens":0,"output_tokens":2,"thought_tokens":3,"rough_paid_usd":0.01}},
          {"analysis":{"screen_scene_decision":"yes"},"comparison":{"expected":"not_movie_drama","comparable":True,"correct":False},"costEstimate":{"input_tokens":20,"tool_use_tokens":0,"output_tokens":2,"thought_tokens":3,"rough_paid_usd":0.02}},
        ]
        s=M.summarize(rows)
        self.assertEqual(s["correct"],1);self.assertEqual(s["falsePositive"],1);self.assertEqual(s["falseNegative"],0)
        self.assertAlmostEqual(s["accuracy"],0.5)

if __name__=="__main__": unittest.main()
