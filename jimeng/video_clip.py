# -*- coding: utf-8 -*-
"""图生视频：把场景图生成为短视频片段。

模式：
- image2video：每个场景一张图 → 一段视频（默认，4-6 秒）
- multiframe2video：整集多张场景图 → 一段连贯故事视频（可选）
"""
import logging
from pathlib import Path

from . import dreamina_cli
from .config import resolve_path

log = logging.getLogger("jimeng.video")


def clip_output_path(cfg, episode, scene_index):
    d = resolve_path(cfg, "clips_dir", "assets/clips")
    return d / ("E%03d_S%02d.mp4" % (episode, scene_index))


def episode_clip_output_path(cfg, episode):
    d = resolve_path(cfg, "clips_dir", "assets/clips")
    return d / ("E%03d_story.mp4" % episode)


def build_motion_prompt(cfg, scene):
    template = (cfg.get("video") or {}).get("motion_prompt", "镜头缓慢推近，人物自然动作，电影感运镜，画面稳定")
    action = (scene.action or "").strip()
    if action:
        return template.replace("{action}", action)
    return template


def generate_scene_video(scene, image_path, cfg, cli=None):
    """单场景图生视频，返回视频文件路径。已有产物直接复用。"""
    cli = cli or dreamina_cli
    out = clip_output_path(cfg, scene.episode, scene.index)
    if out.exists():
        log.info("视频片段已存在，复用：%s", out)
        return str(out)

    vid_cfg = cfg.get("video") or {}
    prompt = build_motion_prompt(cfg, scene)
    log.info("图生视频：E%d S%d", scene.episode, scene.index)
    files = dreamina_cli.submit_and_wait(
        cfg,
        lambda: cli.image2video(
            cfg,
            image_path,
            prompt,
            duration=vid_cfg.get("duration", 5),
            video_resolution=vid_cfg.get("video_resolution", "1080p"),
            model_version=vid_cfg.get("model_version", "seedance2.0"),
        ),
        out.parent,
        max_wait=int((cfg.get("dreamina") or {}).get("max_wait_seconds", 900)),
    )
    if not files:
        raise dreamina_cli.DreaminaError("视频生成未返回文件：E%d S%d" % (scene.episode, scene.index))
    src = files[0]
    if src.name != out.name:
        src.replace(out)
    return str(out)


def generate_episode_video(episode, image_paths, cfg, cli=None):
    """整集多图连贯视频（multiframe2video）。image_paths 为该集场景图路径列表。"""
    cli = cli or dreamina_cli
    out = episode_clip_output_path(cfg, episode.number)
    if out.exists():
        log.info("整集视频已存在，复用：%s", out)
        return str(out)
    if len(image_paths) < 2:
        raise dreamina_cli.DreaminaError("multiframe2video 至少需要 2 张图（当前 %d 张）" % len(image_paths))
    # 每个转场一段提示词：N 张图需要 N-1 个
    transition_prompts = [
        "镜头自然过渡到下一场景，人物动作连贯，电影感运镜"
        for _ in range(len(image_paths) - 1)
    ]
    files = dreamina_cli.submit_and_wait(
        cfg,
        lambda: cli.multiframe2video(
            cfg,
            image_paths,
            transition_prompts=transition_prompts,
        ),
        out.parent,
        max_wait=int((cfg.get("dreamina") or {}).get("max_wait_seconds", 1200)),
    )
    if not files:
        raise dreamina_cli.DreaminaError("整集视频生成未返回文件：E%d" % episode.number)
    src = files[0]
    if src.name != out.name:
        src.replace(out)
    return str(out)
