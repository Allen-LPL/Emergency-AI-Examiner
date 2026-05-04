from loguru import logger


class EventMerger:
    def merge(
        self,
        video_events: list[dict],
        audio_events: list[dict],
        sensor_events: list[dict] | None = None,
    ) -> list[dict]:
        unified = []

        for ev in video_events:
            unified.append(
                {
                    "time": ev.get("time", 0.0),
                    "actor": ev.get("actor_track_id"),
                    "event_type": ev.get("action", "unknown"),
                    "source": "video",
                    "confidence": ev.get("confidence", 0.5),
                    "data": ev,
                }
            )

        for ev in audio_events:
            unified.append(
                {
                    "time": ev.get("time", 0.0),
                    "actor": ev.get("speaker", ev.get("data", {}).get("speaker")),
                    "event_type": ev.get(
                        "rule_code", ev.get("event_type", "voice_command")
                    ),
                    "source": "audio",
                    "confidence": ev.get("confidence", ev.get("similarity", 0.9)),
                    "data": ev.get("data", ev),
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
