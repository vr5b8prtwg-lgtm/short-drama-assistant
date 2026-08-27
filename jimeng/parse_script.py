# -*- coding: utf-8 -*-
"""剧本包解析：把 Dify 输出的剧本包 Markdown 解析为结构化数据。

支持两种来源：
1. 「三、分集剧本」逐场景字段（人物/画面提示词/对白/情绪/动作）
2. 「四、文生视频提示词包」的【第N集·场景M】块（出场角色/画面提示词/对白字幕）

人物定妆表来自「## 人物定妆表」小节；若缺失则回退从「一、大纲与人物设定」的
**定妆描述** 条目提取。
"""
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Scene:
    episode: int = 0
    index: int = 0
    characters: list = field(default_factory=list)
    location: str = ""
    action: str = ""
    dialogue: list = field(default_factory=list)  # [(role, text)]
    emotion: str = ""
    image_prompt: str = ""


@dataclass
class Episode:
    number: int = 0
    title: str = ""
    scenes: list = field(default_factory=list)


@dataclass
class Package:
    title: str = ""
    outline: str = ""
    character_sheet: list = field(default_factory=list)  # [(name, desc)]
    characters: dict = field(default_factory=dict)
    episodes: list = field(default_factory=list)
    video_pack_blocks: list = field(default_factory=list)
    raw: str = ""


# ---------- 章节切分 ----------

_SECTION_RE = re.compile(r"^##\s*[一二三四五六]、\s*(.*)$")


def split_heading(text):
    """按章节标题（## 一、/二、/三、…）切块。返回 [(标题, 内容)]。"""
    parts = []
    lines = (text or "").splitlines()
    current_title = None
    buf = []
    for line in lines:
        m = _SECTION_RE.match(line)
        if m:
            if current_title is not None:
                parts.append((current_title, "\n".join(buf).strip()))
            current_title = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current_title is not None:
        parts.append((current_title, "\n".join(buf).strip()))
    return parts


def extract_title(text):
    m = re.search(r"^#\s+([^\n]*网剧剧本包[^\n]*)", text, re.M)
    return m.group(1).strip() if m else ""


def extract_character_sheet_block(body):
    """从「一、大纲与人物设定」正文中截取 ## 人物定妆表 小节。"""
    out = []
    grab = False
    for line in (body or "").splitlines():
        if line.startswith("## 人物定妆表"):
            grab = True
            continue
        if grab:
            if line.startswith("## "):
                break
            out.append(line)
    return "\n".join(out).strip()


# ---------- 人物定妆表 ----------

def parse_character_sheet(text):
    """解析定妆条目：**角色名**：… 后跟 **定妆描述**：…；返回 [(name, desc)]。"""
    entries = []
    cur_name = None
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^[-*]?\s*\*\*(.+?)\*\*\s*[:：]\s*(.+)$", s)
        if m:
            key, val = m.group(1).strip(), m.group(2).strip()
            if key == "定妆描述":
                entries.append((cur_name or ("角色%d" % (len(entries) + 1)), val))
            elif "定妆描述" not in key:
                cur_name = key
            continue
        m2 = re.match(r"^[-*]?\s*定妆描述\s*[:：]\s*(.+)$", s)
        if m2:
            entries.append((cur_name or ("角色%d" % (len(entries) + 1)), m2.group(1).strip()))
    return entries


def parse_character_sheet_table(text):
    """解析「人物定妆表」小节：每行 - **角色名**：定妆描述。返回 [(name, desc)]。"""
    entries = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^[-*]?\s*\*\*(.+?)\*\*\s*[:：]\s*(.+)$", s)
        if m:
            entries.append((m.group(1).strip(), m.group(2).strip()))
            continue
        m2 = re.match(r"^[-*]?\s*([^：:]+?)\s*[:：]\s*(.+)$", s)
        if m2 and "定妆描述" not in m2.group(1):
            entries.append((m2.group(1).strip(), m2.group(2).strip()))
    return entries


# ---------- 分集剧本 ----------

def split_episodes(text):
    """按 '## 第N集：标题' 切分。返回 [(number, title, body)]。"""
    out = []
    lines = (text or "").splitlines()
    cur = None
    for line in lines:
        m = re.match(r"^##\s*第\s*(\d+)\s*集\s*[:：]?\s*(.*)$", line)
        if m:
            if cur is not None:
                out.append(cur)
            cur = [int(m.group(1)), m.group(2).strip(), []]
        elif cur is not None:
            cur[2].append(line)
    if cur is not None:
        out.append(cur)
    return [(n, t, "\n".join(b).strip()) for n, t, b in out]


def split_scenes(body):
    """按 '### 场景 N' 切分。返回 [(index, text)]。"""
    out = []
    lines = (body or "").splitlines()
    cur = None
    for line in lines:
        m = re.match(r"^###\s*场景\s*(\d+)", line)
        if m:
            if cur is not None:
                out.append(cur)
            cur = [int(m.group(1)), []]
        elif cur is not None:
            cur[1].append(line)
    if cur is not None:
        out.append(cur)
    return [(i, "\n".join(t).strip()) for i, t in out]


_FIELD_START = re.compile(r"^[-*]?\s*(场景地点/时间|地点/时间|人物|剧情与动作|动作|情绪|画面提示词)")


def _field_value(scene_text, key):
    m = re.search(r"^[-*]?\s*" + re.escape(key) + r"\s*[^：:]*[：:]\s*(.+)$", scene_text, re.M)
    return m.group(1).strip() if m else ""


def split_characters(value):
    """把 '林川、沈晚晴' 拆成角色名列表。"""
    if not value:
        return []
    parts = re.split(r"[、，,;；/和与及]+", value)
    return [p.strip(" \t*#") for p in parts if p.strip(" \t*#")]


def parse_dialogue(scene_text):
    """解析「对白：」块（到下一个字段行为止）。返回 [(role, text)]。"""
    out = []
    lines = (scene_text or "").splitlines()
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s.startswith("- 对白") or s.startswith("对白"):
            i += 1
            while i < n:
                t = lines[i].strip()
                if not t:
                    i += 1
                    continue
                if t.startswith("- ") and ("：" in t or ":" in t):
                    body = t[2:]
                    sep = "：" if "：" in body else ":"
                    role, text = body.split(sep, 1)
                    out.append((role.strip(), text.strip()))
                    i += 1
                    continue
                if _FIELD_START.match(t):
                    break
                if "：" in t and not t.startswith("- "):
                    role, text = t.split("：", 1)
                    out.append((role.strip(), text.strip()))
                    i += 1
                    continue
                break
            break
        i += 1
    return out


def parse_scene(ep_no, scene_idx, text):
    sc = Scene(episode=ep_no, index=scene_idx)
    sc.characters = split_characters(_field_value(text, "人物"))
    sc.location = _field_value(text, "场景地点/时间") or _field_value(text, "地点/时间")
    sc.action = _field_value(text, "剧情与动作") or _field_value(text, "动作")
    sc.emotion = _field_value(text, "情绪")
    sc.image_prompt = _field_value(text, "画面提示词")
    if not sc.image_prompt:
        sc.image_prompt = sc.action
    sc.dialogue = parse_dialogue(text)
    return sc


def parse_episodes(text):
    episodes = []
    for number, title, body in split_episodes(text):
        ep = Episode(number=number, title=title)
        for idx, scene_text in split_scenes(body):
            ep.scenes.append(parse_scene(number, idx, scene_text))
        episodes.append(ep)
    return episodes


# ---------- 文生视频提示词包 ----------

def parse_video_pack(text):
    """解析提示词包的块：{'ep','scene','characters','prompt','dialogue'}。"""
    blocks = []
    lines = (text or "").splitlines()
    cur = None
    for line in lines:
        s = line.strip()
        m = re.match(r"^【第\s*(\d+)\s*集\s*·\s*场景\s*(\d+)】$", s)
        if m:
            if cur is not None:
                blocks.append(cur)
            cur = {"ep": int(m.group(1)), "scene": int(m.group(2)),
                   "characters": [], "prompt": "", "dialogue": ""}
            continue
        if cur is None:
            continue
        if s.startswith("出场角色"):
            cur["characters"] = split_characters(s.split("：", 1)[1].strip())
        elif s.startswith("画面提示词"):
            cur["prompt"] = s.split("：", 1)[1].strip()
        elif s.startswith("对白/字幕"):
            cur["dialogue"] = s.split("：", 1)[1].strip()
    if cur is not None:
        blocks.append(cur)
    return blocks


# ---------- 入口 ----------

def parse_package(text):
    pkg = Package(raw=text)
    pkg.title = extract_title(text)
    sections = split_heading(text)
    for title, body in sections:
        t = title.strip()
        if "大纲与人物设定" in t:
            pkg.outline = body
            sheet_block = extract_character_sheet_block(body)
            if sheet_block:
                pkg.character_sheet = parse_character_sheet_table(sheet_block)
            else:
                pkg.character_sheet = parse_character_sheet(body)
        elif "分集剧本" in t:
            pkg.episodes = parse_episodes(body)
        elif "文生视频提示词包" in t:
            pkg.video_pack_blocks = parse_video_pack(body)
    pkg.characters = {name: desc for name, desc in pkg.character_sheet}

    # 用提示词包补全场景缺失字段
    for block in pkg.video_pack_blocks:
        for ep in pkg.episodes:
            if ep.number == block["ep"]:
                for sc in ep.scenes:
                    if sc.index == block["scene"]:
                        if not sc.image_prompt:
                            sc.image_prompt = block["prompt"]
                        if not sc.characters:
                            sc.characters = block["characters"]
                        if not sc.dialogue and block["dialogue"]:
                            sc.dialogue = [
                                (part.split("：", 1)[0].strip(), part.split("：", 1)[1].strip())
                                for part in block["dialogue"].split("；")
                                if "：" in part
                            ]
    return pkg


def load_package(path):
    with open(path, encoding="utf-8") as f:
        return parse_package(f.read())
