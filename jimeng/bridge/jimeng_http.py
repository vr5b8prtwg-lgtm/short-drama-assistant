# -*- coding: utf-8 -*-
"""即梦网页版 API 桥接客户端（OpenAI 兼容接口，标准会员可用）。

通过本地桥接服务（jimeng-free-api-all）调用即梦网页版后台：
- 文生图 / 图生图（images 传 URL 数组）
- 文生视频 / 图生视频（file_paths 传 URL 数组）
鉴权：Authorization: Bearer <sessionid>
"""
import logging
import os

import requests

log = logging.getLogger("jimeng.http")


class JimengHTTPError(Exception):
    pass


def base_url(cfg):
    return str((cfg.get("bridge") or {}).get("base_url") or "http://127.0.0.1:8000").rstrip("/")


def session_id(cfg):
    sid = (cfg.get("bridge") or {}).get("session_id") or os.environ.get("JIMENG_SESSIONID", "")
    if not sid:
        raise JimengHTTPError("缺少 sessionid：请在 config.yaml 的 bridge.session_id 或环境变量 JIMENG_SESSIONID 配置")
    return sid


def _post(cfg, path, payload, timeout=900):
    url = base_url(cfg) + path
    headers = {
        "Authorization": "Bearer " + session_id(cfg),
        "Content-Type": "application/json",
    }
    log.info("POST %s", url)
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise JimengHTTPError("桥接服务请求失败（请确认已启动）：%s" % exc)
    if resp.status_code >= 400:
        raise JimengHTTPError("桥接接口报错 HTTP %s: %s" % (resp.status_code, resp.text[:500]))
    try:
        data = resp.json()
    except ValueError:
        raise JimengHTTPError("桥接响应非 JSON：%s" % resp.text[:300])
    items = (data or {}).get("data") or []
    if not items or not items[0].get("url"):
        raise JimengHTTPError("桥接未返回 URL：%s" % data)
    return items[0]["url"]


def check_login(cfg):
    """健康检查 + 验证 sessionid 是否被接受（GET /v1/models）。"""
    try:
        resp = requests.get(base_url(cfg) + "/v1/models",
                            headers={"Authorization": "Bearer " + session_id(cfg)}, timeout=30)
        if resp.status_code >= 400:
            raise JimengHTTPError("sessionid 无效或被拒绝（HTTP %s）：%s" % (resp.status_code, resp.text[:300]))
        return {"bridge": "ok", "session": "ok"}
    except JimengHTTPError:
        raise
    except requests.RequestException as exc:
        raise JimengHTTPError("无法访问桥接服务（请先启动）：%s" % exc)


def text2image(cfg, prompt, ratio="9:16", resolution_type="2k", model_version=None, poll=None, extra_args=None):
    model = model_version or (cfg.get("bridge") or {}).get("image_model", "jimeng-4.5")
    return _post(cfg, "/v1/images/generations", {
        "model": model,
        "prompt": prompt,
        "ratio": ratio,
        "resolution": resolution_type,
        "n": 1,
    })


def image2image(cfg, images, prompt, ratio="9:16", resolution_type="2k", model_version=None,
                poll=None, extra_args=None):
    model = model_version or (cfg.get("bridge") or {}).get("image_model", "jimeng-4.5")
    return _post(cfg, "/v1/images/generations", {
        "model": model,
        "prompt": prompt,
        "images": list(images),
        "ratio": ratio,
        "resolution": resolution_type,
        "n": 1,
    })


def image2video(cfg, image, prompt, duration=5, video_resolution="720p", model_version=None,
                poll=None, extra_args=None):
    model = model_version or (cfg.get("bridge") or {}).get("video_model", "jimeng-video-seedance-2.0")
    return _post(cfg, "/v1/videos/generations", {
        "model": model,
        "prompt": prompt,
        "file_paths": [image],
        "ratio": "9:16",
        "resolution": video_resolution,
        "duration": int(duration),
    }, timeout=1800)
