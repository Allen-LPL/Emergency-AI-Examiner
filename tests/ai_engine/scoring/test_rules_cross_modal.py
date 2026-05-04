import unittest

from ai_engine.fusion.timeline import Timeline
from ai_engine.scoring.rules.base import ScoringRule
from ai_engine.scoring.rules.phase1_before_arrival import (
    CarryBreathingBag,
    CarryDefibrillator,
    CarryMedicineBox,
    EnvironmentSafety,
)
from ai_engine.scoring.rules.phase2_arrival_step1 import (
    EquipmentPlacement,
    InformFamily,
)
from ai_engine.scoring.rules.phase3_arrival_step2 import BreathingBagPrep, ECGConnection
from ai_engine.scoring.rules.phase4_arrival_step3 import (
    ApplyConductivePaste,
    CooperationSmooth,
    EnergyCorrect,
    EvaluateRhythm,
    PastePositionCorrect,
)
from ai_engine.scoring.rules.phase5_arrival_step4 import CompressionHandover
from ai_engine.scoring.rules.phase6_arrival_step5 import (
    BodyCameraWarning,
    HumanisticCare,
    ScoopStretcherTransfer,
)


class DummyVoiceRule(ScoringRule):
    rule_code = "dummy_rule"
    rule_name = "测试规则"
    phase = "phase_test"
    max_score = 2.0

    def evaluate(self, timeline: Timeline, context: dict) -> dict:
        score, match = self._compute_voice_score(context)
        found, event = self._check_video_confirm(
            timeline,
            event_type="kneeling",
            audio_time=match["time"] if match else 0.0,
            window=5.0,
        )
        evidence = {"match": match, "video_found": found, "video_event": event}
        return self._result(score, evidence=evidence)


class CrossModalRuleTests(unittest.TestCase):
    def test_base_helpers_scale_voice_score_and_attach_video_confirmation(self):
        timeline = Timeline()
        timeline.add_event(13.0, "kneeling", "video")
        context = {
            "voice_matches": [
                {
                    "rule_code": "dummy_rule",
                    "time": 10.0,
                    "similarity": 0.75,
                    "role_correct": False,
                    "speaker_role": "assistant",
                }
            ]
        }

        result = DummyVoiceRule().evaluate(timeline, context)

        self.assertEqual(result["actual_score"], 1.2)
        self.assertTrue(result["evidence"]["video_found"])
        self.assertEqual(result["evidence"]["video_event"]["time"], 13.0)

    def test_phase1_device_rules_default_to_full_score(self):
        timeline = Timeline()

        for rule in [CarryDefibrillator(), CarryMedicineBox(), CarryBreathingBag()]:
            with self.subTest(rule=rule.rule_code):
                result = rule.evaluate(timeline, {})
                self.assertEqual(result["actual_score"], rule.max_score)
                self.assertIn("自动满分", result["evidence"]["note"])

    def test_environment_safety_uses_similarity_score_and_evidence(self):
        rule = EnvironmentSafety()
        context = {
            "voice_matches": [
                {
                    "rule_code": "environment_safety",
                    "similarity": 0.8,
                    "matched_text": "现场安全",
                    "speaker_role": "doctor",
                    "role_correct": True,
                }
            ]
        }

        result = rule.evaluate(Timeline(), context)

        self.assertEqual(result["actual_score"], 0.8)
        self.assertEqual(result["evidence"]["matched_text"], "现场安全")
        self.assertIsNone(result["deduction_reason"])

    def test_equipment_placement_defaults_to_full_score(self):
        result = EquipmentPlacement().evaluate(Timeline(), {})

        self.assertEqual(result["actual_score"], 1.0)
        self.assertIn("自动满分", result["evidence"]["note"])

    def test_inform_family_applies_similarity_score_within_time_limit(self):
        timeline = Timeline()
        timeline.add_event(2.0, "equipment_placement", "video")
        context = {
            "voice_matches": [
                {
                    "rule_code": "inform_family",
                    "time": 10.0,
                    "similarity": 0.9,
                    "role_correct": True,
                    "matched_text": "患者需要立即抢救",
                }
            ]
        }

        result = InformFamily().evaluate(timeline, context)

        self.assertEqual(result["actual_score"], 0.9)
        self.assertAlmostEqual(result["evidence"]["time_diff"], 8.0)

    def test_inform_family_fails_when_audio_time_exceeds_limit(self):
        timeline = Timeline()
        timeline.add_event(1.0, "equipment_placement", "video")
        context = {
            "voice_matches": [
                {
                    "rule_code": "inform_family",
                    "time": 30.5,
                    "similarity": 0.95,
                    "role_correct": True,
                }
            ]
        }

        result = InformFamily().evaluate(timeline, context)

        self.assertEqual(result["actual_score"], 0.0)
        self.assertIn("超时", result["deduction_reason"])

    def test_breathing_bag_prep_uses_sensor_and_video_confirmation_as_evidence(self):
        timeline = Timeline()
        timeline.add_event(16.0, "ventilation_pose", "video")
        context = {
            "sensor_data": {"ventilation_volume_ml": 550, "ventilation_time": 15.0}
        }

        result = BreathingBagPrep().evaluate(timeline, context)

        self.assertEqual(result["actual_score"], 3.0)
        self.assertTrue(result["evidence"]["video_confirmed"])
        self.assertEqual(
            result["evidence"]["video_event"]["event_type"], "ventilation_pose"
        )

    def test_ecg_connection_uses_voice_similarity_and_video_auxiliary_evidence(self):
        timeline = Timeline()
        timeline.add_event(25.0, "ecg_connection", "video")
        context = {
            "voice_matches": [
                {
                    "rule_code": "ecg_connection",
                    "time": 24.0,
                    "similarity": 0.8,
                    "role_correct": True,
                    "matched_text": "连接心电监护",
                }
            ]
        }

        result = ECGConnection().evaluate(timeline, context)

        self.assertEqual(result["actual_score"], 2.4)
        self.assertTrue(result["evidence"]["video_confirmed"])

    def test_phase4_default_rules_and_voice_rules_follow_new_pattern(self):
        timeline = Timeline()
        timeline.add_event(40.0, "kneeling", "video")
        evaluate_context = {
            "voice_matches": [
                {
                    "rule_code": "evaluate_rhythm",
                    "time": 39.0,
                    "similarity": 0.7,
                    "role_correct": True,
                },
                {
                    "rule_code": "energy_correct",
                    "time": 45.0,
                    "similarity": 0.9,
                    "role_correct": True,
                    "matched_text": "200焦准备除颤",
                },
            ]
        }

        evaluate_result = EvaluateRhythm().evaluate(timeline, evaluate_context)
        self.assertEqual(evaluate_result["actual_score"], 1.4)
        self.assertTrue(evaluate_result["evidence"]["video_confirmed"])

        energy_result = EnergyCorrect().evaluate(timeline, evaluate_context)
        self.assertEqual(energy_result["actual_score"], 1.8)

        for rule in [
            ApplyConductivePaste(),
            PastePositionCorrect(),
            CooperationSmooth(),
        ]:
            with self.subTest(rule=rule.rule_code):
                result = rule.evaluate(Timeline(), {})
                self.assertEqual(result["actual_score"], rule.max_score)
                self.assertIn("自动", result["evidence"]["note"])

    def test_phase5_and_phase6_rules_use_new_defaults_and_voice_scores(self):
        timeline = Timeline()
        timeline.add_event(60.0, "standing_nearby", "video")
        context = {
            "voice_matches": [
                {
                    "rule_code": "compression_handover",
                    "time": 59.0,
                    "similarity": 0.85,
                    "role_correct": True,
                },
                {
                    "rule_code": "humanistic_care",
                    "time": 75.0,
                    "similarity": 0.6,
                    "role_correct": True,
                },
            ]
        }

        handover_result = CompressionHandover().evaluate(timeline, context)
        self.assertEqual(handover_result["actual_score"], 1.7)
        self.assertTrue(handover_result["evidence"]["video_confirmed"])

        humanistic_result = HumanisticCare().evaluate(timeline, context)
        self.assertEqual(humanistic_result["actual_score"], 0.6)

        for rule in [ScoopStretcherTransfer(), BodyCameraWarning()]:
            with self.subTest(rule=rule.rule_code):
                result = rule.evaluate(Timeline(), {})
                self.assertEqual(result["actual_score"], rule.max_score)
                self.assertIn("默认", result["evidence"]["note"])


if __name__ == "__main__":
    unittest.main()
