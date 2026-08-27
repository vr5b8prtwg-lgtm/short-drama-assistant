# -*- coding: utf-8 -*-
"""连通性验证：用你的即梦 sessionid 调用本地桥接服务（OpenAI 兼容接口）。

用法：
    python -m jimeng.bridge.test_bridge --sessionid <sessionid> [--base http://127.0.0.1:8000] [--video]
    # 或用环境变量 JIMENG_SESSIONID
"""
import argparse
import os
import sys

import requests

IMAGE_MODEL = "jimeng-4.5"
VIDEO_MODEL = "jimeng-video-seedance-2.0"


def call(base, sessionid, endpoint, payload, timeout=600):
    url = base.rstrip("/") + endpoint
    headers = {
        "Authorization": "Bearer " + sessionid,
        "Content-Type": "application/json",
    }
    print("POST %s" % url)
    print("payload: %s" % payload)
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        print("请求失败：%s" % exc)
        return None
    print("HTTP %s" % resp.status_code)
    try:
        data = resp.json()
    except ValueError:
        print("响应非 JSON：%s" % resp.text[:500])
        return None
    if resp.status_code >= 400:
        print("接口报错：%s" % data)
        return None
    return data


def test_image(base, sessionid, prompt):
    data = call(base, sessionid, "/v1/images/generations", {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "ratio": "9:16",
        "resolution": "2k",
        "n": 1,
    })
    if not data:
        return False
    items = data.get("data") or []
    if not items or not items[0].get("url"):
        print("未返回图片 URL：%s" % data)
        return False
    print("图片生成成功：%s" % items[0]["url"])
    return True


def test_video(base, sessionid, prompt):
    data = call(base, sessionid, "/v1/videos/generations", {
        "model": VIDEO_MODEL,
        "prompt": prompt,
        "ratio": "9:16",
        "resolution": "720p",
        "duration": 5,
    }, timeout=1200)
    if not data:
        return False
    items = data.get("data") or []
    if not items or not items[0].get("url"):
        print("未返回视频 URL：%s" % data)
        return False
    print("视频生成成功：%s" % items[0]["url"])
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="即梦桥接服务连通性验证")
    parser.add_argument("--sessionid", default=None, help="即梦网页版 sessionid（或用环境变量 JIMENG_SESSIONID）")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="桥接服务地址")
    parser.add_argument("--prompt", default="一个穿深蓝外套的年轻男子站在医院大厅，2D国漫风格，竖屏9:16", help="测试提示词")
    parser.add_argument("--video", action="store_true", help="同时验证视频生成（耗积分）")
    args = parser.parse_args(argv)

    sessionid = args.sessionid or os.environ.get("JIMENG_SESSIONID", "")
    if not sessionid:
        print("缺少 sessionid：请用 --sessionid 传入或设置环境变量 JIMENG_SESSIONID")
        return 2

    ok = test_image(args.base, sessionid, args.prompt)
    if args.video:
        ok2 = test_video(args.base, sessionid, args.prompt)
        ok = ok and ok2
    print("== 验证%s ==" % ("通过" if ok else "失败（见上方输出）"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
