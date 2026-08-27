# -*- coding: utf-8 -*-
"""场景图生成：为每个场景生成竖屏 9:16 的 2D 国漫/日漫风画面。

一致性策略（双保险）：
1. 提示词层：风格前缀 + 场景画面提示词 + 补全出场角色的「定妆描述」原文
2. 参考图层：优先 image2image 以出场角色的定妆图做参考；失败自动退回 text2image
"""
import logging
from pathlib import Path

from . import dreamina_cli
from .config import resolve_path

log = logging.getLogger("jimeng.scene_image")


def scene_output_path(cfg, episode, scene_index):
    d = resolve_path(cfg, "scenes_dir", "assets/scenes")
    return d / ("E%03d_S%02d.png" % (episode, scene_index))


def build_scene_prompt(cfg, scene, characters_desc):
    style = (cfg.get("style") or {}).get("prefix", "")
    parts = [style]
    if scene.image_prompt:
        parts.append(scene.image_prompt)
    else:
        parts.append(scene.action or "空场景")
    # 提示词层锚点：原样补全出场角色定妆描述
    descs = []
    for name in scene.characters:
        desc = characters_desc.get(name)
        if desc and desc not in scene.image_prompt:
            descs.append("%s：%s" % (name, desc))
    if descs:
        parts.append("出场角色定妆（必须严格保持）：" + "；".join(descs))
    return "，".join(parts)


def generate_scene_image(scene, character_refs, characters_desc, cfg, cli=None):
    """生成单个场景图，返回图片路径。已有产物则直接复用（断点续跑）。"""
    cli = cli or dreamina_cli
    out = scene_output_path(cfg, scene.episode, scene.index)
    if out.exists():
        log.info("场景图已存在，复用：%s", out)
        return str(out)

    prompt = build_scene_prompt(cfg, scene, characters_desc)
    img_cfg = cfg.get("image") or {}
    kwargs = dict(
        ratio=img_cfg.get("ratio", "9:16"),
        resolution_type=img_cfg.get("resolution_type", "2k"),
        model_version=img_cfg.get("model_version", "4.0"),
    )

    refs = []
    if img_cfg.get("use_character_reference", True):
        refs = [character_refs[c] for c in scene.characters if c in character_refs]

    files = []
    if refs:
        try:
            log.info("场景图（带定妆参考）：E%d S%d", scene.episode, scene.index)
            files = dreamina_cli.submit_and_wait(
                cfg,
                lambda: cli.image2image(cfg, refs, prompt, **kwargs),
                out.parent,
            )
        except dreamina_cli.DreaminaError as exc:
            log.warning("image2image 参考生成失败，退回 text2image：%s", exc)
            files = []

    if not files:
        log.info("场景图（文生图）：E%d S%d", scene.episode, scene.index)
        files = dreamina_cli.submit_and_wait(
            cfg,
            lambda: cli.text2image(cfg, prompt, **kwargs),
            out.parent,
        )

    if not files:
        raise dreamina_cli.DreaminaError("场景图生成未返回文件：E%d S%d" % (scene.episode, scene.index))
    src = files[0]
    if src.name != out.name:
        src.replace(out)
    return str(out)
