from pathlib import Path

from loguru import logger

from ai_engine.config import AIEngineConfig, get_ai_config


class ExaminationPipeline:
    def __init__(self, config: AIEngineConfig | None = None):
        self.config = config or get_ai_config()
        self._video_modules = None
        self._audio_modules = None

    def _init_video(self):
        if self._video_modules is not None:
            return
        try:
            from ai_engine.video.action_recognizer import ActionRecognizer
            from ai_engine.video.detector import ObjectDetector
            from ai_engine.video.extractor import FrameExtractor
            from ai_engine.video.pose_estimator import PoseEstimator
            from ai_engine.video.tracker import PersonTracker

            self._video_modules = {
                "extractor": FrameExtractor(target_fps=self.config.video_fps),
                "detector": ObjectDetector(
                    model_path=self.config.yolo_model,
                    device=self.config.device,
                    conf_threshold=self.config.yolo_conf_threshold,
                ),
                "tracker": PersonTracker(
                    model_path=self.config.yolo_model, device=self.config.device
                ),
                "pose": PoseEstimator(device=self.config.device),
                "action": ActionRecognizer(),
            }
            logger.info("Video modules initialized")
        except Exception as e:
            logger.warning(f"Video modules unavailable: {e}")
            self._video_modules = {}

    def _init_audio(self):
        if self._audio_modules is not None:
            return
        try:
            from ai_engine.audio.asr import SpeechRecognizer
            from ai_engine.audio.diarizer import SpeakerDiarizer
            from ai_engine.audio.extractor import AudioExtractor
            from ai_engine.audio.keyword_matcher import KeywordMatcher
            from ai_engine.audio.vad import VoiceActivityDetector

            self._audio_modules = {
                "extractor": AudioExtractor(sample_rate=self.config.sample_rate),
                "vad": VoiceActivityDetector(),
                "asr": SpeechRecognizer(
                    model_name=self.config.asr_model, device=self.config.device
                ),
                "diarizer": SpeakerDiarizer(
                    hf_token=self.config.hf_token,
                    device=self.config.device,
                    max_speakers=self.config.max_speakers,
                ),
                "keyword": KeywordMatcher(),
            }
            logger.info("Audio modules initialized")
        except Exception as e:
            logger.warning(f"Audio modules unavailable: {e}")
            self._audio_modules = {}

    def process_examination(
        self, video_path: str, sensor_data: dict | None = None
    ) -> dict:
        logger.info(f"Starting examination processing: {video_path}")

        from ai_engine.fusion.event_merger import EventMerger
        from ai_engine.fusion.timeline import Timeline
        from ai_engine.scoring.engine import ScoringEngine

        self._init_video()
        self._init_audio()

        video_events = self._process_video(video_path)
        audio_events, voice_matches, transcription = self._process_audio(video_path)

        merger = EventMerger()
        all_events = merger.merge(video_events, audio_events)

        timeline = Timeline()
        timeline.add_events(all_events)

        detected_equipment = []
        if self._video_modules and "detector" in self._video_modules:
            detected_equipment = self._detect_equipment_summary(video_path)

        context = {
            "voice_matches": voice_matches,
            "detected_equipment": detected_equipment,
            "sensor_data": sensor_data or {},
            "transcription": transcription,
        }

        engine = ScoringEngine()
        score_result = engine.score(timeline, context)

        from backend.app.services.report_service import generate_html_report

        report_html = generate_html_report(exam_id=0, score_result=score_result)

        logger.info(f"Processing complete. Score: {score_result['total_score']}/100")
        return {
            "events": all_events,
            "scores": score_result,
            "timeline": timeline.to_list(),
            "report_html": report_html,
        }

    def _process_video(self, video_path: str) -> list[dict]:
        if not self._video_modules:
            logger.warning("Video modules unavailable, skipping video analysis")
            return []

        extractor = self._video_modules.get("extractor")
        tracker = self._video_modules.get("tracker")
        pose = self._video_modules.get("pose")
        action = self._video_modules.get("action")

        if not all([extractor, tracker, pose, action]):
            return []

        try:
            frames = extractor.extract_frames(video_path)
        except Exception as e:
            logger.error(f"Frame extraction failed: {e}")
            return []

        pose_sequence = []
        timestamps = []

        for frame_data in frames:
            frame = frame_data["frame"]
            timestamp = frame_data["timestamp"]

            try:
                tracked = tracker.track(frame)
                poses = pose.estimate(frame)

                for p in poses:
                    pose_sequence.append(
                        {
                            "keypoints": p["keypoints"],
                            "bbox": p["bbox"],
                            "confidence": p["confidence"],
                            "track_id": tracked[0]["track_id"] if tracked else None,
                        }
                    )
                    timestamps.append(timestamp)
            except Exception as e:
                logger.debug(f"Frame {frame_data['frame_idx']} processing error: {e}")

        if not pose_sequence:
            return []

        try:
            events = action.recognize_from_poses(pose_sequence, timestamps)
            return events
        except Exception as e:
            logger.error(f"Action recognition failed: {e}")
            return []

    def _process_audio(
        self, video_path: str
    ) -> tuple[list[dict], list[dict], list[dict]]:
        if not self._audio_modules:
            logger.warning("Audio modules unavailable, skipping audio analysis")
            return [], [], []

        extractor = self._audio_modules.get("extractor")
        vad = self._audio_modules.get("vad")
        asr = self._audio_modules.get("asr")
        diarizer = self._audio_modules.get("diarizer")
        keyword = self._audio_modules.get("keyword")

        if not all([extractor, asr, keyword]):
            return [], [], []

        try:
            audio_dir = Path(video_path).parent
            audio_path = extractor.extract_from_video(
                video_path, str(audio_dir / "exam_audio.wav")
            )
        except Exception as e:
            logger.error(f"Audio extraction failed: {e}")
            return [], [], []

        transcription = []
        try:
            transcription = asr.transcribe(audio_path)
        except Exception as e:
            logger.error(f"ASR failed: {e}")

        if diarizer:
            try:
                diarization = diarizer.diarize(audio_path)
                transcription = diarizer.assign_speakers(transcription, diarization)
            except Exception as e:
                logger.warning(f"Diarization failed: {e}")

        voice_matches = []
        audio_events = []
        if keyword and transcription:
            voice_matches = keyword.match_transcript(transcription)
            for match in voice_matches:
                audio_events.append(
                    {
                        "time": match["time"],
                        "event_type": match["rule_code"],
                        "source": "audio",
                        "confidence": 0.9,
                        "data": match,
                    }
                )

        return audio_events, voice_matches, transcription

    def _detect_equipment_summary(self, video_path: str) -> list[dict]:
        extractor = self._video_modules.get("extractor")
        detector = self._video_modules.get("detector")
        if not extractor or not detector:
            return []

        try:
            frames = extractor.extract_frames(video_path)
            all_equipment = []
            seen_classes = set()
            sample_frames = frames[:10]
            for frame_data in sample_frames:
                equipment = detector.detect_equipment(frame_data["frame"])
                for eq in equipment:
                    if eq["class_name"] not in seen_classes:
                        seen_classes.add(eq["class_name"])
                        all_equipment.append(eq)
            return all_equipment
        except Exception as e:
            logger.error(f"Equipment detection failed: {e}")
            return []


def process_examination(video_path: str, sensor_data: dict | None = None) -> dict:
    pipeline = ExaminationPipeline()
    return pipeline.process_examination(video_path, sensor_data)
