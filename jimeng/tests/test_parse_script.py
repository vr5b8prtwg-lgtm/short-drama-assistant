# -*- coding: utf-8 -*-
"""parse_script 单元测试。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parse_script import (
    load_package,
    parse_character_sheet,
    parse_dialogue,
    parse_episodes,
    parse_video_pack,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_package.md"


def test_load_package_characters():
    pkg = load_package(FIXTURE)
    assert "网剧剧本包" in pkg.title
    assert len(pkg.character_sheet) == 2
    names = [n for n, _ in pkg.character_sheet]
    assert "林川" in names and "沈晚晴" in names
    desc = dict(pkg.character_sheet)["林川"]
    assert "深蓝外卖冲锋衣" in desc


def test_character_sheet_also_in_characters_dict():
    pkg = load_package(FIXTURE)
    assert "林川" in pkg.characters
    assert "沈晚晴" in pkg.characters


def test_load_package_episodes():
    pkg = load_package(FIXTURE)
    assert len(pkg.episodes) == 1
    ep = pkg.episodes[0]
    assert ep.number == 1
    assert ep.title == "一针惊四座"
    assert len(ep.scenes) == 2


def test_scene_fields():
    pkg = load_package(FIXTURE)
    sc = pkg.episodes[0].scenes[0]
    assert sc.characters == ["林川", "赵德海"]
    assert "市医院大厅" in sc.location
    assert "当众讥讽" in sc.action
    assert "2D国漫风" in sc.image_prompt
    assert ("赵德海", "送外卖的也配谈医？") in sc.dialogue


def test_scene_dialogue_parse():
    text = """- 对白：
  - 角色A：你好
  - 角色B：再见"""
    assert parse_dialogue(text) == [("角色A", "你好"), ("角色B", "再见")]


def test_video_pack_fallback():
    pkg = load_package(FIXTURE)
    assert len(pkg.video_pack_blocks) == 2
    block = pkg.video_pack_blocks[0]
    assert block["ep"] == 1 and block["scene"] == 1
    assert "林川" in block["characters"]
    assert "画面提示词" in block["prompt"] or block["prompt"]


def test_parse_character_sheet_from_outline_only():
    text = """## 人物卡
- **张三**：身份——保安；反差——人前怂人后猛。
- **定妆描述**：30 岁平头壮汉，黑西装。
"""
    entries = parse_character_sheet(text)
    assert ("张三", "30 岁平头壮汉，黑西装。") in entries


def test_parse_episodes_heading_variants():
    text = "## 第2集：反转\n### 场景 1\n- 画面提示词（文生视频）：中景"
    eps = parse_episodes(text)
    assert eps[0].number == 2
    assert len(eps[0].scenes) == 1
    assert eps[0].scenes[0].image_prompt == "中景"


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
