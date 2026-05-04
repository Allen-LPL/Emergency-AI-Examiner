"""
说话人角色推断器
根据每个说话人的转写内容，通过医疗术语密度分析推断角色:
  - 医生(doctor): 下达医疗指令最多的人
  - 护士(nurse): 执行辅助操作、记录的人
  - 驾驶员(driver): 发言最少或包含转运相关词的人
"""

import re
from collections import Counter, defaultdict

from loguru import logger

DOCTOR_KEYWORDS = [
    "肾上腺素",
    "除颤",
    "评估",
    "静脉",
    "通气",
    "按压",
    "开始",
    "停止",
    "心律",
    "室颤",
    "电击",
    "能量",
    "焦耳",
    "建立",
    "给予",
    "推注",
    "心肺复苏",
    "气管插管",
    "监护",
    "抢救",
]

NURSE_KEYWORDS = [
    "准备好",
    "已完成",
    "记录",
    "签字",
    "配合",
    "吸引器",
    "导联",
    "已连接",
    "好的",
    "收到",
    "准备",
    "打印",
    "血压",
    "氧饱和度",
    "体温",
    "备好",
    "已开通",
]

DRIVER_KEYWORDS = [
    "担架",
    "转运",
    "上车",
    "出发",
    "到达",
    "路线",
    "医院",
    "急诊",
    "送",
    "车",
    "固定",
]


class SpeakerRoleInferrer:
    """根据转写内容分析说话人角色"""

    def __init__(self):
        """预编译角色关键词正则，减少重复匹配开销"""
        self._doctor_pattern = re.compile("|".join(DOCTOR_KEYWORDS))
        self._nurse_pattern = re.compile("|".join(NURSE_KEYWORDS))
        self._driver_pattern = re.compile("|".join(DRIVER_KEYWORDS))

    def infer_roles(self, transcription: list[dict]) -> dict[str, str]:
        """
        分析每个说话人的内容，推断角色

        Args:
            transcription: 带有 speaker 字段的转写段列表

        Returns:
            {speaker_id: role} 映射，如 {"SPEAKER_00": "doctor", "SPEAKER_01": "nurse", "SPEAKER_02": "driver"}
        """
        speaker_texts: dict[str, str] = defaultdict(str)
        speaker_segment_counts: dict[str, int] = Counter()

        for seg in transcription:
            speaker = seg.get("speaker")
            if not speaker:
                continue
            speaker_texts[speaker] += seg.get("text", "") + " "
            speaker_segment_counts[speaker] += 1

        if not speaker_texts:
            logger.warning("没有说话人信息，无法推断角色")
            return {}

        speaker_scores: dict[str, dict[str, float]] = {}
        for speaker, text in speaker_texts.items():
            doctor_hits = len(self._doctor_pattern.findall(text))
            nurse_hits = len(self._nurse_pattern.findall(text))
            driver_hits = len(self._driver_pattern.findall(text))
            total_chars = max(len(text), 1)

            speaker_scores[speaker] = {
                "doctor": doctor_hits / total_chars * 1000,
                "nurse": nurse_hits / total_chars * 1000,
                "driver": driver_hits / total_chars * 1000,
                "total_segments": speaker_segment_counts[speaker],
            }

        roles: dict[str, str] = {}
        available_speakers = set(speaker_scores.keys())

        doctor_candidates = sorted(
            available_speakers,
            key=lambda speaker: speaker_scores[speaker]["doctor"],
            reverse=True,
        )
        if doctor_candidates:
            roles[doctor_candidates[0]] = "doctor"
            available_speakers.discard(doctor_candidates[0])

        if available_speakers:
            driver_candidates = sorted(
                available_speakers,
                key=lambda speaker: (
                    speaker_scores[speaker]["driver"],
                    -speaker_scores[speaker]["total_segments"],
                ),
                reverse=True,
            )
            least_speaker = min(
                available_speakers,
                key=lambda speaker: speaker_scores[speaker]["total_segments"],
            )

            if driver_candidates and speaker_scores[driver_candidates[0]]["driver"] > 0:
                roles[driver_candidates[0]] = "driver"
                available_speakers.discard(driver_candidates[0])
            else:
                roles[least_speaker] = "driver"
                available_speakers.discard(least_speaker)

        for speaker in available_speakers:
            roles[speaker] = "nurse"

        logger.info(f"说话人角色推断: {roles}")
        for speaker, role in roles.items():
            scores = speaker_scores[speaker]
            logger.debug(
                f"  {speaker} → {role} "
                f"(医生词频:{scores['doctor']:.1f}, "
                f"护士词频:{scores['nurse']:.1f}, "
                f"驾驶员词频:{scores['driver']:.1f}, "
                f"发言段数:{scores['total_segments']})"
            )
        return roles

    def apply_roles(
        self, transcription: list[dict], roles: dict[str, str]
    ) -> list[dict]:
        """将角色标注写入转写段"""
        for seg in transcription:
            speaker = seg.get("speaker")
            if speaker and speaker in roles:
                seg["speaker_role"] = roles[speaker]
            else:
                seg["speaker_role"] = "unknown"
        return transcription
