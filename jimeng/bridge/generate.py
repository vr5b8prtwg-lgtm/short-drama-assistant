# -*- coding: utf-8 -*-
"""本地编排引擎：剧本包 → 定妆图/场景图/视频 URL 清单（manifest）。

基于桥接服务（jimeng-free-api-all，OpenAI 兼容接口）逐场景生成：
  剧本包 → 人物定妆图(text2image) → 场景图(image2image 带定妆参考) → 图生视频
返回与 assemble_manifest.py 兼容的 manifest JSON。

用法：
    python -m jimeng.bridge.generate --script <剧本包.md> --sessionid <sessionid> [--base http://127.0.0.1:8000] [--out manifest.json] [--skip-video]
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ..config import load_config
from ..parse_script import load_package
from . import jimeng_http

log = logging.getLogger("jimeng.bridge.generate")

DEFAULT_STYLE = "2D国漫/日漫风格，精致线稿，电影感光影，高完成度，无文字水印"
DEFAULT_BG = "纯色浅灰背景，全身立绘，正面站立，单人，无文字"
DEFAULT_MOTION = "镜头缓慢推近，人物自然动作，电影感运镜，画面稳定"


def build_cfg(args):
    cfg = load_config(args.config)
    bridge = cfg.setdefault("bridge", {})
    bridge["base_url"] = args.base or bridge.get("base_url", "http://127.0.0.1:8000")
    bridge["session_id"] = args.sessionid or os.environ.get("JIMENG_SESSIONID", "") or bridge.get("session_id", "")
    if args.image_model:
        bridge["image_model"] = args.image_model
    if args.video_model:
        bridge["video_model"] = args.video_model
    if args.resolution:
        bridge["resolution"] = args.resolution
    if args.video_resolution:
        bridge["video_resolution"] = args.video_resolution
    if args.duration:
        bridge["duration"] = args.duration
    return cfg


def extract_drama_title(pkg):
    """从剧本包提取剧名（用于封面）。"""
    import re
    outline = pkg.outline or ""
    m = re.search(r"剧名\s*[：:]\s*《?([^》\n]+)》?", outline)
    if m:
        return m.group(1).strip()
    m = re.search(r"《([^》]+)》", outline)
    return m.group(1).strip() if m else (pkg.title or "")


def cover_prompt(cfg, title):
    style = (cfg.get("style") or {}).get("prefix", DEFAULT_STYLE)
    return "%s。竖屏电影感海报封面，画面中央大标题文字：%s，画面精美，无其他文字" % (style, title)


def character_prompt(cfg, name, desc):
    style = (cfg.get("style") or {}).get("prefix", DEFAULT_STYLE)
    bg = (cfg.get("style") or {}).get("character_bg", DEFAULT_BG)
    return "%s。角色名：%s。定妆描述：%s。%s" % (style, name, desc, bg)


def scene_prompt(cfg, scene, characters_desc):
    style = (cfg.get("style") or {}).get("prefix", DEFAULT_STYLE)
    parts = [style]
    if scene.image_prompt:
        parts.append(scene.image_prompt)
    else:
        parts.append(scene.action or "空场景")
    descs = []
    for name in scene.characters:
        desc = characters_desc.get(name)
        if desc and desc not in (scene.image_prompt or ""):
            descs.append("%s：%s" % (name, desc))
    if descs:
        parts.append("出场角色定妆（必须严格保持）：" + "；".join(descs))
    return "，".join(parts)


def motion_prompt(cfg, scene):
    return (cfg.get("video") or {}).get("motion_prompt", DEFAULT_MOTION).replace(
        "{action}", scene.action or "")


def generate_manifest(pkg, cfg, skip_video=False, skip_scenes=False, scene_mode="episode_base"):
    """执行生成并返回 manifest dict。

    skip_scenes=True 时只生成「定妆图 + 封面图」（试跑/素材模式，最省积分）。
    scene_mode：
      - "episode_base"（默认，最省积分）：每集只生成 1 张基准场景图，该集所有场景的视频都从这张图生成
      - "text"：每场景 1 张文生图
      - "reference"：每场景图生图带定妆参考（更一致但每场景生成 4 张）
    """
    jimeng_http.check_login(cfg)
    bridge = cfg.get("bridge") or {}

    # 1) 定妆图（每人 1 张）
    char_urls = {}
    log.info("生成定妆图：%d 位角色", len(pkg.character_sheet))
    for name, desc in pkg.character_sheet:
        log.info("定妆图：%s", name)
        url = jimeng_http.text2image(
            cfg, character_prompt(cfg, name, desc),
            ratio=bridge.get("ratio", "9:16"),
            resolution_type=bridge.get("resolution", "2k"),
        )
        char_urls[name] = url
        log.info("定妆图完成：%s -> %s", name, url)

    # 1.5) 封面图（1 张，带剧名标题）
    title = extract_drama_title(pkg)
    log.info("生成封面图（剧名：%s）", title)
    cover_url = jimeng_http.text2image(
        cfg, cover_prompt(cfg, title),
        ratio=bridge.get("ratio", "9:16"),
        resolution_type=bridge.get("resolution", "2k"),
    )
    log.info("封面图完成：%s", cover_url)

    manifest = {"title": pkg.title, "drama_title": title, "cover_url": cover_url,
                "characters": char_urls, "episodes": []}

    if skip_scenes:
        log.info("仅素材模式：跳过场景与视频，只输出定妆图+封面")
        return manifest

    # 2) 逐场景生成
    episodes = []
    ratio = bridge.get("ratio", "9:16")
    resolution = bridge.get("resolution", "2k")
    for ep in pkg.episodes:
        scenes_out = []
        # 每集基准场景图（episode_base：整集只生成 1 张，最省积分）
        episode_base_image = None
        if scene_mode == "episode_base" and ep.scenes:
            base_scene = ep.scenes[0]
            base_prompt = scene_prompt(cfg, base_scene, pkg.characters)
            log.info("每集基准场景图：E%d（1 张）", ep.number)
            episode_base_image = jimeng_http.text2image(
                cfg, base_prompt, ratio=ratio, resolution_type=resolution)
            log.info("基准场景图完成：%s", episode_base_image)

        for scene in ep.scenes:
            log.info("场景图（%s）：E%d S%d", scene_mode, ep.number, scene.index)
            img_prompt = scene_prompt(cfg, scene, pkg.characters)
            if scene_mode == "episode_base":
                image_url = episode_base_image
                if not image_url:
                    image_url = jimeng_http.text2image(
                        cfg, img_prompt, ratio=ratio, resolution_type=resolution)
            elif scene_mode == "reference":
                refs = [char_urls[c] for c in scene.characters if c in char_urls]
                if refs:
                    try:
                        image_url = jimeng_http.image2image(
                            cfg, refs, img_prompt, ratio=ratio, resolution_type=resolution)
                    except jimeng_http.JimengHTTPError as exc:
                        log.warning("图生图失败，退回文生图：%s", exc)
                        image_url = jimeng_http.text2image(
                            cfg, img_prompt, ratio=ratio, resolution_type=resolution)
                else:
                    image_url = jimeng_http.text2image(
                        cfg, img_prompt, ratio=ratio, resolution_type=resolution)
            else:
                image_url = jimeng_http.text2image(
                    cfg, img_prompt, ratio=ratio, resolution_type=resolution)
            log.info("场景图完成：%s", image_url)

            video_url = None
            if not skip_video:
                log.info("图生视频：E%d S%d", ep.number, scene.index)
                video_url = jimeng_http.image2video(
                    cfg, image_url, motion_prompt(cfg, scene),
                    duration=bridge.get("duration", 5),
                    video_resolution=bridge.get("video_resolution", "720p"),
                )
                log.info("视频完成：%s", video_url)

            scenes_out.append({
                "index": scene.index,
                "image_url": image_url,
                "video_url": video_url,
                "prompt": img_prompt,
                "dialogue": [[role, text] for role, text in scene.dialogue],
            })
        episodes.append({
            "number": ep.number,
            "title": ep.title,
            "scenes": scenes_out,
        })

    manifest["episodes"] = episodes
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="即梦网页版 API 剧本→素材清单生成")
    parser.add_argument("--script", required=True, help="剧本包 Markdown 路径")
    parser.add_argument("--sessionid", default=None, help="即梦网页版 sessionid（或用环境变量 JIMENG_SESSIONID）")
    parser.add_argument("--base", default=None, help="桥接服务地址（默认 http://127.0.0.1:8000）")
    parser.add_argument("--config", default=None, help="jimeng 配置（可覆盖桥接参数）")
    parser.add_argument("--out", default=None, help="manifest 输出 JSON 路径（默认打印到 stdout）")
    parser.add_argument("--skip-video", action="store_true", help="只生成图片，不生成视频（省积分）")
    parser.add_argument("--assets-only", action="store_true", help="仅素材：只生成每人 1 张定妆图 + 1 张封面图（最省积分）")
    parser.add_argument("--scene-mode", default=None, help="场景图模式：text（文生图 1 张，省积分）/ reference（图生图带定妆参考，更一致但每场景 4 张）")
    parser.add_argument("--image-model", default=None)
    parser.add_argument("--video-model", default=None)
    parser.add_argument("--resolution", default=None, help="图片分辨率 1k/2k/4k")
    parser.add_argument("--video-resolution", default=None, help="视频分辨率 480p/720p/1080p")
    parser.add_argument("--duration", type=int, default=None, help="视频时长秒（Seedance 4-15）")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = build_cfg(args)
    if args.scene_mode:
        cfg.setdefault("bridge", {})["scene_mode"] = args.scene_mode
    pkg = load_package(args.script)
    manifest = generate_manifest(
        pkg, cfg,
        skip_video=args.skip_video or args.assets_only,
        skip_scenes=args.assets_only,
        scene_mode=(cfg.get("bridge") or {}).get("scene_mode", "text"),
    )

    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print("manifest 已写入：%s" % args.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
