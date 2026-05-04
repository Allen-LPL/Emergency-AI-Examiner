import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_template_matcher_class():
    module_path = (
        Path(__file__).resolve().parents[3]
        / "ai_engine"
        / "audio"
        / "template_matcher.py"
    )
    spec = spec_from_file_location("test_template_matcher_module", module_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TemplateMatcher


TemplateMatcher = _load_template_matcher_class()


class TemplateMatcherTests(unittest.TestCase):
    def test_match_transcript_returns_best_match_and_role_status(self):
        matcher = TemplateMatcher(
            templates={
                "inform_family": {
                    "templates": ["患者心跳骤停，我们需要立即进行抢救"],
                    "expected_role": "doctor",
                    "phase": "phase2_arrival_step1",
                    "rule_code": "inform_family",
                    "rule_name": "口头告知病情",
                    "max_score": 1,
                },
                "iv_access": {
                    "templates": ["开通静脉通路"],
                    "expected_role": None,
                    "phase": "phase4_arrival_step3",
                    "rule_code": "iv_access",
                    "rule_name": "开通静脉通路",
                    "max_score": 2,
                },
            },
            min_similarity=0.3,
        )

        transcription = [
            {
                "start": 1.5,
                "end": 3.0,
                "text": "患者心跳骤停我们现在立即抢救",
                "speaker": "SPEAKER_00",
                "speaker_role": "doctor",
            },
            {
                "start": 3.0,
                "end": 4.0,
                "text": "静脉通路已经开通",
                "speaker": "SPEAKER_01",
                "speaker_role": "nurse",
            },
        ]

        matches = matcher.match_transcript(transcription)
        matches_by_code = {match["rule_code"]: match for match in matches}

        self.assertEqual(len(matches), 2)
        self.assertEqual(matches_by_code["inform_family"]["speaker_role"], "doctor")
        self.assertTrue(matches_by_code["inform_family"]["role_correct"])
        self.assertEqual(matches_by_code["inform_family"]["time"], 1.5)
        self.assertEqual(matches_by_code["iv_access"]["speaker_role"], "nurse")
        self.assertTrue(matches_by_code["iv_access"]["role_correct"])
        self.assertGreater(matches_by_code["inform_family"]["similarity"], 0.3)

    def test_match_transcript_marks_role_mismatch(self):
        matcher = TemplateMatcher(
            templates={
                "clear_before_defib": {
                    "templates": ["所有人离开，准备除颤"],
                    "expected_role": "doctor",
                    "phase": "phase4_arrival_step3",
                    "rule_code": "clear_before_defib",
                    "rule_name": "除颤前旁人离开",
                    "max_score": 2,
                }
            },
            min_similarity=0.3,
        )

        transcription = [
            {
                "start": 5.0,
                "end": 6.0,
                "text": "所有人离开准备除颤",
                "speaker": "SPEAKER_01",
                "speaker_role": "nurse",
            }
        ]

        matches = matcher.match_transcript(transcription)

        self.assertEqual(len(matches), 1)
        self.assertFalse(matches[0]["role_correct"])


if __name__ == "__main__":
    unittest.main()
