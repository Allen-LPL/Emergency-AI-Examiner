# pyright: reportMissingImports=false
import gc
from pathlib import Path

from loguru import logger

from ai_engine.config import AIEngineConfig, get_ai_config


class ExaminationPipeline:
    def __init__(self, config: AIEngineConfig | None = None, progress_callback=None):
        self.config = config or get_ai_config()
        self._cb = progress_callback or (lambda **kw: None)

    def _report(self, progress: int, stage: str, substep: str, detail: str = ""):
        self._cb(progress=progress, stage=stage, substep=substep, detail=detail)

    def process(self, video_path: str, sensor_data: dict | None = None) -> dict:
        logger.info(f"Starting examination: {video_path}")

        self._report(1, "preprocessing", "video_info", "提取视频信息...")
        from ai_engine.video.extractor import FrameExtractor

        extractor = FrameExtractor(target_fps=self.config.video_fps)
        video_info = extractor.get_video_info(video_path)
        duration = video_info.get("duration", 0)
        logger.info(f"Video: {duration:.1f}s, {video_info.get('fps', 0):.1f}fps")

        self._report(3, "preprocessing", "audio_extract", "分离音频轨道...")
        audio_path = self._extract_audio(video_path)

        self._report(
            5,
            "video_analysis",
            "frame_sampling",
            f"自适应采样 (目标≤{self.config.max_total_frames}帧)...",
        )
        frames = extractor.extract_frames_adaptive(
            video_path, self.config.max_total_frames
        )
        total_frames = len(frames)
        target_fps = total_frames / duration if duration > 0 else 1.0
        logger.info(f"Sampled {total_frames} frames at ~{target_fps:.2f}fps")

        video_events, frame_results, raw_action_events = self._process_video(
            frames, total_frames
        )
        self._cleanup_gpu()

        audio_events, voice_matches, transcription, audio_result = self._process_audio(
            audio_path
        )
        transcript_events = self._build_transcript_events(transcription)
        self._cleanup_gpu()

        self._report(70, "fusion", "merge_events", "合并视频+音频事件...")
        from ai_engine.fusion.event_merger import EventMerger
        from ai_engine.fusion.timeline import Timeline

        merger = EventMerger()
        all_events = merger.merge(video_events, audio_events + transcript_events)
        timeline = Timeline()
        timeline.add_events(all_events)
        self._report(
            82,
            "fusion",
            "build_timeline",
            f"统一时间轴构建完成 ({len(all_events)}个事件)",
        )

        self._report(85, "scoring", "rule_engine", "6阶段规则引擎评分...")
        context = {
            "voice_matches": voice_matches,
            "detected_equipment": [],
            "sensor_data": sensor_data or {},
            "transcription": transcription,
            "speaker_roles": {
                seg.get("speaker"): seg.get("speaker_role")
                for seg in transcription
                if seg.get("speaker")
            },
        }
        from ai_engine.scoring.engine import ScoringEngine

        engine = ScoringEngine()
        score_result = engine.score(timeline, context)

        self._report(93, "scoring", "report_gen", "生成评分报告...")
        from backend.app.services.report_service import generate_html_report

        report_html = generate_html_report(exam_id=0, score_result=score_result)

        # 生成标注视频: 叠加姿态骨架、关键点、动作标签、语音字幕
        processed_video_path = self._generate_annotated_video(
            video_path, frame_results, raw_action_events, transcription
        )
        self._cleanup_gpu()

        self._report(
            99,
            "scoring",
            "complete",
            f"评分完成: {score_result['total_score']:.1f}/100",
        )
        logger.info(f"Processing complete. Score: {score_result['total_score']}/100")

        return {
            "events": all_events,
            "scores": score_result,
            "timeline": timeline.to_list(),
            "report_html": report_html,
            "processed_video_path": processed_video_path,
            # 完整音频管线输出, 供 backend 持久化 transcripts / speaker_role_map / JSON
            "audio_result": audio_result,
        }

    def _build_transcript_events(self, transcription: list[dict]) -> list[dict]:
        events = []

        role_text_map: dict[str, list[str]] = {}
        for seg in transcription:
            role = (seg.get("speaker_role") or "unknown").strip() or "unknown"
            text = (seg.get("text") or "").strip()
            if text:
                role_text_map.setdefault(role, []).append(text)

            events.append(
                {
                    "time": seg.get("start", 0.0),
                    "event_type": "audio_transcript_segment",
                    "source": "audio",
                    "actor": seg.get("speaker"),
                    "confidence": seg.get("confidence", 1.0),
                    "data": {
                        "start": seg.get("start", 0.0),
                        "end": seg.get("end", 0.0),
                        "text": text,
                        "speaker": seg.get("speaker"),
                        "speaker_role": role,
                    },
                }
            )

        if transcription:
            full_text = " ".join(
                (seg.get("text") or "").strip()
                for seg in transcription
                if (seg.get("text") or "").strip()
            )
            role_text = {role: " ".join(texts) for role, texts in role_text_map.items()}
            events.append(
                {
                    "time": transcription[0].get("start", 0.0),
                    "event_type": "audio_transcript_full",
                    "source": "audio",
                    "actor": None,
                    "confidence": 1.0,
                    "data": {
                        "text": full_text,
                        "role_text": role_text,
                    },
                }
            )

        return events

    def _process_video(
        self, frames: list[dict], total_frames: int
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """
        视频分析管线: 姿态检测 → 多人跟踪 → 动作识别

        Returns:
            (pipeline_events, frame_results, raw_action_events)
            - pipeline_events: 供融合/评分使用的标准事件列表
            - frame_results: 逐帧姿态检测原始结果，供视频标注使用
            - raw_action_events: 动作识别原始事件，供视频标注使用
        """
        empty_result: tuple[list[dict], list[dict], list[dict]] = ([], [], [])

        try:
            from ai_engine.video.pose_detector import PoseDetector
        except ImportError as exc:
            logger.warning(f"PoseDetector unavailable: {exc}")
            return empty_result

        device = self.config.device
        try:
            detector = PoseDetector(device=device)
        except Exception as exc:
            logger.warning(f"PoseDetector init failed ({exc}), trying CPU")
            try:
                detector = PoseDetector(device="cpu")
            except Exception as cpu_exc:
                logger.error(f"PoseDetector unavailable: {cpu_exc}")
                return empty_result

        def frame_progress(done, total):
            if total <= 0:
                pct = 10
            else:
                pct = 10 + int(25 * done / total)
            self._report(
                pct,
                "video_analysis",
                "pose_detection",
                f"YOLOv8n-pose 检测+骨架 ({done}/{total}帧)",
            )

        self._report(
            10,
            "video_analysis",
            "pose_detection",
            f"YOLOv8n-pose 人体检测+骨架 (0/{total_frames}帧)",
        )

        try:
            frame_results = detector.detect_batch(frames, progress_fn=frame_progress)
        except Exception as exc:
            logger.error(f"Pose detection failed: {exc}")
            detector.release()
            return empty_result

        self._report(35, "video_analysis", "tracking", "ByteTrack 多人跟踪...")
        try:
            from ai_engine.video.tracker import PersonTracker  # noqa: F401
        except Exception:
            pass

        self._report(
            40, "video_analysis", "action_recognition", "动作识别: 按压/通气/跑步..."
        )
        events = []
        raw_action_events: list[dict] = []
        try:
            from ai_engine.video.action_recognizer import ActionRecognizer

            recognizer = ActionRecognizer()
            pose_sequence = []
            timestamps = []
            for frame_result in frame_results:
                for person in frame_result["persons"]:
                    pose_sequence.append(
                        {
                            "keypoints": person["keypoints"],
                            "bbox": person["bbox"],
                            "confidence": person["confidence"],
                            "track_id": None,
                        }
                    )
                    timestamps.append(frame_result["timestamp"])

            if pose_sequence:
                raw_action_events = recognizer.recognize_from_poses(
                    pose_sequence, timestamps
                )
                for event in raw_action_events:
                    events.append(
                        {
                            "time": event["time"],
                            "event_type": event.get("action", "unknown"),
                            "source": "video",
                            "confidence": event.get("confidence", 0.5),
                            "data": event,
                        }
                    )
        except Exception as exc:
            logger.error(f"Action recognition failed: {exc}")
        finally:
            detector.release()

        logger.info(f"Video analysis: {len(events)} events detected")
        return events, frame_results, raw_action_events

    def _process_audio(
        self, audio_path: str
    ) -> tuple[list[dict], list[dict], list[dict], dict]:
        """音频处理管线 (新版): AudioPipeline 统一编排.

        AudioPipeline 内部顺序为:
            预处理 → diarization (pyannote 3.1) → 段合并 → ASR (Paraformer-large)
            → 文本清洗 → 领域纠错 → 段类型分类 → 角色绑定 → 话术模板匹配

        Returns:
            (audio_events, voice_matches, transcription, audio_result)
            - audio_events: 供 EventMerger 融合用 (event_type=rule_code, source=audio)
            - voice_matches: scoring engine 上下文用 (兼容旧字段名 time/score/similarity)
            - transcription: 供 video_annotator 字幕渲染用 (text/speaker/speaker_role/start/end)
            - audio_result: AudioPipeline 原始输出, 供 transcript 持久化使用
        """
        if not audio_path or not Path(audio_path).exists():
            logger.warning("音频文件不存在，跳过音频分析")
            return [], [], [], {}

        device = self.config.device

        # 阶段进度: 46 ~ 68 留给整个音频管线. AudioPipeline 内部分多个子步骤,
        # 这里只在入口和出口报告, 避免过度刷屏.
        self._report(
            46,
            "audio_analysis",
            "audio_pipeline_start",
            "启动音频管线: pyannote 3.1 + Paraformer-large...",
        )

        try:
            from ai_engine.audio.audio_pipeline import AudioPipeline

            pipeline = AudioPipeline(
                hf_token=self.config.hf_token or None,
                device=device,
                num_speakers=min(self.config.max_speakers, 3),
                sample_rate=self.config.sample_rate,
                vad_model=self.config.vad_model,
            )
            audio_result = pipeline.process(audio_path)
        except Exception as exc:
            logger.exception(f"音频管线执行失败: {exc}")
            return [], [], [], {}

        # 把 AudioPipeline 的输出投影成下游模块需要的旧字段名
        segments = audio_result.get("segments", [])
        audio_pipeline_events = audio_result.get("events", [])

        # 1) audio_events: 供 EventMerger 融合
        audio_events: list[dict] = []
        for ev in audio_pipeline_events:
            audio_events.append(
                {
                    "time": ev.get("start", 0.0),
                    "event_type": ev.get("rule_code") or ev.get("event_type"),
                    "source": "audio",
                    "actor": ev.get("speaker"),
                    "confidence": ev.get("similarity", 0.5),
                    "data": ev,
                }
            )

        # 2) voice_matches: scoring engine 用 (兼容旧字段)
        voice_matches: list[dict] = []
        for ev in audio_pipeline_events:
            voice_matches.append(
                {
                    "time": ev.get("start", 0.0),
                    "end": ev.get("end", 0.0),
                    "rule_code": ev.get("rule_code"),
                    "rule_name": ev.get("rule_name"),
                    "phase": ev.get("phase"),
                    "score": 1.0,  # scoring engine 自己给 max_score, 这里只标记命中
                    "similarity": ev.get("similarity", 0.0),
                    "matched_text": ev.get("text", ""),
                    "matched_template": ev.get("matched_template", ""),
                    "speaker": ev.get("speaker"),
                    "speaker_role": ev.get("role"),
                    "role_correct": ev.get("role_correct", True),
                }
            )

        # 3) transcription: 兼容旧 dict 形态, 给 video_annotator 字幕用
        transcription: list[dict] = []
        for seg in segments:
            transcription.append(
                {
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "text": seg.get("text", ""),
                    "speaker": seg.get("speaker"),
                    "speaker_role": seg.get("role") or "unknown",
                    "confidence": seg.get("confidence", 1.0),
                    "segment_type": seg.get("segment_type"),
                }
            )

        stats = audio_result.get("stats", {})
        self._report(
            68,
            "audio_analysis",
            "complete",
            (
                f"音频分析完成: 转写={stats.get('asr_success', 0)}有效/"
                f"{stats.get('asr_failed', 0)}无效, "
                f"角色={len(audio_result.get('speaker_role_map', {}))}, "
                f"话术命中={stats.get('matched_rules', 0)}"
            ),
        )
        return audio_events, voice_matches, transcription, audio_result

    def _generate_annotated_video(
        self,
        video_path: str,
        frame_results: list[dict],
        action_events: list[dict],
        transcription: list[dict],
    ) -> str:
        """生成带有姿态骨架、关键点、动作标签和语音字幕的标注视频。

        前置条件: frame_results 非空 (至少有一帧检测到了人体), 否则没有可叠加的内容,
        直接跳过. 所有失败分支都会用 logger.exception 输出完整堆栈, 方便排查.
        """
        # 函数入口先打印一条 INFO, 即便后续被前置条件短路, 也能在日志中确认本步骤被调用
        logger.info(
            f"【标注视频】开始生成: video={video_path}, "
            f"检测帧={len(frame_results)}, 动作事件={len(action_events)}, "
            f"转写段={len(transcription)}"
        )

        if not frame_results:
            logger.warning(
                "【标注视频】frame_results 为空, 跳过标注视频生成 "
                "(通常是姿态检测全部失败或视频中无人体)"
            )
            return ""

        self._report(95, "video_annotation", "rendering", "渲染标注视频...")

        # 使用绝对路径写出, 避免 worker 容器与 api 容器工作目录差异导致 api 找不到文件
        output_dir = Path(self.config.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        video_stem = Path(video_path).stem
        output_path = str(output_dir / f"{video_stem}_annotated.mp4")
        logger.info(f"【标注视频】目标输出路径: {output_path}")

        try:
            from ai_engine.video.video_annotator import VideoAnnotator

            annotator = VideoAnnotator(
                keypoint_threshold=self.config.pose_keypoint_threshold,
            )

            def annotation_progress(done, total):
                if total <= 0:
                    return
                pct = 95 + int(3 * done / total)
                self._report(
                    pct,
                    "video_annotation",
                    "rendering",
                    f"渲染标注视频帧 ({done}/{total})",
                )

            result_path = annotator.generate(
                video_path=video_path,
                output_path=output_path,
                frame_results=frame_results,
                action_events=action_events,
                transcription=transcription,
                progress_fn=annotation_progress,
            )

            # 写盘成功后打印文件大小, 一眼即可判断是否真实落盘
            try:
                size_mb = Path(result_path).stat().st_size / (1024 * 1024)
                logger.info(
                    f"【标注视频】生成完成: {result_path} ({size_mb:.2f} MB)"
                )
            except OSError:
                logger.info(f"【标注视频】生成完成: {result_path} (无法读取大小)")
            return result_path
        except Exception as exc:
            # 关键: 用 logger.exception 暴露完整 Python 堆栈
            logger.exception(f"【标注视频】生成失败: {exc}")
            return ""

    def _extract_audio(self, video_path: str) -> str:
        try:
            from ai_engine.audio.extractor import AudioExtractor

            extractor = AudioExtractor(sample_rate=self.config.sample_rate)
            audio_dir = Path(video_path).parent
            audio_out = str(audio_dir / "exam_audio.wav")
            return extractor.extract_from_video(video_path, audio_out)
        except Exception as exc:
            logger.error(f"Audio extraction failed: {exc}")
            return ""

    def _cleanup_gpu(self):
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("GPU cache cleared")
        except ImportError:
            pass


def process_examination(video_path: str, sensor_data: dict | None = None) -> dict:
    pipeline = ExaminationPipeline()
    return pipeline.process(video_path, sensor_data)
