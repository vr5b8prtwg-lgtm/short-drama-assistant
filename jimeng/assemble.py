# -*- coding: utf-8 -*-
"""ffmpeg 合成：拼接场景片段 + 配音音轨 + 字幕 → 整集 MP4（竖屏 9:16）。

字幕时序由调用方（cli.py）按各场景片段实际时长计算偏移后合并为一条 SRT。
"""
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from .config import resolve_path

log = logging.getLogger("jimeng.assemble")


class AssembleError(Exception):
    pass


def _ffmpeg(cfg):
    return (cfg.get("assemble") or {}).get("ffmpeg_bin", "ffmpeg")


def _ffprobe(cfg):
    return _ffmpeg(cfg).replace("ffmpeg", "ffprobe")


def probe_duration(cfg, media_path, timeout=30):
    """返回媒体时长（秒）；失败返回 None。"""
    try:
        proc = subprocess.run(
            [_ffprobe(cfg), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)],
            capture_output=True, text=True, timeout=timeout,
            cwd=os.environ.get("TEMP") or tempfile.gettempdir(),
            encoding="utf-8", errors="replace",
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        pass
    return None


def _run(cmd, timeout=1800):
    log.debug("ffmpeg: %s", " ".join(cmd))
    # 从系统临时目录启动：避免从 OneDrive 等受限路径启动 ffmpeg 被拒绝
    cwd = os.environ.get("TEMP") or tempfile.gettempdir()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=cwd, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise AssembleError("未找到 ffmpeg，请先安装并加入 PATH，或在 config.yaml 的 assemble.ffmpeg_bin 配置完整路径。")
    except subprocess.TimeoutExpired:
        raise AssembleError("ffmpeg 超时: %s" % " ".join(cmd))
    if proc.returncode != 0:
        raise AssembleError("ffmpeg 失败:\n%s" % ((proc.stderr or proc.stdout or "")[-800:]))
    return proc


def _concat_list(paths, list_file):
    lines = []
    for p in paths:
        lines.append("file '%s'" % Path(p).resolve().as_posix())
    list_file.write_text("\n".join(lines), encoding="utf-8")
    return list_file


def concat_clips(cfg, clip_paths, out_path):
    """拼接视频片段（重编码保证兼容）。"""
    if not clip_paths:
        raise AssembleError("没有可拼接的视频片段。")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(clip_paths) == 1:
        src = clip_paths[0]
        _run([_ffmpeg(cfg), "-y", "-i", str(src), "-c:v", "libx264", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-movflags", "+faststart", str(out_path)])
        return str(out_path)
    list_file = out_path.parent / ("_concat_%s.txt" % out_path.stem)
    _concat_list(clip_paths, list_file)
    _run([_ffmpeg(cfg), "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
          str(out_path)])
    return str(out_path)


def concat_audio(cfg, audio_paths, out_path):
    """拼接音频片段为一条音轨。"""
    if not audio_paths:
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(audio_paths) == 1:
        src = audio_paths[0]
        _run([_ffmpeg(cfg), "-y", "-i", str(src), "-c:a", "aac", str(out_path)])
        return str(out_path)
    list_file = out_path.parent / ("_alist_%s.txt" % out_path.stem)
    _concat_list(audio_paths, list_file)
    _run([_ffmpeg(cfg), "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
          "-c:a", "aac", str(out_path)])
    return str(out_path)


def mux_episode(cfg, video_path, audio_path, srt_path, out_path, burn=False):
    """视频+配音+字幕合成整集 MP4。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_ffmpeg(cfg), "-y", "-i", str(video_path)]
    if audio_path:
        cmd += ["-i", str(audio_path)]
    has_srt = bool(srt_path) and Path(srt_path).exists()
    if has_srt:
        cmd += ["-i", str(srt_path)]
    if burn and has_srt:
        sub = Path(srt_path).resolve().as_posix().replace(":", "\\:")
        cmd += ["-vf", "subtitles='%s'" % sub]
    cmd += ["-c:v", "copy"]
    if audio_path:
        cmd += ["-c:a", "aac"]
    if has_srt and not burn:
        cmd += ["-c:s", "mov_text", "-metadata:s:s:0", "language=chi"]
    cmd += ["-shortest", "-movflags", "+faststart", str(out_path)]
    _run(cmd)
    return str(out_path)


def assemble_episode(cfg, scene_assets, merged_srt, out_path, subtitle_mode=None):
    """scene_assets: [{video, audio(可空)}] 按场景顺序；merged_srt 为整集 SRT 路径（可空）。"""
    clips = [a["video"] for a in scene_assets if a.get("video")]
    audios = [a["audio"] for a in scene_assets if a.get("audio")]

    joined_video = concat_clips(cfg, clips, out_path.parent / ("_joined_%s.mp4" % out_path.stem))

    joined_audio = None
    if audios:
        joined_audio = concat_audio(cfg, audios, out_path.parent / ("_joined_%s.m4a" % out_path.stem))

    mode = subtitle_mode or (cfg.get("assemble") or {}).get("subtitle_mode", "soft")
    return mux_episode(cfg, joined_video, joined_audio, merged_srt, out_path, burn=(mode == "burn"))
