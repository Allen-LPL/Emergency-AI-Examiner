from loguru import logger


class EventMerger:
    """统一事件融合器: 将视频/音频/传感器三路事件合并为按时间排序的统一事件流。

    关键约定: 输入的 video_events 已经被 pipeline._process_video 标准化, 即每条
    都形如 {time, event_type, source, confidence, data}; 同理 audio_events 也已
    在 pipeline._process_audio / _build_transcript_events 中标准化. 因此本类只
    做"取已标准化字段 + 兜底"的工作, 不要再去 raw event 里翻 'action' 字段,
    否则会把 event_type 抹成 'unknown', 导致 scoring 规则全部命中失败.
    """

    def merge(
        self,
        video_events: list[dict],
        audio_events: list[dict],
        sensor_events: list[dict] | None = None,
    ) -> list[dict]:
        unified = []

        for ev in video_events:
            # 注意: ev 已经是 pipeline 包装后的字典, 直接取 event_type
            # 兜底链: event_type → data.action → 'unknown'
            data = ev.get("data") or {}
            event_type = (
                ev.get("event_type")
                or (data.get("action") if isinstance(data, dict) else None)
                or "unknown"
            )
            unified.append(
                {
                    "time": ev.get("time", 0.0),
                    "actor": ev.get("actor")
                    or (data.get("actor_track_id") if isinstance(data, dict) else None),
                    "event_type": event_type,
                    "source": "video",
                    "confidence": ev.get("confidence", 0.5),
                    "data": data if isinstance(data, dict) else {"raw": data},
                }
            )

        for ev in audio_events:
            data = ev.get("data") or {}
            # 音频事件优先取 event_type (pipeline 已写入 rule_code 或 transcript 类型)
            # 不再退化到 raw 'rule_code', 因为这会把 'audio_transcript_segment' 抹掉
            event_type = ev.get("event_type") or ev.get("rule_code") or "voice_command"
            unified.append(
                {
                    "time": ev.get("time", 0.0),
                    "actor": ev.get("actor")
                    or (data.get("speaker") if isinstance(data, dict) else None),
                    "event_type": event_type,
                    "source": "audio",
                    "confidence": ev.get("confidence", ev.get("similarity", 0.9)),
                    "data": data if isinstance(data, dict) else {"raw": data},
                }
            )

        if sensor_events:
            for ev in sensor_events:
                unified.append(
                    {
                        "time": ev.get("time", 0.0),
                        "actor": ev.get("actor"),
                        "event_type": ev.get("event_type", "sensor_reading"),
                        "source": "sensor",
                        "confidence": ev.get("confidence", 1.0),
                        "data": ev,
                    }
                )

        unified.sort(key=lambda e: e["time"])
        logger.info(
            f"Merged {len(video_events)} video + {len(audio_events)} audio "
            f"+ {len(sensor_events or [])} sensor = {len(unified)} events"
        )
        return unified
