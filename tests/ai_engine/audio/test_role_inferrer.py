import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_role_inferrer_class():
    module_path = (
        Path(__file__).resolve().parents[3] / "ai_engine" / "audio" / "role_inferrer.py"
    )
    spec = spec_from_file_location("test_role_inferrer_module", module_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SpeakerRoleInferrer


SpeakerRoleInferrer = _load_role_inferrer_class()


class SpeakerRoleInferrerTests(unittest.TestCase):
    def test_infer_roles_assigns_doctor_nurse_and_driver(self):
        inferrer = SpeakerRoleInferrer()

        transcription = [
            {
                "speaker": "SPEAKER_00",
                "text": "开始按压，建立静脉通路，给予肾上腺素一毫克，评估心律",
            },
            {"speaker": "SPEAKER_00", "text": "准备除颤，能量200焦"},
            {"speaker": "SPEAKER_01", "text": "好的，静脉通路已开通，记录血压"},
            {"speaker": "SPEAKER_01", "text": "导联已连接，氧饱和度正常"},
            {"speaker": "SPEAKER_02", "text": "担架准备好了，马上转运上车"},
        ]

        roles = inferrer.infer_roles(transcription)

        self.assertEqual(roles["SPEAKER_00"], "doctor")
        self.assertEqual(roles["SPEAKER_01"], "nurse")
        self.assertEqual(roles["SPEAKER_02"], "driver")

    def test_apply_roles_marks_unknown_when_speaker_missing(self):
        inferrer = SpeakerRoleInferrer()

        transcription = [
            {"speaker": "SPEAKER_00", "text": "开始按压"},
            {"text": "没有说话人"},
        ]

        updated = inferrer.apply_roles(transcription, {"SPEAKER_00": "doctor"})

        self.assertEqual(updated[0]["speaker_role"], "doctor")
        self.assertEqual(updated[1]["speaker_role"], "unknown")


if __name__ == "__main__":
    unittest.main()
