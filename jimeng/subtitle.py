# -*- coding: utf-8 -*-
"""字幕生成：对白 → SRT。

优先使用每句音频的实际时长；不可用时按字数估算或使用固定默认时长。
支持为每个场景传入 offset_seconds，以对齐整集时间轴。
"""
import logging
from pathlib import Path

log = logging.getLogger("jimeng.subtitle")


def format_ts(seconds):
    seconds = max(0.0, seconds)
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def build_srt(dialogues, durations=None, default_line_seconds=2.5, gap_seconds=0.2,
              offset_seconds=0.0):
    """dialogues: [(role, text)]；durations: 可选每句时长列表；offset_seconds: 场景起始时间。返回 SRT 文本。"""
    if not dialogues:
        return ""
    lines = []
    cursor = float(offset_seconds)
    for i, (role, text) in enumerate(dialogues):
        dur = default_line_seconds
        if durations and i < len(durations) and durations[i]:
            dur = durations[i]
        start = cursor
        end = start + dur
        cursor = end + gap_seconds
        lines.append("%d" % (i + 1))
        lines.append("%s --> %s" % (format_ts(start), format_ts(end)))
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def write_srt(path, srt_text):
    if not srt_text:
        return None
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(srt_text)
    return path
