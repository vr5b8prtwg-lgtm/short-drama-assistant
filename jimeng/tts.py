# -*- coding: utf-8 -*-
"""豆包语音（Doubao Speech V3 SSE）多角色配音。

- 按角色映射音色（tts.voices / tts.default_voice）
- 逐句合成，每句一个 mp3，返回 (文件路径, 时长秒)
- 未配置 api_key 时抛 TTSUnavailable，管线据此跳过配音
"""
import base64
import json
import logging
import os
import uuid
from pathlib import Path

import requests

from .config import resolve_path

log = logging.getLogger("jimeng.tts")


class TTSUnavailable(Exception):
    """TTS 未配置或不可用。"""


def _synthesize(cfg, text, speaker, out_path, timeout=60):
    tts = cfg.get("tts") or {}
    api_key = tts.get("api_key") or os.environ.get("VOLC_TTS_API_KEY", "")
    if not api_key:
        raise TTSUnavailable("未配置 tts.api_key 或环境变量 VOLC_TTS_API_KEY，跳过配音。")

    endpoint = tts.get("endpoint", "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse")
    headers = {
        "Content-Type": "application/json",
        "X-Api-Resource-Id": tts.get("resource_id", "seed-tts-2.0"),
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Key": api_key,
    }
    additions = {
        "post_process": {"pitch": 0},
        "disable_markdown_filter": True,
        "enable_latex_tn": False,
        "latex_parser": "v2",
    }
    body = {
        "user": {"uid": "jimeng_pipeline"},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "sample_rate": int(tts.get("sample_rate", 24000)),
            "audio_params": {
                "format": tts.get("format", "mp3"),
                "speech_rate": int(tts.get("speech_rate", 0)),
                "loudness_rate": int(tts.get("loudness_rate", 0)),
                "bit_rate": int(tts.get("bit_rate", 64000)),
            },
            "additions": json.dumps(additions, ensure_ascii=False),
        },
    }

    chunks = []
    with requests.post(endpoint, headers=headers, json=body, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            try:
                d = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            code = d.get("code", 0)
            if code not in (0, 20000000):
                raise TTSUnavailable("TTS 错误 code=%s: %s" % (code, d.get("message", "")))
            if d.get("data"):
                chunks.append(base64.b64decode(d["data"]))

    if not chunks:
        raise TTSUnavailable("TTS 未返回音频数据。")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        for chunk in chunks:
            f.write(chunk)
    return out_path


def _probe_duration(cfg, audio_path):
    """用 ffprobe 探测音频时长（秒）；不可用时按字数估算。"""
    ffprobe = str((cfg.get("assemble") or {}).get("ffmpeg_bin", "ffmpeg")).replace("ffmpeg", "ffprobe")
    try:
        import subprocess
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        pass
    return None


def pick_voice(cfg, role):
    tts = cfg.get("tts") or {}
    voices = tts.get("voices") or {}
    return voices.get(role) or voices.get("旁白") or tts.get("default_voice", "zh_female_vv_uranus_bigtts")


def synthesize_scene(cfg, scene, out_dir, cli=None):
    """合成一个场景的对白。返回 [(audio_path, duration_seconds)]；无对白返回 []。"""
    if not scene.dialogue:
        return []
    if not (cfg.get("tts") or {}).get("enabled", True):
        return []
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for i, (role, text) in enumerate(scene.dialogue, start=1):
        out = out_dir / ("E%03d_S%02d_L%02d.mp3" % (scene.episode, scene.index, i))
        if out.exists():
            dur = _probe_duration(cfg, out)
            result.append((str(out), dur))
            continue
        speaker = pick_voice(cfg, role)
        _synthesize(cfg, text, speaker, str(out))
        dur = _probe_duration(cfg, out)
        result.append((str(out), dur))
        log.info("配音完成：%s（%s）", out.name, role)
    return result


def estimate_duration(text, chars_per_second=4.5):
    return max(1.0, len(text) / chars_per_second)
