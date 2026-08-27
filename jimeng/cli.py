# -*- coding: utf-8 -*-
"""即梦 dreamina CLI 全自动 AI 漫剧管线入口。

用法：
    python -m jimeng.cli --script <剧本包.md> [--config config.yaml]
    python -m jimeng.cli --script <剧本包.md> --episodes 1        # 只跑第 1 集
    python -m jimeng.cli --script <剧本包.md> --only-scenes       # 只生成场景图（快速验证）
    python -m jimeng.cli --check-login-only                       # 只校验登录与积分

流程：解析剧本包 → 定妆图 → 场景图 → 图生视频 → 配音 → 字幕 → ffmpeg 合成整集。
支持断点续跑：已有产物自动复用；单场景失败重试 2 次并记录，不影响其他场景。
"""
import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

from . import dreamina_cli
from .assemble import assemble_episode, probe_duration
from .character_assets import ensure_character_images
from .config import load_config, resolve_path
from .parse_script import load_package
from .scene_image import generate_scene_image
from .subtitle import build_srt, write_srt
from .tts import TTSUnavailable, synthesize_scene
from .video_clip import generate_episode_video, generate_scene_video

log = logging.getLogger("jimeng")


def setup_logging(log_path):
    root = logging.getLogger("jimeng")
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)


def parse_episode_selection(spec, available):
    """'all' | '1' | '1-3' | '1,3' -> 有序去重的集号列表。"""
    if not available:
        return []
    if spec in (None, "", "all"):
        return available
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            out.extend(range(lo, hi + 1))
        elif part.isdigit():
            out.append(int(part))
    out = [n for n in dict.fromkeys(out) if n in available]
    return out


def summarize_package(pkg):
    print("=" * 60)
    print("剧本包：%s" % (pkg.title or "未命名"))
    print("人物定妆表：%d 位" % len(pkg.character_sheet))
    for name, desc in pkg.character_sheet:
        print("  - %s：%s" % (name, desc[:50] + ("…" if len(desc) > 50 else "")))
    print("分集：%d 集，共 %d 个场景" % (len(pkg.episodes), sum(len(e.scenes) for e in pkg.episodes)))
    print("=" * 60)


def process_episode(episode, pkg, cfg, character_refs, retries=2, only_scenes=False, skip_dubbing=False):
    """处理一集：场景图→视频→配音→字幕→合成。返回 (episode_path, failures)。"""
    failures = []
    scene_assets = []
    srt_parts = []
    video_mode = (cfg.get("video") or {}).get("mode", "image2video")

    # ---- 1) 场景图 ----
    image_paths = []
    for scene in episode.scenes:
        try:
            img = generate_scene_image(scene, character_refs, pkg.characters, cfg)
            image_paths.append(img)
            scene_assets.append({"video": None, "audio": None, "image": img, "scene": scene})
        except Exception as exc:
            log.error("场景图失败 E%d S%d：%s", episode.number, scene.index, exc)
            failures.append("E%d S%d 场景图：%s" % (episode.number, scene.index, exc))

    if only_scenes:
        return None, failures

    if not image_paths:
        log.error("第 %d 集没有可用场景图，跳过本集", episode.number)
        return None, failures + ["第 %d 集无场景图" % episode.number]

    # ---- 2) 视频 ----
    if video_mode == "multiframe2video":
        try:
            story = generate_episode_video(episode, image_paths, cfg)
            scene_assets = [{"video": story, "audio": None}]
        except Exception as exc:
            log.error("整集视频失败 E%d：%s", episode.number, exc)
            failures.append("E%d 整集视频：%s" % (episode.number, exc))
            return None, failures
    else:
        for asset in scene_assets:
            scene = asset["scene"]
            if not asset["image"]:
                continue
            for attempt in range(retries + 1):
                try:
                    clip = generate_scene_video(scene, asset["image"], cfg)
                    asset["video"] = clip
                    break
                except Exception as exc:
                    log.warning("视频失败 E%d S%d（第 %d 次）：%s",
                                episode.number, scene.index, attempt + 1, exc)
                    if attempt == retries:
                        failures.append("E%d S%d 视频：%s" % (episode.number, scene.index, exc))
                        time.sleep(3)

    # ---- 3) 配音 + 字幕 ----
    audio_dir = resolve_path(cfg, "audio_dir", "assets/audio")
    subs_dir = resolve_path(cfg, "subs_dir", "assets/subs")
    episode_srt = subs_dir / ("E%03d.srt" % episode.number)

    clip_durations = []
    for asset in scene_assets:
        if asset.get("video"):
            dur = probe_duration(cfg, asset["video"])
            clip_durations.append(dur if dur else None)
        else:
            clip_durations.append(None)

    cursor = 0.0
    for i, asset in enumerate(scene_assets):
        scene = asset["scene"]
        start = cursor
        if clip_durations[i]:
            cursor += clip_durations[i]

        audios = []
        if not skip_dubbing:
            try:
                audios = synthesize_scene(cfg, scene, audio_dir)
            except TTSUnavailable as exc:
                log.warning("配音跳过：%s", exc)
            except Exception as exc:
                log.warning("配音失败 E%d S%d：%s", episode.number, scene.index, exc)

        if audios:
            asset["audio"] = audios[0][0]
            durations = [d for _, d in audios]
        else:
            durations = None

        srt = build_srt(
            scene.dialogue,
            durations=durations,
            default_line_seconds=float((cfg.get("subtitle") or {}).get("default_line_seconds", 2.5)),
            gap_seconds=float((cfg.get("subtitle") or {}).get("gap_seconds", 0.2)),
            offset_seconds=start,
        )
        if srt:
            srt_parts.append(srt)

    # 字幕合并：重新编号
    merged = []
    idx = 1
    for part in srt_parts:
        for line in part.splitlines():
            if line.strip().isdigit():
                merged.append(str(idx))
                idx += 1
            else:
                merged.append(line)
    srt_path = write_srt(episode_srt, "\n".join(merged) + "\n" if merged else "")

    # ---- 4) 合成整集 ----
    episodes_dir = resolve_path(cfg, "episodes_dir", "assets/episodes")
    out = episodes_dir / ("第%d集.mp4" % episode.number)
    try:
        assemble_episode(cfg, scene_assets, str(srt_path) if srt_path else None, out)
        log.info("整集完成：%s", out)
        return str(out), failures
    except Exception as exc:
        log.error("整集合成失败 E%d：%s", episode.number, exc)
        return None, failures + ["E%d 合成：%s" % (episode.number, exc)]


def main(argv=None):
    parser = argparse.ArgumentParser(description="即梦 dreamina CLI 全自动 AI 漫剧管线")
    parser.add_argument("--script", help="Dify 输出的剧本包 Markdown 路径")
    parser.add_argument("--config", default=None, help="用户配置 config.yaml 路径")
    parser.add_argument("--episodes", default="all", help="集数选择：all / 1 / 1-3 / 1,3")
    parser.add_argument("--only-scenes", action="store_true", help="只生成场景图，不生成视频与成片")
    parser.add_argument("--skip-dubbing", action="store_true", help="跳过配音（仍生成字幕）")
    parser.add_argument("--rebuild-characters", action="store_true", help="重新生成定妆图（删除已有）")
    parser.add_argument("--check-login-only", action="store_true", help="只校验 dreamina 登录与积分后退出")
    parser.add_argument("--retries", type=int, default=2, help="单场景失败重试次数")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    log_path = resolve_path(cfg, "logs_dir", "assets/logs") / "pipeline.log"
    setup_logging(log_path)

    # 登录/积分校验
    try:
        credit = dreamina_cli.check_login(cfg)
        log.info("dreamina 登录正常，积分信息：%s", json.dumps(credit, ensure_ascii=False)[:200])
    except dreamina_cli.DreaminaError as exc:
        log.error("dreamina 校验失败：%s", exc)
        log.info("%s", dreamina_cli.login_hint())
        return 2
    if args.check_login_only:
        print("dreamina 登录校验通过。")
        return 0

    if not args.script:
        parser.error("--script 必填（除非使用 --check-login-only）")

    pkg = load_package(args.script)
    summarize_package(pkg)

    if not pkg.character_sheet:
        log.warning("剧本包未检出「人物定妆表」/「定妆描述」，将无法生成定妆图；"
                    "请确认剧本由已更新的 Dify 工作流（人物卡含定妆描述）输出。")

    # 定妆图
    if args.rebuild_characters:
        chars_dir = resolve_path(cfg, "characters_dir", "assets/characters")
        for p in (chars_dir.glob("*.png") if chars_dir.exists() else []):
            p.unlink()
    character_refs = ensure_character_images(pkg, cfg)

    # 积分门槛
    min_credit = int(cfg.get("min_credit", 0) or 0)
    if min_credit > 0:
        try:
            credit = dreamina_cli.check_login(cfg)
            log.info("当前积分信息：%s", json.dumps(credit, ensure_ascii=False)[:200])
        except dreamina_cli.DreaminaError as exc:
            log.error("积分校验失败：%s", exc)
            return 2

    available = [e.number for e in pkg.episodes]
    selected = parse_episode_selection(args.episodes, available)
    if not selected:
        log.error("没有匹配到要处理的集（剧本共 %d 集）", len(available))
        return 2

    summary = {
        "script": args.script,
        "title": pkg.title,
        "characters": dict(pkg.character_sheet),
        "episodes": [],
        "failures": [],
    }

    for ep_no in selected:
        episode = next((e for e in pkg.episodes if e.number == ep_no), None)
        if episode is None:
            summary["failures"].append("第 %d 集不存在" % ep_no)
            continue
        log.info("开始处理第 %d 集（%d 个场景）", ep_no, len(episode.scenes))
        out, failures = process_episode(
            episode, pkg, cfg, character_refs,
            retries=args.retries,
            only_scenes=args.only_scenes,
            skip_dubbing=args.skip_dubbing,
        )
        summary["episodes"].append({"number": ep_no, "output": out, "scenes": len(episode.scenes)})
        summary["failures"].extend(failures)

    root = resolve_path(cfg, "assets_root", "assets")
    with open(root / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    if summary["failures"]:
        print("完成，但有 %d 个失败项：" % len(summary["failures"]))
        for item in summary["failures"]:
            print("  - " + item)
        return 1
    print("全部完成，成片在 %s 目录。" % resolve_path(cfg, "episodes_dir", "assets/episodes"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
