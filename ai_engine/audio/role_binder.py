# pyright: reportMissingImports=false
"""说话人 → 角色绑定.

绑定优先级 (高 → 低):
    1. 显式参数 manual_map: 来自数据库 / 前端人工标注
    2. 内容驱动推断: 基于 segment_type 计数
        - 含 medical_command 最多的 speaker → doctor
        - 含 family_inquiry  最多的 speaker → driver
        - 含 assistant_response 最多的 speaker → nurse
    3. 兜底: 按发言量分配剩余 speaker

设计要点:
    - 不要"只看发言少就判 driver", 否则在驾驶员发言比护士多的场景会判反
      (用户原文: "不要只靠发言少判断 driver")
    - 同一 speaker 只会有一个角色, 多个候选时按计数排序后顺次分配
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from loguru import logger

from ai_engine.audio.types import (
    SEGMENT_TYPE_ASSISTANT_RESPONSE,
    SEGMENT_TYPE_FAMILY_INQUIRY,
    SEGMENT_TYPE_MEDICAL_COMMAND,
    SpeechSegment,
)


ROLE_DOCTOR = "doctor"
ROLE_NURSE = "nurse"
ROLE_DRIVER = "driver"
ROLE_UNKNOWN = "unknown"

# 优先级顺序: doctor 最先确定 (内容信号最强), 然后 driver (家属沟通), 最后 nurse 兜底
PRIMARY_ROLES = [ROLE_DOCTOR, ROLE_DRIVER, ROLE_NURSE]


class SpeakerRoleBinder:
    """根据 SpeechSegment 列表把 speaker 绑定到 doctor/nurse/driver."""

    def bind(
        self,
        segments: list[SpeechSegment],
        manual_map: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """返回 speaker_role_map: {speaker: role}.

        Args:
            segments: 已经填好 segment_type 的段
            manual_map: 人工 / DB 已有标注, 优先级最高
        """
        if not segments:
            return dict(manual_map or {})

        # 1) 收集所有 speaker, 统计每类 segment_type 的次数
        type_count_per_speaker: dict[str, Counter[str]] = {}
        total_segments_per_speaker: Counter[str] = Counter()

        for seg in segments:
            if not seg.speaker:
                continue
            total_segments_per_speaker[seg.speaker] += 1
            counter = type_count_per_speaker.setdefault(seg.speaker, Counter())
            if seg.segment_type:
                counter[seg.segment_type] += 1

        all_speakers = set(total_segments_per_speaker.keys())
        if not all_speakers:
            logger.warning("[RoleBinder] 没有有效 speaker, 返回空映射")
            return dict(manual_map or {})

        # 2) 用 manual_map 预占角色 (人工标注最高优先级)
        roles: dict[str, str] = {}
        if manual_map:
            for sp, role in manual_map.items():
                if sp in all_speakers and role:
                    roles[sp] = role
                    logger.info(
                        f"[RoleBinder] 采用人工标注: {sp} → {role}"
                    )

        # 3) 内容驱动推断剩余 speaker
        unassigned = all_speakers - set(roles.keys())

        # 优先级 1: doctor — 比 medical_command 数量, 最多者得
        if unassigned and ROLE_DOCTOR not in roles.values():
            picked = self._pick_speaker_by_type(
                type_count_per_speaker,
                total_segments_per_speaker,
                unassigned,
                target_type=SEGMENT_TYPE_MEDICAL_COMMAND,
            )
            if picked:
                roles[picked] = ROLE_DOCTOR
                unassigned.discard(picked)

        # 优先级 2: driver — 比 family_inquiry 数量
        if unassigned and ROLE_DRIVER not in roles.values():
            picked = self._pick_speaker_by_type(
                type_count_per_speaker,
                total_segments_per_speaker,
                unassigned,
                target_type=SEGMENT_TYPE_FAMILY_INQUIRY,
            )
            if picked:
                roles[picked] = ROLE_DRIVER
                unassigned.discard(picked)

        # 优先级 3: nurse — 比 assistant_response 数量
        if unassigned and ROLE_NURSE not in roles.values():
            picked = self._pick_speaker_by_type(
                type_count_per_speaker,
                total_segments_per_speaker,
                unassigned,
                target_type=SEGMENT_TYPE_ASSISTANT_RESPONSE,
            )
            if picked:
                roles[picked] = ROLE_NURSE
                unassigned.discard(picked)

        # 4) 兜底: 把剩余 speaker 按"还缺哪个角色"补齐, 按发言量降序分配
        remaining_roles = [r for r in PRIMARY_ROLES if r not in roles.values()]
        leftovers = sorted(
            unassigned,
            key=lambda s: total_segments_per_speaker[s],
            reverse=True,
        )
        for speaker in leftovers:
            if remaining_roles:
                roles[speaker] = remaining_roles.pop(0)
            else:
                # 超出 3 个 speaker 的情况 (急救场景偶有), 给 unknown
                roles[speaker] = ROLE_UNKNOWN

        logger.info(f"[RoleBinder] 角色绑定结果: {roles}")
        for sp in sorted(all_speakers):
            counts = type_count_per_speaker.get(sp, Counter())
            logger.debug(
                f"  {sp} → {roles.get(sp, ROLE_UNKNOWN)}: "
                f"medical={counts.get(SEGMENT_TYPE_MEDICAL_COMMAND, 0)}, "
                f"family={counts.get(SEGMENT_TYPE_FAMILY_INQUIRY, 0)}, "
                f"assistant={counts.get(SEGMENT_TYPE_ASSISTANT_RESPONSE, 0)}, "
                f"total={total_segments_per_speaker[sp]}"
            )
        return roles

    @staticmethod
    def _pick_speaker_by_type(
        type_count_per_speaker: dict[str, Counter[str]],
        total_segments_per_speaker: Counter[str],
        candidates: set[str],
        target_type: str,
    ) -> Optional[str]:
        """在 candidates 中, 找 target_type 计数最高且 > 0 的 speaker.

        若所有候选 target_type 都为 0, 返回 None (留给兜底环节处理)
        """
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda s: (
                type_count_per_speaker.get(s, Counter()).get(target_type, 0),
                total_segments_per_speaker[s],
            ),
            reverse=True,
        )
        top = ranked[0]
        if type_count_per_speaker.get(top, Counter()).get(target_type, 0) <= 0:
            return None
        return top

    @staticmethod
    def apply_roles(
        segments: list[SpeechSegment], roles: dict[str, str]
    ) -> list[SpeechSegment]:
        """把 role 写回到每个 SpeechSegment.role 字段."""
        for seg in segments:
            if seg.speaker and seg.speaker in roles:
                seg.role = roles[seg.speaker]
            else:
                seg.role = ROLE_UNKNOWN
        return segments


__all__ = [
    "SpeakerRoleBinder",
    "ROLE_DOCTOR",
    "ROLE_NURSE",
    "ROLE_DRIVER",
    "ROLE_UNKNOWN",
]
