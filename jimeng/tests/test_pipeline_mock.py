# -*- coding: utf-8 -*-
"""管线模块集成测试（模拟 dreamina CLI 输出，不真实联网）。"""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from jimeng import dreamina_cli, character_assets, scene_image, video_clip
from jimeng.parse_script import Scene


def make_cfg(tmp):
    tmp = Path(tmp)
    return {
        "dreamina": {"bin": "dreamina", "poll_seconds": 0, "poll_interval": 0, "max_wait_seconds": 5},
        "style": {"prefix": "2D国漫", "character_bg": "纯色背景"},
        "image": {"ratio": "9:16", "resolution_type": "2k", "model_version": "4.0",
                  "use_character_reference": True},
        "video": {"mode": "image2video", "duration": 5, "video_resolution": "1080p",
                  "model_version": "seedance2.0", "motion_prompt": "镜头缓慢推近，人物自然动作"},
        "paths": {
            "characters_dir": str(tmp / "characters"),
            "scenes_dir": str(tmp / "scenes"),
            "clips_dir": str(tmp / "clips"),
        },
        "assemble": {"ffmpeg_bin": "ffmpeg"},
    }


def fake_submit_factory(ext):
    def fake_submit(cfg, submit_fn, download_dir, max_wait=None):
        d = Path(download_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / ("gen" + ext)).write_bytes(b"FAKEDATA")
        return [d / ("gen" + ext)]
    return fake_submit


def test_character_assets_generate_and_reuse(tmp_path):
    cfg = make_cfg(tmp_path)
    pkg = SimpleNamespace(character_sheet=[("林川", "黑色短发，深蓝外套"), ("沈晚晴", "长发，米白风衣")])
    calls = {"n": 0}

    def fake_submit(cfg, submit_fn, download_dir, max_wait=None):
        calls["n"] += 1
        d = Path(download_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "gen.png").write_bytes(b"FAKE")
        return [d / "gen.png"]

    with patch.object(dreamina_cli, "submit_and_wait", side_effect=fake_submit):
        refs = character_assets.ensure_character_images(pkg, cfg)
    assert set(refs) == {"林川", "沈晚晴"}
    assert Path(refs["林川"]).exists() and Path(refs["沈晚晴"]).exists()
    n1 = calls["n"]
    with patch.object(dreamina_cli, "submit_and_wait", side_effect=fake_submit):
        refs2 = character_assets.ensure_character_images(pkg, cfg)
    assert refs2 == refs
    assert calls["n"] == n1  # 复用，不重新生成


def _submit_that_runs_fn(cfg, submit_fn, download_dir, max_wait=None):
    """真实调用提交函数（以触发被 mock 的异常/成功），再返回假文件。"""
    submit_fn()
    d = Path(download_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "gen.png"
    p.write_bytes(b"FAKE")
    return [p]


def test_scene_image_falls_back_to_text2image(tmp_path):
    cfg = make_cfg(tmp_path)
    scene = Scene(episode=1, index=1, characters=["林川"], image_prompt="医院大厅，中景")
    chars_dir = Path(tmp_path) / "characters"
    chars_dir.mkdir(parents=True, exist_ok=True)
    ref_img = chars_dir / "林川.png"
    ref_img.write_bytes(b"FAKE")
    char_refs = {"林川": str(ref_img)}
    descs = {"林川": "黑色短发，深蓝外套"}

    with patch.object(dreamina_cli, "image2image",
                      side_effect=dreamina_cli.DreaminaError("参考生成失败")) as m_i2i, \
         patch.object(dreamina_cli, "text2image",
                      return_value={"submit_id": "t2i"}) as m_t2i, \
         patch.object(dreamina_cli, "submit_and_wait",
                      side_effect=_submit_that_runs_fn) as m_sw:
        out = scene_image.generate_scene_image(scene, char_refs, descs, cfg)

    assert m_i2i.call_count == 1      # 先尝试参考生成
    assert m_t2i.call_count == 1      # 失败后回退文生图
    assert m_sw.call_count == 2
    assert Path(out).exists()


def test_generate_scene_video(tmp_path):
    cfg = make_cfg(tmp_path)
    scene = Scene(episode=1, index=1, action="林川转身看向门口")
    img = tmp_path / "s.png"
    img.write_bytes(b"FAKE")
    with patch.object(dreamina_cli, "submit_and_wait",
                      side_effect=fake_submit_factory(".mp4")) as m:
        out = video_clip.generate_scene_video(scene, str(img), cfg)
    assert Path(out).exists()
    assert m.call_count == 1


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
