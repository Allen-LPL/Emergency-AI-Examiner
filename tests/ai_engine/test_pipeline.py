import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import ai_engine.pipeline as pipeline_module


class PipelineTests(unittest.TestCase):
    def test_process_examination_delegates_to_pipeline_process(self):
        seen = {}

        class DummyPipeline:
            def process(self, video_path, sensor_data=None):
                seen["call"] = (video_path, sensor_data)
                return {"ok": True}

        with patch.object(pipeline_module, "ExaminationPipeline", DummyPipeline):
            result = pipeline_module.process_examination("demo.mp4", {"sensor": 1})

        self.assertEqual(seen["call"], ("demo.mp4", {"sensor": 1}))
        self.assertEqual(result, {"ok": True})

    def test_pipeline_reports_progress_and_calls_audio_modules(self):
        progress_events = []
        callback = lambda **kw: progress_events.append(kw)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        audio_path = Path(temp_dir.name) / "exam_audio.wav"
        audio_path.write_bytes(b"wav")

        class FakeExtractor:
            def __init__(self, *args, **kwargs):
                self.calls = []

            def get_video_info(self, video_path):
                return {"duration": 10.0, "fps": 25.0}

            def extract_frames_adaptive(self, video_path, max_frames):
                self.calls.append((video_path, max_frames))
                return [
                    {"frame_idx": 0, "timestamp": 0.0, "frame": "frame-0"},
                    {"frame_idx": 1, "timestamp": 1.0, "frame": "frame-1"},
                ]

        class FakePoseDetector:
            def __init__(self, device="cuda:0", model_path="yolov8n-pose.pt"):
                self.device = device

            def detect_batch(self, frames, progress_fn=None):
                if progress_fn:
                    progress_fn(1, len(frames))
                    progress_fn(len(frames), len(frames))
                return [
                    {
                        "timestamp": 0.0,
                        "persons": [
                            {
                                "bbox": [0, 0, 100, 100],
                                "confidence": 0.9,
                                "keypoints": [[0, 0, 0.9]] * 17,
                            }
                        ],
                    }
                ]

            def release(self):
                return None

        class FakeRecognizer:
            def recognize_from_poses(self, pose_sequence, timestamps):
                self.assertEqual(len(pose_sequence), 1)
                self.assertEqual(timestamps, [0.0])
                return [{"time": 0.0, "action": "running", "confidence": 0.8}]

            def assertEqual(self, left, right):
                if left != right:
                    raise AssertionError(f"{left!r} != {right!r}")

        class FakeAudioExtractor:
            def __init__(self, sample_rate):
                self.sample_rate = sample_rate

            def extract_from_video(self, video_path, output_path):
                return str(audio_path)

        class FakeVAD:
            def detect(self, audio_file):
                return [{"start": 0.0, "end": 1.0}]

        class FakeASR:
            def __init__(self, model_name, device):
                self.model_name = model_name
                self.device = device

            def transcribe(self, audio_file):
                raise AssertionError(
                    "transcribe() should not be used when VAD segments exist"
                )

            def transcribe_segments(self, audio_file, vad_segments):
                if vad_segments != [{"start": 0.0, "end": 1.0}]:
                    raise AssertionError("VAD segments were not passed to ASR")
                return [{"text": "检查意识", "start": 0.0, "end": 1.0}]

        class FakeDiarizer:
            pipeline = object()

            def __init__(self, hf_token, device, max_speakers):
                pass

            def diarize(self, audio_file):
                return [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}]

            def assign_speakers(self, transcription, diarization):
                return [{**transcription[0], "speaker": "SPEAKER_00"}]

        class FakeRoleInferrer:
            def infer_roles(self, transcription):
                return {"SPEAKER_00": "doctor"}

            def apply_roles(self, transcription, roles):
                return [{**transcription[0], "speaker_role": roles["SPEAKER_00"]}]

        class FakeMatcher:
            def match_transcript(self, transcription):
                if transcription[0]["speaker_role"] != "doctor":
                    raise AssertionError(
                        "speaker roles were not applied before matching"
                    )
                return [{"time": 0.0, "rule_code": "R1", "similarity": 0.88}]

        class FakeMerger:
            def merge(self, video_events, audio_events):
                return video_events + audio_events

        class FakeTimeline:
            def __init__(self):
                self.events = []

            def add_events(self, events):
                self.events.extend(events)

            def to_list(self):
                return list(self.events)

        class FakeScoringEngine:
            def score(self, timeline, context):
                if context["voice_matches"] != [
                    {"time": 0.0, "rule_code": "R1", "similarity": 0.88}
                ]:
                    raise AssertionError("voice matches were not forwarded")
                if context["transcription"][0]["speaker"] != "SPEAKER_00":
                    raise AssertionError("speaker labels were not assigned")
                if context["speaker_roles"] != {"SPEAKER_00": "doctor"}:
                    raise AssertionError("speaker roles were not forwarded")
                return {"total_score": 88.5}

        cleanup_calls = []
        module_overrides = {
            "ai_engine.video.extractor": types.SimpleNamespace(
                FrameExtractor=FakeExtractor
            ),
            "ai_engine.video.pose_detector": types.SimpleNamespace(
                PoseDetector=FakePoseDetector
            ),
            "ai_engine.video.action_recognizer": types.SimpleNamespace(
                ActionRecognizer=FakeRecognizer
            ),
            "ai_engine.audio.extractor": types.SimpleNamespace(
                AudioExtractor=FakeAudioExtractor
            ),
            "ai_engine.audio.vad": types.SimpleNamespace(VoiceActivityDetector=FakeVAD),
            "ai_engine.audio.asr": types.SimpleNamespace(SpeechRecognizer=FakeASR),
            "ai_engine.audio.diarizer": types.SimpleNamespace(
                SpeakerDiarizer=FakeDiarizer
            ),
            "ai_engine.audio.role_inferrer": types.SimpleNamespace(
                SpeakerRoleInferrer=FakeRoleInferrer
            ),
            "ai_engine.audio.template_matcher": types.SimpleNamespace(
                TemplateMatcher=FakeMatcher
            ),
            "ai_engine.fusion.event_merger": types.SimpleNamespace(
                EventMerger=FakeMerger
            ),
            "ai_engine.fusion.timeline": types.SimpleNamespace(Timeline=FakeTimeline),
            "ai_engine.scoring.engine": types.SimpleNamespace(
                ScoringEngine=FakeScoringEngine
            ),
            "backend.app.services.report_service": types.SimpleNamespace(
                generate_html_report=lambda exam_id, score_result: "<html />"
            ),
        }

        with (
            patch.object(
                pipeline_module.ExaminationPipeline,
                "_cleanup_gpu",
                lambda self: cleanup_calls.append("cleanup"),
            ),
            patch.dict(sys.modules, module_overrides, clear=False),
        ):
            pipeline = pipeline_module.ExaminationPipeline(progress_callback=callback)
            result = pipeline.process("demo.mp4", {"depth": 1})

        self.assertEqual(result["scores"]["total_score"], 88.5)
        self.assertEqual(result["events"][0]["source"], "video")
        self.assertEqual(result["events"][1]["source"], "audio")
        self.assertEqual(cleanup_calls, ["cleanup", "cleanup"])
        self.assertEqual(progress_events[0]["stage"], "preprocessing")
        self.assertEqual(progress_events[-1]["substep"], "complete")
        self.assertTrue(
            any(event["substep"] == "role_inference" for event in progress_events)
        )
        self.assertTrue(
            any(event["substep"] == "template_matching" for event in progress_events)
        )


if __name__ == "__main__":
    unittest.main()
