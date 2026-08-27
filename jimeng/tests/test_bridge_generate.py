# -*- coding: utf-8 -*-
"""桥接编排引擎测试（模拟桥接服务，不真实联网）。"""
import json
import sys
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from jimeng.bridge import generate as gen
from jimeng.bridge import jimeng_http
from jimeng.bridge.server import Handler, ThreadingHTTPServer
from jimeng.parse_script import load_package

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_package.md"


def make_cfg(skip=False):
    return {
        "bridge": {
            "base_url": "http://127.0.0.1:8000",
            "session_id": "fake-session",
            "image_model": "jimeng-4.5",
            "video_model": "jimeng-video-seedance-2.0",
            "ratio": "9:16",
            "resolution": "2k",
            "video_resolution": "720p",
            "duration": 5,
        },
        "style": {"prefix": "2D国漫", "character_bg": "纯色背景"},
        "video": {"motion_prompt": "镜头推近"},
    }


def fake_urls(*args, **kwargs):
    return "http://127.0.0.1:8000/public/fake_%d.png" % id(args[0] if args else 0)


def test_generate_manifest_structure(tmp_path):
    pkg = load_package(FIXTURE)
    cfg = make_cfg()
    with patch.object(jimeng_http, "check_login", return_value={}), \
         patch.object(jimeng_http, "text2image", side_effect=lambda cfg, prompt, **kw: "http://x/img.png") as m_t2i, \
         patch.object(jimeng_http, "image2image", side_effect=lambda cfg, imgs, prompt, **kw: "http://x/scene.png") as m_i2i, \
         patch.object(jimeng_http, "image2video", side_effect=lambda cfg, img, prompt, **kw: "http://x/vid.mp4") as m_i2v:
        manifest = gen.generate_manifest(pkg, cfg)

    assert len(manifest["characters"]) == 2
    assert "林川" in manifest["characters"]
    assert len(manifest["episodes"]) == 1
    ep = manifest["episodes"][0]
    assert len(ep["scenes"]) == 2
    sc = ep["scenes"][0]
    assert sc["image_url"] == "http://x/scene.png"
    assert sc["video_url"] == "http://x/vid.mp4"
    assert len(sc["dialogue"]) >= 1
    # 定妆图：每位角色 1 次文生图；每场景 1 次图生图 + 1 次图生视频
    assert m_t2i.call_count == 2
    assert m_i2i.call_count == 2
    assert m_i2v.call_count == 2


def test_skip_video(tmp_path):
    pkg = load_package(FIXTURE)
    cfg = make_cfg()
    with patch.object(jimeng_http, "check_login", return_value={}), \
         patch.object(jimeng_http, "text2image", return_value="http://x/img.png"), \
         patch.object(jimeng_http, "image2image", return_value="http://x/scene.png"), \
         patch.object(jimeng_http, "image2video") as m_i2v:
        manifest = gen.generate_manifest(pkg, cfg, skip_video=True)
    assert m_i2v.call_count == 0
    assert manifest["episodes"][0]["scenes"][0]["video_url"] is None


def test_image2image_fallback(tmp_path):
    pkg = load_package(FIXTURE)
    cfg = make_cfg()
    with patch.object(jimeng_http, "check_login", return_value={}), \
         patch.object(jimeng_http, "text2image", return_value="http://x/fallback.png") as m_t2i, \
         patch.object(jimeng_http, "image2image",
                      side_effect=jimeng_http.JimengHTTPError("参考失败")) as m_i2i, \
         patch.object(jimeng_http, "image2video", return_value="http://x/vid.mp4"):
        manifest = gen.generate_manifest(pkg, cfg)
    assert m_i2i.call_count == 2
    assert m_t2i.call_count == 4  # 2 定妆图 + 2 回退
    assert manifest["episodes"][0]["scenes"][0]["image_url"] == "http://x/fallback.png"


def test_http_server_generate_endpoint(tmp_path):
    """启动真实 HTTP 服务，POST /generate 应返回 manifest（generate_manifest 被 mock）。"""
    import requests
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        pkg_text = Path(FIXTURE).read_text(encoding="utf-8")
        with patch("jimeng.bridge.server.generate_manifest",
                   return_value={"title": "t", "characters": {"林川": "u"}, "episodes": []}):
            resp = requests.post(
                "http://127.0.0.1:%d/generate" % port,
                json={"session_id": "s", "script_package": pkg_text, "skip_video": "是"},
                timeout=30,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "t"
        assert "林川" in data["characters"]
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_missing_fields(tmp_path):
    import requests
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        resp = requests.post("http://127.0.0.1:%d/generate" % port, json={}, timeout=30)
        assert resp.status_code == 400
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    import tempfile, traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
                print("PASS", name)
            except Exception:
                failed += 1
                print("FAIL", name)
                traceback.print_exc()
    sys.exit(1 if failed else 0)
