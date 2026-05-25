# pyright: reportMissingImports=false
"""Whisper HTTP ASR 客户端。

设计要点:
    1. 失败原因分桶 (超时 / HTTP 状态 / 网络 / 其他), 每一类都打印足够定位的现场信息;
    2. 成功后把完整转写文本落到 INFO 日志, 便于人工复盘 ASR 质量;
    3. 默认超时 600s, 适配 5+ 分钟的考核音频; 连接超时单独设 15s 避免被 hang 死.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from loguru import logger

from ai_engine.audio.hotwords import get_whisper_initial_prompt

__all__ = ["WhisperHTTPClient"]

# 重复短语正则: 8-100 字短语连续重复 3 次以上, 压成单次.
# 用于剥掉 Whisper 把 initial_prompt 当成"已转写文本"复读 N 次的产物.
_REPEAT_PHRASE_RE = re.compile(r"(.{6,80}?)(?:\1){2,}")


class WhisperHTTPClient:
    def __init__(self, url: str = "http://172.28.0.1:9000/asr", timeout: int = 600):
        self.url = url
        self.timeout = timeout

    def transcribe(self, audio_path: str) -> dict[str, Any]:
        t0 = time.monotonic()
        # 注入医疗/急救领域上下文 + 高权重热词, 压低 Whisper 在中文医疗场景的幻听.
        # 此前 Whisper 裸跑大量幻听 (1001 1002 1003.../5 4 3 2 1) 就是因为没有 initial_prompt.
        initial_prompt = get_whisper_initial_prompt()
        logger.info(
            f"[WhisperHTTPClient] 开始转写: file={audio_path}, "
            f"url={self.url}, timeout={self.timeout}s, "
            f"prompt_len={len(initial_prompt)}字"
        )
        try:
            # connect=15s 用于快速感知服务不可达; 总超时 self.timeout 覆盖长音频上传+推理
            with httpx.Client(
                timeout=httpx.Timeout(self.timeout, connect=15.0)
            ) as client:
                with open(audio_path, "rb") as audio_file:
                    response = client.post(
                        self.url,
                        # output=json: whisper-asr-webservice 默认返回纯文本,
                        # 显式要 JSON 才有 text/language/segments 字段
                        # initial_prompt: Whisper 标准参数, 引导模型领域上下文
                        params={
                            "language": "zh",
                            "output": "json",
                            "initial_prompt": initial_prompt,
                        },
                        files={"audio_file": audio_file},
                    )
            response.raise_for_status()
            text, language, segments = self._parse_response(response)
            raw_len = len(text)
            # prompt-leak 防御: 即便 prompt 改成了散文, medium 模型在静音段仍可能复读;
            # 这里做最后一道防线, 剥掉 (a) prompt 的开头/重复出现 (b) 任意 6-80 字短语连续重复 3+ 次.
            text = self._strip_prompt_leakage(text, initial_prompt)
            stripped_len = len(text)
            elapsed = time.monotonic() - t0
            logger.info(
                f"[WhisperHTTPClient] 转写成功: {raw_len}字 → 剥 prompt 复读后 {stripped_len}字, "
                f"耗时={elapsed:.1f}s, language={language}, "
                f"segments={len(segments)}"
            )
            # 把完整转写文本落到日志, 便于人工复盘 ASR 质量 (用户明确要求)
            logger.info(f"[WhisperHTTPClient] 转写文本: {text}")
            return {"text": text, "language": language, "segments": segments}
        except httpx.TimeoutException as exc:
            elapsed = time.monotonic() - t0
            logger.error(
                f"[WhisperHTTPClient] 请求超时 ({self.timeout}s): "
                f"file={audio_path}, 耗时={elapsed:.1f}s, exc={exc}"
            )
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500] if exc.response is not None else ""
            status = exc.response.status_code if exc.response is not None else -1
            logger.error(
                f"[WhisperHTTPClient] HTTP {status} 错误: "
                f"url={self.url}, body={body}"
            )
        except httpx.HTTPError as exc:
            logger.error(
                f"[WhisperHTTPClient] 网络/传输错误 "
                f"({type(exc).__name__}): {exc}"
            )
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            logger.exception(
                f"[WhisperHTTPClient] 转写异常 ({type(exc).__name__}): {exc}"
            )
        return {"text": "", "segments": []}

    @staticmethod
    def _parse_response(response: httpx.Response) -> tuple[str, str, list]:
        """兼容 JSON 与纯文本两种响应。

        whisper-asr-webservice 在 output=json 时返回 JSON, 但 Content-Type 不一定带 json
        (实测有的 fork 是 text/plain), 所以双重判断: header 含 json 或 body 看起来像 JSON
        ({ / [ 开头) 都先按 JSON 解析; JSON 解析失败再退回纯文本兜底.

        历史 bug: 早期版本只看 Content-Type, 结果 Whisper 服务返回 JSON 但 header 是
        text/plain, 整段 JSON 字符串被当成 text 存进去 (出现过 66292字、segments=0、
        转写文本首字符是 '{' 的现象).
        """
        body_text = (response.text or "").strip()
        ctype = response.headers.get("content-type", "").lower()
        looks_json = "json" in ctype or body_text.startswith(("{", "["))
        if looks_json:
            try:
                data = response.json()
            except ValueError:
                data = None
            if isinstance(data, dict):
                return (
                    str(data.get("text", "")),
                    str(data.get("language", "zh")),
                    data.get("segments", []) or [],
                )
        # 纯文本: 直接当 text, 没有 segments
        return body_text, "zh", []

    @staticmethod
    def _strip_prompt_leakage(text: str, prompt: str) -> str:
        """剥掉 Whisper 复读 initial_prompt 产生的伪转写片段.

        策略 (按顺序应用):
            1. 任何 6-80 字短语连续重复 3+ 次, 压成单次 (覆盖"判断脉搏等操作 ..."这种 17 次复读)
            2. 文本开头如果与 prompt 高度相似 (前 30 字含 prompt 中 3 个以上连续字), 把
               该相似段截到第一个明确转写句子 (出现 "收到"/"继续"/"按压"/数字 等正常转写标志).
            3. 中间出现的 prompt 关键短语 ("急救现场"/"心肺复苏抢救"/"急救医生和护士"/"气道管理")
               所在的句子整句删 (这些是 prompt 内独有表达, 真实转写一般不会原样说).

        即使 prompt 改成了散文式, medium 模型在静音段仍有概率复读, 这里是最后兜底.
        """
        if not text:
            return text

        # 1. 任意 6-80 字短语连续重复 3+ 次, 保留 1 份
        text = _REPEAT_PHRASE_RE.sub(r"\1", text)

        # 2. + 3. 从 prompt 自动提取标志短语, 句级清理:
        #    把 prompt 按中文标点 (顿号/逗号/句号等) 切片, 取长度 >=4 的"独有片段"作为 marker.
        #    转写文本中任何句子包含 marker → 视为 prompt leak 整句删.
        #    优势: prompt 改动后这里自动跟上, 不需要同步维护硬编码列表.
        markers = [
            seg.strip() for seg in re.split(r"[、,，。.!?！？\s]+", prompt or "")
            if len(seg.strip()) >= 4
        ]
        # 兼容历史旧 prompt 残留 (用户跑老镜像还在吐这些)
        markers.extend(["判断脉搏等操作", "做好个人防护", "环境安全、做好"])
        markers = list(dict.fromkeys(markers))  # 去重保序

        if not markers:
            return text.strip()

        sentences = re.split(r"([。!?！？\n])", text)
        cleaned: list[str] = []
        for sent in sentences:
            if any(marker in sent for marker in markers):
                # 该句包含 prompt 标志短语, 视为 leak, 整句删
                continue
            cleaned.append(sent)
        return "".join(cleaned).strip()
