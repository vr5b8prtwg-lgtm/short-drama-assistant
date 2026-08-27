# -*- coding: utf-8 -*-
"""角色定妆图生成与资产库管理。

依据剧本包「人物定妆表」为每位角色生成一张定妆图（竖版、中性背景、2D 国漫/日漫风），
保存到 assets/characters/，已有则跳过。该图作为后续所有场景图生成的参考（人物一致性锚点）。
"""
import logging
import re
from pathlib import Path

from . import dreamina_cli
from .config import resolve_path

log = logging.getLogger("jimeng.character")


def sanitize_name(name):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_") or "角色"


def build_character_prompt(cfg, name, desc):
    style = (cfg.get("style") or {})
    prefix = style.get("prefix", "")
    bg = style.get("character_bg", "纯色浅灰背景，全身立绘，正面站立，单人，无文字")
    return "%s。角色名：%s。定妆描述：%s。%s" % (prefix, name, desc, bg)


def ensure_character_images(pkg, cfg, cli=None):
    """为人物定妆表中的每位角色生成/复用定妆图。返回 {角色名: 图片路径}。"""
    cli = cli or dreamina_cli
    chars_dir = resolve_path(cfg, "characters_dir", "assets/characters")
    chars_dir.mkdir(parents=True, exist_ok=True)

    img_cfg = cfg.get("image") or {}
    result = {}
    for name, desc in pkg.character_sheet:
        safe = sanitize_name(name)
        out = chars_dir / ("%s.png" % safe)
        if out.exists():
            log.info("定妆图已存在，复用：%s", out)
            result[name] = str(out)
            continue
        prompt = build_character_prompt(cfg, name, desc)
        log.info("生成定妆图：%s", name)
        files = dreamina_cli.submit_and_wait(
            cfg,
            lambda: cli.text2image(
                cfg,
                prompt,
                ratio=img_cfg.get("ratio", "9:16"),
                resolution_type=img_cfg.get("resolution_type", "2k"),
                model_version=img_cfg.get("model_version", "4.0"),
            ),
            chars_dir,
        )
        if not files:
            raise dreamina_cli.DreaminaError("定妆图生成未返回文件：%s" % name)
        src = files[0]
        if src.name != out.name:
            src.replace(out)
        result[name] = str(out)
        log.info("定妆图完成：%s -> %s", name, out)
    return result
