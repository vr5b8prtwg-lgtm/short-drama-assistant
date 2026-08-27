# -*- coding: utf-8 -*-
"""subtitle 单元测试。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from subtitle import build_srt, format_ts, write_srt


def test_format_ts():
    assert format_ts(0) == "00:00:00,000"
    assert format_ts(65.5) == "00:01:05,500"
    assert format_ts(3661.25) == "01:01:01,250"


def test_build_srt_basic():
    srt = build_srt([("A", "你好"), ("B", "再见")], default_line_seconds=2.0, gap_seconds=0.5)
    assert srt.count("\n\n") >= 1
    assert "00:00:00,000 --> 00:00:02,000" in srt
    assert "00:00:02,500 --> 00:00:04,500" in srt
    assert "你好" in srt and "再见" in srt
    assert srt.strip().startswith("1\n")


def test_build_srt_with_durations():
    srt = build_srt([("A", "短"), ("B", "很长很长")], durations=[1.0, 3.0],
                    default_line_seconds=2.0, gap_seconds=0.2)
    assert "00:00:00,000 --> 00:00:01,000" in srt
    assert "00:00:01,200 --> 00:00:04,200" in srt


def test_build_srt_offset():
    srt = build_srt([("A", "你好")], default_line_seconds=2.0, gap_seconds=0.2, offset_seconds=10.0)
    assert "00:00:10,000 --> 00:00:12,000" in srt


def test_empty_dialogue():
    assert build_srt([]) == ""


def test_write_srt(tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = write_srt(Path(d) / "a.srt", build_srt([("A", "hi")]))
        assert p is not None
        assert Path(p).read_text(encoding="utf-8").strip().endswith("hi")


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
