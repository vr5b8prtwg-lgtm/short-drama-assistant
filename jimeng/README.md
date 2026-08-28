# 即梦 dreamina CLI 全自动 AI 漫剧管线

基于 Dify「网剧自动生成」工作流输出的剧本包，调用即梦官方 CLI `dreamina`
（消耗你的即梦订阅套餐积分）全自动生成 **2D 国漫/日漫风、竖屏 9:16** 的 AI 漫剧整集：

`剧本包 → 人物定妆图（text2image）→ 场景图（带定妆图参考）→ 图生视频（image2video/multiframe2video）→ 豆包语音多角色配音 → 字幕 SRT → ffmpeg 合成整集 MP4`

## 前置条件

1. **即梦 CLI（dreamina）**：在 Git Bash（或 WSL/Linux/macOS 终端）安装并登录：
   ```bash
   curl -fsSL https://jimeng.jianying.com/cli | bash
   dreamina login        # 浏览器 OAuth 登录，之后复用登录态
   dreamina user_credit  # 确认登录成功并查看积分
   ```
   - 需要即梦订阅套餐（高级会员）且含 CLI 权限；生成消耗套餐积分。
   - Windows 用户：官方脚本在 Git Bash / MSYS / Cygwin 下可用，安装到 `~/bin/dreamina.exe`。
   - 若提示 `AigcComplianceConfirmationRequired`：先在即梦网页端完成该模型的一次性授权后重试。

2. **ffmpeg / ffprobe**：用于合成整集。安装后加入 PATH，或在 `config.yaml` 的 `assemble.ffmpeg_bin` 填完整路径。
   - Windows 可用 `winget install ffmpeg` 或下载静态版。

3. **Python 3.10+** 及依赖：
   ```bash
   pip install -r jimeng/requirements.txt
   ```

4. **豆包语音（可选，多角色配音）**：到火山引擎控制台创建语音应用并获取 API Key，
   填入 `config.yaml` 的 `tts.api_key`（或环境变量 `VOLC_TTS_API_KEY`）。
   未配置时管线自动跳过配音，只出画面 + 字幕。

## 快速开始

```bash
# 1) 生成用户配置（按需修改）
Copy-Item jimeng/config.example.yaml jimeng/config.yaml   # PowerShell
cp jimeng/config.example.yaml jimeng/config.yaml          # Git Bash

# 2) 用 Dify 试跑模式产出的第 1 集剧本包试跑
python -m jimeng.cli --script 剧本包.md --config jimeng/config.yaml --episodes 1

# 3) 只生成场景图快速验证（不消耗视频积分）
python -m jimeng.cli --script 剧本包.md --config jimeng/config.yaml --only-scenes

# 4) 全量
python -m jimeng.cli --script 剧本包.md --config jimeng/config.yaml
```

## 常用参数

| 参数 | 说明 |
|---|---|
| `--script` | Dify 输出的剧本包 Markdown 路径（必填） |
| `--config` | 用户配置路径（默认用 config.example.yaml） |
| `--episodes` | `all` / `1` / `1-3` / `1,3` |
| `--only-scenes` | 只生成场景图，不生成视频与成片 |
| `--skip-dubbing` | 跳过配音 |
| `--rebuild-characters` | 重新生成定妆图 |
| `--check-login-only` | 只校验 dreamina 登录与积分 |
| `--retries` | 单场景失败重试次数（默认 2） |

## 产物目录（默认 `assets/`，已 gitignore）

```
assets/
├── characters/    # 人物定妆图（跨集一致性锚点）
├── scenes/        # 场景图（9:16）
├── clips/         # 视频片段
├── audio/         # 每句配音 mp3
├── subs/          # 整集 SRT 字幕
├── episodes/      # 整集成片 MP4
└── summary.json   # 本次运行汇总（产物路径 + 失败清单）
```

## 人物一致性双保险

1. **提示词层**：剧本工作流已强制人物卡输出「定妆描述」，每场景「画面提示词」
   必须原样包含出场角色定妆描述；管线生成场景图时若发现缺失会再补一次。
2. **参考图层**：管线用定妆图作为 `image2image` 参考生成场景图（失败自动退回
   `text2image`），并在 `multiframe2video`/`image2video` 中保持同一套画面。

## 标准会员路线（不用高级会员，推荐）

如果你的即梦是标准会员（CLI 被拦截），改用**网页版 API 桥接**，积分照常可用：

1. **启动桥接服务**（二选一）：
   - Docker：`docker run -d --name jimeng-bridge -p 8000:8000 -e TZ=Asia/Shanghai wwwzhouhui569/jimeng-free-api-all:latest`
   - 或 Node 源码：`git clone https://github.com/wwwzhouhui/jimeng-free-api-all.git && cd jimeng-free-api-all && npm install && npx playwright-core install chromium && npm run dev`
   - 详见 `jimeng/bridge/README.md`
2. **取 sessionid**：浏览器登录 https://jimeng.jianying.com → F12 → Application → Cookies → 复制 `sessionid`。
3. **验证**：`python -m jimeng.bridge.test_bridge --sessionid <你的sessionid>`
4. **生成素材清单**（命令行，方便先验证）：
   ```bash
   python -m jimeng.bridge.generate --script 剧本包.md --sessionid <sessionid> --out manifest.json
   ```
   - 试跑最省积分：加 `--assets-only`，只生成「每人 1 张定妆图 + 1 张带剧名封面图」
   - 完整模式默认最省积分：**每集只生成 1 张基准场景图**，该集所有场景的视频都从它生成（`scene_mode=episode_base`）
   - 可选：`text`=每场景 1 张文生图；`reference`=图生图带定妆参考（更一致但每场景 4 张）
5. **Dify HTTP 节点自动化**：直接导入 `dify/网剧自动生成.yml`（已整合漫剧生成，无需单独导入），
   输入表单填 sessionid / 编排服务地址（Docker 版 Dify 用 http://host.docker.internal:8100，
   本机原生用 http://127.0.0.1:8100；并在 Dify .env 放行内网，见 jimeng/bridge/README.md）/
   「剧本确认后自动生成漫剧=是」，先启动本地编排服务
   `python -m jimeng.bridge.server --port 8100 --host 0.0.0.0` 与桥接服务，然后从头跑即可。
6. **合成整集**：`python -m jimeng.assemble_manifest --manifest manifest.json`

> 非官方接口（自用研究性质），可能随官方调整失效；请勿商用。

## 成本与合规

- 积分消耗大头是视频生成（image2video/multiframe2video 按秒计分）；建议先用
  `--only-scenes` 验证画面，再开视频。
- 全部画面由 AI 生成、不涉真人素材；对外发布前请自行完成内容合规审核。

## 常见问题

- **未找到 dreamina**：确认已在 Git Bash 安装并在同一 PATH；或在 `config.yaml`
  的 `dreamina.bin` 填完整路径。
- **登录失效**：重新执行 `dreamina login`（或 `relogin`）。
- **模型需授权**：`AigcComplianceConfirmationRequired` → 即梦网页端一次性授权。
- **配音不响**：检查 `tts.api_key` 是否配置；可先 `--skip-dubbing` 出片。
- **字幕时间轴不齐**：当前按每句配音实际时长或估算时长排布；合成前建议抽检。

> 各子命令最新支持的模型/比例/时长以 `dreamina <子命令> -h` 为准，管线参数在
> `config.yaml` 中可改；首次使用可先人工核对一次命令帮助。
