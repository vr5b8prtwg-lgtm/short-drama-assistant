# -*- coding: utf-8 -*-
"""配置加载：config.yaml（用户）叠加在 config.example.yaml（默认）之上，环境变量覆盖关键项。"""
import copy
import os
from pathlib import Path

import yaml


def _deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def default_config():
    pkg_dir = Path(__file__).resolve().parent
    example = pkg_dir / "config.example.yaml"
    with open(example, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path=None):
    """加载配置。path 指向用户 config.yaml；为空时只使用默认示例配置。"""
    cfg = default_config()
    if path:
        with open(path, encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        cfg = _deep_merge(cfg, user)

    # 环境变量覆盖
    dreamina = cfg.setdefault("dreamina", {})
    dreamina["bin"] = os.environ.get("DREAMINA_BIN", dreamina.get("bin", "") or "")
    tts = cfg.setdefault("tts", {})
    tts["api_key"] = os.environ.get("VOLC_TTS_API_KEY", tts.get("api_key", "") or "")
    return cfg


def resolve_path(cfg, key, default):
    """按项目根目录解析 paths 下配置的目录。"""
    root = Path.cwd()
    rel = (cfg.get("paths") or {}).get(key, default)
    p = Path(rel)
    if not p.is_absolute():
        p = root / p
    return p
