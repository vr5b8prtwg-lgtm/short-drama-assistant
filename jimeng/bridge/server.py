# -*- coding: utf-8 -*-
"""本地 HTTP 编排服务：让 Dify 的 HTTP 请求节点能一键触发「剧本包 → 素材清单」生成。

端点：
    GET  /health           健康检查
    POST /generate         生成素材清单（见下方请求体）

请求体（JSON）：
{
  "session_id": "你的即梦sessionid",
  "script_package": "剧本包 Markdown 全文",
  "base_url": "http://127.0.0.1:8000",   // 可选，桥接服务地址
  "skip_video": false,                   // 可选，true 只出图
  "image_model": "jimeng-4.5",           // 可选
  "video_model": "jimeng-video-seedance-2.0"  // 可选
}

响应：manifest JSON（与 assemble_manifest.py 兼容）。

启动：
    python -m jimeng.bridge.server --port 8100
"""
import argparse
import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ..config import load_config
from ..parse_script import parse_package
from .generate import generate_manifest

log = logging.getLogger("jimeng.bridge.server")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/generate"):
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            req = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            self._send(400, {"error": "请求体必须是 JSON：%s" % exc})
            return

        script_package = req.get("script_package") or ""
        session_id = req.get("session_id") or ""
        if not script_package:
            self._send(400, {"error": "缺少 script_package"})
            return
        if not session_id:
            self._send(400, {"error": "缺少 session_id"})
            return

        cfg = load_config(None)
        cfg.setdefault("bridge", {})
        cfg["bridge"]["base_url"] = req.get("base_url") or "http://127.0.0.1:8000"
        cfg["bridge"]["session_id"] = session_id
        if req.get("image_model"):
            cfg["bridge"]["image_model"] = req["image_model"]
        if req.get("video_model"):
            cfg["bridge"]["video_model"] = req["video_model"]

        try:
            skip_video = str(req.get("skip_video", "")).lower() in ("true", "1", "是", "yes")
            pkg = parse_package(script_package)
            manifest = generate_manifest(pkg, cfg, skip_video=skip_video)
            self._send(200, manifest)
        except Exception as exc:
            log.exception("generate 失败")
            self._send(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)


def main(argv=None):
    parser = argparse.ArgumentParser(description="即梦素材清单 HTTP 编排服务")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("编排服务已启动：http://%s:%d  （POST /generate，GET /health）", args.host, args.port)
    server.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
