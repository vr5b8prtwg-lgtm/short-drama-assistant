# -*- coding: utf-8 -*-
"""从 Dify「网剧AI漫剧生成」工作流输出的素材清单（JSON）下载视频并合成整集 MP4。

用法：
    python -m jimeng.assemble_manifest --manifest <manifest.json> [--config jimeng/config.yaml]

manifest.json 结构（由 Dify 工作流输出）：
{
  "title": "剧名",
  "episodes": [
    {
      "number": 1,
      "title": "集标题",
      "scenes": [
        {"index": 1, "image_url": "...", "video_url": "...",
         "dialogue": [["角色","台词"], ...], "prompt": "画面提示词"}
      ]
    }
  ]
}
"""
import argparse
import json
import logging
import sys
from pathlib import Path

import requests

from .assemble import assemble_episode, probe_duration
from .config import load_config, resolve_path
from .subtitle import build_srt, write_srt

log = logging.getLogger("jimeng.assemble_manifest")


def download(url, out_path, timeout=600):
    out_path = Path(out_path)
    if out_path.exists():
        log.info("已存在，跳过下载：%s", out_path)
        return str(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("下载 %s", url)
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    return str(out_path)


def build_manifest_srt(scenes, clip_durations, cfg):
    """按场景起始时间偏移生成整集 SRT。"""
    subtitle_cfg = cfg.get("subtitle") or {}
    default_sec = float(subtitle_cfg.get("default_line_seconds", 2.5))
    gap = float(subtitle_cfg.get("gap_seconds", 0.2))
    parts = []
    cursor = 0.0
    for i, scene in enumerate(scenes):
        start = cursor
        if i < len(clip_durations) and clip_durations[i]:
            cursor += clip_durations[i]
        srt = build_srt(
            scene.get("dialogue") or [],
            durations=None,
            default_line_seconds=default_sec,
            gap_seconds=gap,
            offset_seconds=start,
        )
        if srt:
            parts.append(srt)
    # 重新编号
    merged = []
    idx = 1
    for part in parts:
        for line in part.splitlines():
            if line.strip().isdigit():
                merged.append(str(idx))
                idx += 1
            else:
                merged.append(line)
    return "\n".join(merged) + "\n" if merged else ""


def assemble_one_episode(episode, cfg, out_dir):
    scenes = episode.get("scenes") or []
    if not scenes:
        log.warning("第 %d 集没有场景，跳过", episode.get("number"))
        return None

    downloads = resolve_path(cfg, "scenes_dir", "assets/scenes") / "downloads"
    clips = []
    scene_assets = []
    for scene in scenes:
        video_url = scene.get("video_url") or scene.get("url")
        if not video_url:
            log.warning("场景 %s 缺少 video_url，跳过", scene.get("index"))
            continue
        clip = download(video_url, downloads / ("E%02d_S%02d.mp4" % (episode.get("number", 0), scene.get("index", 0))))
        clips.append(clip)
        scene_assets.append({"video": clip, "audio": None})

    if not clips:
        log.warning("第 %d 集没有可用的视频片段", episode.get("number"))
        return None

    clip_durations = [probe_duration(cfg, c) for c in clips]
    srt_text = build_manifest_srt(scenes, clip_durations, cfg)
    subs_dir = resolve_path(cfg, "subs_dir", "assets/subs")
    srt_path = write_srt(subs_dir / ("E%03d.srt" % episode.get("number", 0)), srt_text)

    episodes_dir = out_dir or resolve_path(cfg, "episodes_dir", "assets/episodes")
    out = episodes_dir / ("第%d集.mp4" % episode.get("number", 0))
    try:
        assemble_episode(cfg, scene_assets, str(srt_path) if srt_path else None, out)
        return str(out)
    except Exception as exc:
        log.error("合成第 %d 集失败：%s", episode.get("number"), exc)
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="从素材清单合成整集 AI 漫剧")
    parser.add_argument("--manifest", required=True, help="Dify 输出的素材清单 JSON 路径")
    parser.add_argument("--config", default=None, help="jimeng 配置（ffmpeg 路径等）")
    parser.add_argument("--out-dir", default=None, help="成片输出目录（默认用配置的 episodes_dir）")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)

    episodes = manifest.get("episodes") or []
    if not episodes:
        print("清单中没有剧集，请检查 manifest 格式")
        return 2

    results = []
    for ep in episodes:
        log.info("合成第 %d 集", ep.get("number"))
        out = assemble_one_episode(ep, cfg, Path(args.out_dir) if args.out_dir else None)
        results.append({"number": ep.get("number"), "output": out})

    print(json.dumps(results, ensure_ascii=False, indent=2))
    failed = [r for r in results if not r["output"]]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
