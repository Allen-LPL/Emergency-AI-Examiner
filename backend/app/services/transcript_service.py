"""音频时间轴持久化服务.

负责把 AudioPipeline 输出的 segments / speaker_role_map 写入:
    1. 数据库 (ExamTranscript / SpeakerRoleMap 两张表)
    2. JSON 文件 (outputs/exam_{exam_id}_audio_timeline.json), 便于离线 review
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from backend.app.models.transcript import ExamTranscript, SpeakerRoleMap


def save_audio_timeline_sync(
    db_session,
    exam_id: int,
    audio_result: dict[str, Any],
) -> None:
    """把 AudioPipeline.process() 的返回值写入数据库.

    Args:
        db_session: SQLAlchemy 同步 Session (Celery worker 内使用)
        exam_id: 考试 ID
        audio_result: AudioPipeline.process() 返回的 dict
    """
    segments = audio_result.get("segments", [])
    speaker_role_map = audio_result.get("speaker_role_map", {})

    # 写 transcripts
    for seg in segments:
        db_session.add(
            ExamTranscript(
                exam_id=exam_id,
                start_time=float(seg.get("start", 0.0)),
                end_time=float(seg.get("end", 0.0)),
                speaker=seg.get("speaker"),
                role=seg.get("role"),
                text=seg.get("text"),
                segment_type=seg.get("segment_type"),
                confidence=seg.get("confidence"),
            )
        )

    # 写 speaker_role_maps
    for speaker, role in speaker_role_map.items():
        if not speaker or not role:
            continue
        db_session.add(
            SpeakerRoleMap(
                exam_id=exam_id,
                speaker=speaker,
                role=role,
                source="auto",
            )
        )

    db_session.flush()
    logger.info(
        f"[Transcript] 已保存到数据库: exam_id={exam_id}, "
        f"transcripts={len(segments)}, speaker_role_maps={len(speaker_role_map)}"
    )


def dump_audio_timeline_json(
    output_dir: str,
    exam_id: int,
    audio_result: dict[str, Any],
) -> str:
    """把 audio_result 完整序列化为 JSON 写到 output_dir.

    Returns:
        JSON 文件绝对路径
    """
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"exam_{exam_id}_audio_timeline.json"

    payload = {
        "exam_id": exam_id,
        "audio_path": audio_result.get("audio_path"),
        "speaker_role_map": audio_result.get("speaker_role_map", {}),
        "segments": audio_result.get("segments", []),
        "events": audio_result.get("events", []),
        "hotwords": audio_result.get("hotwords", []),
        "stats": audio_result.get("stats", {}),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    size_kb = json_path.stat().st_size / 1024
    logger.info(
        f"[Transcript] 时间轴 JSON 已写入: {json_path} ({size_kb:.1f} KB)"
    )
    return str(json_path)
