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
        """新管线: 视频走原有姿态/动作链路, 音频整体由 AudioPipeline 编排."""
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
                return [{"time": 0.0, "action": "running", "confidence": 0.8}]

        class FakeAudioExtractor:
            def __init__(self, sample_rate):
                self.sample_rate = sample_rate

            def extract_from_video(self, video_path, output_path):
                return str(audio_path)

        class FakeAudioPipeline:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def process(self, audio_file, exam_id=None, manual_speaker_role_map=None):
                # 模拟 AudioPipeline 的输出结构
                return {
                    "audio_path": audio_file,
                    "segments": [
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "speaker": "SPEAKER_00",
                            "role": "doctor",
                            "text": "开始胸外按压",
                            "raw_text": "开始胸外按压",
                            "confidence": None,
                            "segment_type": "medical_command",
                        }
                    ],
                    "events": [
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "speaker": "SPEAKER_00",
                            "role": "doctor",
                            "event_type": "compression_start_fast",
                            "text": "开始胸外按压",
                            "rule_code": "compression_start_fast",
                            "rule_name": "及时开始胸外按压",
                            "phase": "phase2_arrival_step1",
                            "similarity": 0.88,
                            "matched_template": "开始胸外按压",
                            "role_correct": True,
                            "extras": {},
                        }
                    ],
                    "speaker_role_map": {"SPEAKER_00": "doctor"},
                    "hotwords": ["胸外按压"],
                    "stats": {
                        "diarization_segments": 1,
                        "merged_segments": 1,
                        "asr_success": 1,
                        "asr_failed": 0,
                        "matched_rules": 1,
                    },
                }

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
                # 验证音频上下文已正确传递到打分引擎
                if not context["voice_matches"]:
                    raise AssertionError("voice_matches 应包含 AudioPipeline 命中的事件")
                if context["voice_matches"][0]["rule_code"] != "compression_start_fast":
                    raise AssertionError("rule_code 应来自 AudioPipeline 的 events")
                if context["transcription"][0]["speaker"] != "SPEAKER_00":
                    raise AssertionError("transcription 应包含 speaker")
                if context["speaker_roles"].get("SPEAKER_00") != "doctor":
                    raise AssertionError("speaker_roles 应被 AudioPipeline 填充")
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
            "ai_engine.audio.audio_pipeline": types.SimpleNamespace(
                AudioPipeline=FakeAudioPipeline
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
            patch.object(
                pipeline_module.ExaminationPipeline,
                "_generate_annotated_video",
                lambda self, *a, **kw: "",
            ),
            patch.dict(sys.modules, module_overrides, clear=False),
        ):
            pipeline = pipeline_module.ExaminationPipeline(progress_callback=callback)
            result = pipeline.process("demo.mp4", {"depth": 1})

        self.assertEqual(result["scores"]["total_score"], 88.5)
        # 视频和音频事件都应在 events 列表里
        sources = [ev.get("source") for ev in result["events"]]
        self.assertIn("video", sources)
        self.assertIn("audio", sources)
        # 新管线返回 audio_result, 包含完整 segments / events / speaker_role_map
        self.assertIn("audio_result", result)
        self.assertEqual(
            result["audio_result"]["speaker_role_map"], {"SPEAKER_00": "doctor"}
        )
        self.assertGreaterEqual(len(cleanup_calls), 2)
        self.assertEqual(progress_events[0]["stage"], "preprocessing")
        self.assertEqual(progress_events[-1]["substep"], "complete")
        # 进度回调应至少出现一次音频管线 substep
        self.assertTrue(
            any(
                event["stage"] == "audio_analysis" for event in progress_events
            )
        )


if __name__ == "__main__":
    unittest.main()
