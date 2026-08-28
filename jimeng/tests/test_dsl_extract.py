# -*- coding: utf-8 -*-
"""DSL 联动测试：执行 dify/网剧自动生成.yml 中嵌的 video_pack / build_package 代码。"""
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DSL = Path(__file__).resolve().parents[2] / "dify" / "网剧自动生成.yml"


def _node_code(node_id):
    with open(DSL, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    nodes = {n["id"]: n["data"] for n in data["workflow"]["graph"]["nodes"]}
    return nodes[node_id]["code"]


def _exec(code):
    ns = {}
    exec(code, ns)
    return ns


SAMPLE_SCRIPTS = """## 第1集：一针惊四座

### 场景 1
- 场景地点/时间：市医院大厅，白天
- 人物：林川、赵德海
- 剧情与动作：赵德海当众讥讽林川
- 对白：
  - 赵德海：送外卖的也配谈医？
- 情绪：冲突
- 画面提示词（文生视频）：中景、医院大厅；林川被讥讽；2D国漫风
"""

SAMPLE_OUTLINE = """## 人物卡
- **林川**：身份——外卖员/隐世医传人；反差——人前卑微隐忍。
- **定妆描述**：23 岁清俊青年，黑色碎发，深蓝外卖冲锋衣；气质隐忍内敛。
- **沈晚晴**：身份——沈氏集团千金；反差——表面冷艳疏离。
- **定妆描述**：26 岁冷艳千金，黑色长发及腰，米白风衣；气质清冷。
"""


def test_video_pack_adds_characters():
    ns = _exec(_node_code("video_pack"))
    out = ns["main"](SAMPLE_SCRIPTS)["video_pack"]
    assert "出场角色：林川、赵德海" in out
    assert "画面提示词：中景、医院大厅；林川被讥讽；2D国漫风" in out
    assert "对白/字幕：赵德海：送外卖的也配谈医？" in out


def test_build_package_extracts_character_sheet():
    ns = _exec(_node_code("build_package"))
    pkg = ns["main"](
        outline=SAMPLE_OUTLINE,
        episode_plan="[{\"number\":1}]",
        all_scripts=SAMPLE_SCRIPTS,
        video_pack="# 文生视频提示词包",
        qa_report="# 质检报告",
        trial_mode="否",
    )["package"]
    assert "## 人物定妆表（全剧固定外观锚点）" in pkg
    assert "**林川**：23 岁清俊青年，黑色碎发，深蓝外卖冲锋衣；气质隐忍内敛。" in pkg
    assert "**沈晚晴**：26 岁冷艳千金，黑色长发及腰，米白风衣；气质清冷。" in pkg


DSL_BRIDGE = Path(__file__).resolve().parents[2] / "dify" / "网剧AI漫剧生成.yml"


def _bridge_code(node_id):
    with open(DSL_BRIDGE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    nodes = {n["id"]: n["data"] for n in data["workflow"]["graph"]["nodes"]}
    return nodes[node_id]["code"]


def test_bridge_build_payload():
    ns = _exec(_bridge_code("build_payload"))
    payload = ns["main"](
        script_package="## 三、分集剧本\n## 第1集：测试",
        session_id="sid",
        bridge_url="http://127.0.0.1:8000",
        skip_video="是",
        image_model="jimeng-4.5",
        video_model="jimeng-video-seedance-2.0",
    )["payload"]
    import json
    data = json.loads(payload)
    assert data["session_id"] == "sid"
    assert data["base_url"] == "http://127.0.0.1:8000"
    assert data["skip_video"] is True
    assert "分集剧本" in data["script_package"]


def test_bridge_parse_manifest():
    ns = _exec(_bridge_code("parse_manifest"))
    out = ns["main"]({
        "title": "测试剧",
        "characters": {"林川": "u1"},
        "episodes": [{
            "number": 1, "title": "第一集",
            "scenes": [{"index": 1, "image_url": "http://x/a.png", "video_url": "http://x/a.mp4"}],
        }],
    })
    assert "测试剧" in out["summary"]
    assert "第1集" in out["summary"]
    assert "图片 a.png" in out["summary"]
    assert "视频 a.mp4" in out["summary"]
    assert "林川" in out["manifest"]


DSL_MAIN = Path(__file__).resolve().parents[2] / "dify" / "网剧自动生成.yml"


def _main_code(node_id):
    with open(DSL_MAIN, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    nodes = {n["id"]: n["data"] for n in data["workflow"]["graph"]["nodes"]}
    return nodes[node_id]["code"]


def test_integrated_manga_prep():
    ns = _exec(_main_code("manga_prep"))
    payload = ns["main"](
        script_package="# 网剧剧本包\n## 一、大纲与人物设定",
        session_id="sid2",
        bridge_url="http://127.0.0.1:8100",
    )["payload"]
    import json
    data = json.loads(payload)
    assert data["session_id"] == "sid2"
    assert data["base_url"] == "http://127.0.0.1:8100"
    assert data["skip_video"] is False
    assert "剧本包" in data["script_package"]


def test_integrated_manga_parse():
    ns = _exec(_main_code("manga_parse"))
    out = ns["main"]({
        "title": "整合剧",
        "characters": {"林川": "u"},
        "episodes": [{"number": 2, "title": "第二集",
                      "scenes": [{"index": 1, "image_url": "http://x/i.png", "video_url": "http://x/v.mp4"}]}],
    })
    assert "第2集" in out["summary"]
    assert "图片 i.png" in out["summary"]
    assert "视频 v.mp4" in out["summary"]


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception:
                failed += 1
                print("FAIL", name)
                traceback.print_exc()
    sys.exit(1 if failed else 0)
