# -*- coding: utf-8 -*-
"""dreamina（即梦）CLI 封装。

职责：
- 定位可执行文件、检查登录与积分（user_credit）
- 提交图像/视频生成任务（text2image / image2image / image2video / multiframe2video）
- 异步任务跟踪（query_result + --download_dir）并返回下载到的本地文件

注意事项：
- 各子命令实际支持的模型/比例/时长以 `dreamina <子命令> -h` 为准；
  本模块的参数名与 CLI 参考文档一致，生成前可先人工核对一次。
- 生成消耗即梦订阅套餐积分，运行前用 user_credit 校验。
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


class DreaminaError(Exception):
    """dreamina 调用通用错误。"""


class NotLoggedIn(DreaminaError):
    """未登录或登录已失效。"""


class TaskFailed(DreaminaError):
    """生成任务最终状态为 fail。"""


class ComplianceRequired(DreaminaError):
    """部分模型首次使用需在即梦网页端完成一次性授权。"""


def find_dreamina(cfg):
    """返回 dreamina 可执行文件路径；找不到时给出安装提示。"""
    bin_cfg = (cfg.get("dreamina") or {}).get("bin") or ""
    if bin_cfg:
        p = Path(bin_cfg).expanduser()
        if p.exists():
            return str(p)
        raise DreaminaError("配置的 dreamina 路径不存在: %s" % bin_cfg)

    exe = shutil.which("dreamina")
    if exe:
        return exe

    home = Path.home()
    candidates = [
        home / ".local/bin/dreamina",
        home / "bin/dreamina",
    ]
    if os.name == "nt":
        candidates += [
            home / ".local/bin/dreamina.exe",
            home / "bin/dreamina.exe",
            home / "AppData/Local/dreamina/dreamina.exe",
        ]
    for c in candidates:
        if c.exists():
            return str(c)

    raise DreaminaError(
        "未找到 dreamina 命令。请在 Git Bash 中安装并登录后重试：\n"
        "  curl -fsSL https://jimeng.jianying.com/cli | bash\n"
        "  dreamina login\n"
        "或在 config.yaml 的 dreamina.bin 填写完整路径。"
    )


def parse_output(text):
    """解析 CLI 输出：优先 JSON，其次尝试最后一行 JSON 对象，最后返回原始文本。"""
    text = (text or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        s = line.strip()
        if s.startswith("{"):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                continue
    return {"raw": text}


def run(cfg, args, timeout=600, cwd=None):
    """执行 dreamina 命令，返回解析后的结果（dict）。"""
    bin_path = find_dreamina(cfg)
    cmd = [bin_path] + [str(a) for a in args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        raise DreaminaError("无法执行 dreamina: %s" % bin_path)
    except subprocess.TimeoutExpired:
        raise DreaminaError("dreamina 命令超时: %s" % " ".join(cmd))

    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    result = parse_output(text)

    if "AigcComplianceConfirmationRequired" in text:
        raise ComplianceRequired(
            "该模型首次使用需在即梦网页端完成授权确认，请先在 Web 端确认后重试。"
        )

    if proc.returncode != 0:
        msg = (
            result.get("error")
            or result.get("message")
            or result.get("fail_reason")
            or text.strip()[-500:]
            or "无输出"
        )
        if "登录" in text or "login" in text.lower() or "credential" in text.lower():
            raise NotLoggedIn("dreamina 未登录或登录失效，请先运行 dreamina login。")
        raise DreaminaError("dreamina 执行失败(%d): %s" % (proc.returncode, msg))
    return result


# ---------- 登录 / 积分 ----------

def check_login(cfg):
    """校验登录态并返回积分信息（user_credit）。"""
    try:
        return run(cfg, ["user_credit"])
    except DreaminaError as exc:
        raise NotLoggedIn("dreamina 未登录或无法校验：%s" % exc)


def login_hint():
    return (
        "请在终端执行以下命令完成即梦账号登录：\n"
        "  dreamina login\n"
        "（无浏览器环境可用 dreamina login --headless 获取设备码后再 checklogin）"
    )


# ---------- 生成命令 ----------

def _poll(cfg, override=None):
    if override is not None:
        return int(override)
    return int((cfg.get("dreamina") or {}).get("poll_seconds", 30))


def text2image(cfg, prompt, ratio=None, resolution_type=None, model_version=None,
               poll=None, extra_args=None, timeout=600):
    args = ["text2image", "--prompt", prompt]
    if ratio:
        args += ["--ratio", str(ratio)]
    if resolution_type:
        args += ["--resolution_type", str(resolution_type)]
    if model_version:
        args += ["--model_version", str(model_version)]
    args += ["--poll", str(_poll(cfg, poll))]
    args += list(extra_args or [])
    return run(cfg, args, timeout=timeout)


def image2image(cfg, images, prompt, ratio=None, resolution_type=None,
                model_version=None, poll=None, extra_args=None, timeout=600):
    args = ["image2image", "--images", ",".join(str(i) for i in images), "--prompt", prompt]
    if ratio:
        args += ["--ratio", str(ratio)]
    if resolution_type:
        args += ["--resolution_type", str(resolution_type)]
    if model_version:
        args += ["--model_version", str(model_version)]
    args += ["--poll", str(_poll(cfg, poll))]
    args += list(extra_args or [])
    return run(cfg, args, timeout=timeout)


def image2video(cfg, image, prompt, duration=None, video_resolution=None,
                model_version=None, poll=None, extra_args=None, timeout=900):
    args = ["image2video", "--image", str(image), "--prompt", prompt]
    if duration:
        args += ["--duration", str(duration)]
    if video_resolution:
        args += ["--video_resolution", str(video_resolution)]
    if model_version:
        args += ["--model_version", str(model_version)]
    args += ["--poll", str(_poll(cfg, poll))]
    args += list(extra_args or [])
    return run(cfg, args, timeout=timeout)


def multiframe2video(cfg, images, prompt=None, transition_prompts=None,
                     transition_durations=None, poll=None, extra_args=None, timeout=1200):
    args = ["multiframe2video", "--images", ",".join(str(i) for i in images)]
    if prompt:
        args += ["--prompt", prompt]
    for tp in (transition_prompts or []):
        args += ["--transition-prompt", tp]
    for td in (transition_durations or []):
        args += ["--transition-duration", str(td)]
    args += ["--poll", str(_poll(cfg, poll))]
    args += list(extra_args or [])
    return run(cfg, args, timeout=timeout)


def query_result(cfg, submit_id, download_dir=None, timeout=600):
    args = ["query_result", "--submit_id", str(submit_id)]
    if download_dir:
        args += ["--download_dir", str(download_dir)]
    return run(cfg, args, timeout=timeout)


# ---------- 任务跟踪与下载 ----------

def _new_files(directory, before):
    directory = Path(directory)
    if not directory.exists():
        return []
    files = [p for p in directory.iterdir() if p.is_file() and p.name not in before]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def wait_and_download(cfg, submit_id, download_dir, before=None, max_wait=None, poll_interval=None):
    """轮询任务直至 success/fail，返回下载目录中新出现的媒体文件列表。"""
    d = Path(download_dir)
    d.mkdir(parents=True, exist_ok=True)
    before = set(before or {p.name for p in d.iterdir() if p.is_file()})
    max_wait = max_wait if max_wait is not None else int((cfg.get("dreamina") or {}).get("max_wait_seconds", 900))
    poll_interval = poll_interval if poll_interval is not None else int((cfg.get("dreamina") or {}).get("poll_interval", 10))
    deadline = time.time() + max_wait
    while True:
        result = query_result(cfg, submit_id, download_dir=str(d))
        status = str(result.get("gen_status") or "").lower()
        if status == "success":
            files = _new_files(d, before)
            if files:
                return files
        if status == "fail":
            raise TaskFailed("生成任务失败: %s" % (result.get("fail_reason") or result))
        if time.time() > deadline:
            raise DreaminaError(
                "任务超时未完成: submit_id=%s；可稍后手动执行 "
                "dreamina query_result --submit_id=%s 查询。" % (submit_id, submit_id)
            )
        time.sleep(poll_interval)


def submit_and_wait(cfg, submit_fn, download_dir, max_wait=None):
    """提交任务并等待完成，返回下载到 download_dir 的媒体文件列表。"""
    d = Path(download_dir)
    d.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in d.iterdir() if p.is_file()}
    result = submit_fn()
    submit_id = result.get("submit_id")
    if not submit_id:
        raise DreaminaError("提交结果中没有 submit_id: %s" % result)
    return wait_and_download(cfg, submit_id, d, before=before, max_wait=max_wait)
