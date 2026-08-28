# 即梦网页版 API 本地桥接（标准会员可用）

## 为什么需要它

`dreamina` CLI 被即梦限制为「高级及以上会员」，但**即梦网页版的后台接口本身不限制会员等级**——
只要账号有积分（标准会员的 785 积分、甚至每日赠送积分），就能生成图片/视频。

本项目用社区开源的逆向服务 **jimeng-free-api-all** 把网页版接口封装成 OpenAI 兼容 API，
Dify 的 HTTP 请求节点直接调用它即可，从而**用标准会员绕开 CLI 的高级会员门槛**。

> ⚠️ 说明：这是非官方接口（自用研究性质）。接口可能随官方调整而失效；
> 请仅自用、不要对外提供商用服务。官方免责声明见 jimeng-free-api-all 项目。

## 架构

```
Dify 工作流（HTTP 请求节点）
        │  POST http://127.0.0.1:8000/v1/images/generations（Bearer sessionid）
        ▼
本地桥接服务 jimeng-free-api-all（Node/Playwright，负责签名/刷新token/轮询）
        │  即梦网页版后台接口（mweb/v1/...）
        ▼
即梦官方（消耗你的积分）
```

## 〇、本机实际部署（2026-08-28）

Docker 镜像在本机拉取失败（镜像源损坏/不可达），已改用 **Node 源码方式**部署并运行：

- 源码目录：`C:\Users\24620\jimeng-free-api-all`（克隆自 laixiao/jimeng-free-api-all）
- 依赖：`npm install` 已完成；**已改用系统 Edge**（`chromium.launch({channel: "msedge"})`，
  并把启动参数改为 Windows 兼容集，见 src/lib/browser-service.ts），无需下载 Chromium
- 当前状态：服务已在后台运行，监听 `http://127.0.0.1:8000`（验证 `curl http://127.0.0.1:8000/ping` → pong）
- 以后启动：运行项目里 `jimeng/bridge/start-bridge-node.ps1`（会自动检测端口）
- ffmpeg：已用 `winget install Gyan.FFmpeg` 安装（完整版含 libx264），路径见 `jimeng/config.yaml` 的 `assemble.ffmpeg_bin`；合成脚本会从系统临时目录启动 ffmpeg（OneDrive 路径下直接启动会被拒绝）
- **Seedance 2.0 视频需先在即梦网页端完成一次「安全确认」**（首次使用会返回「需要安全确认，请刷新页面重试」）；未确认前可用 `jimeng-video-3.5-pro` 等普通模型，已实测可用
- 停止：`Stop-Process -Id <pid>` 或结束 node 进程；日志在 `C:\Users\24620\jimeng-free-api-all\bridge.out.log`

> 若以后想换回 Docker：镜像 `wwwzhouhui569/jimeng-free-api-all:latest` 在本机网络下不可用，
> 需先清理 daemon.json 里的镜像加速器（含占位符 your_preferred_mirror）再重试。

## 一、安装与启动桥接服务

### 方式 A：Docker（推荐，最简单）

```powershell
# 拉取并启动（首次会自动下载镜像，约几百 MB）
docker run -d --name jimeng-bridge -p 8000:8000 -e TZ=Asia/Shanghai wwwzhouhui569/jimeng-free-api-all:latest

# 查看日志
docker logs -f jimeng-bridge
```

也可以直接运行本目录脚本：`.\start-bridge.ps1`

### 方式 B：Node 源码运行

```bash
# 需要 Node.js 16+（本机已有 E:\Node）
git clone https://github.com/wwwzhouhui/jimeng-free-api-all.git jimeng-free-api-all
cd jimeng-free-api-all
npm install
npx playwright-core install chromium --with-deps   # Seedance 视频需要
npm run dev
```

启动成功后访问 `http://127.0.0.1:8000/` 能看到欢迎页即成功。

## 二、获取你的 sessionid（即梦网页版登录令牌）

1. 用浏览器打开 https://jimeng.jianying.com/ 并登录（就是你有积分的那个账号）
2. 按 `F12` 打开开发者工具
3. 切到 `Application → Cookies → https://jimeng.jianying.com`
4. 找到名为 `sessionid` 的 Cookie，复制它的值

> ⚠️ sessionid 等同账号凭证，请勿泄露给他人；只在你自己机器上用。

## 三、验证连通性（关键一步）

把上一步的 sessionid 填入环境变量或参数，运行：

```powershell
# PowerShell
$env:JIMENG_SESSIONID = "你的sessionid"
python -m jimeng.bridge.test_bridge --base http://127.0.0.1:8000

# 或直接传参
python -m jimeng.bridge.test_bridge --sessionid 你的sessionid --base http://127.0.0.1:8000
```

成功会输出生成的图片 URL（如 `http://127.0.0.1:8000/public/...`）。
这一步通过后，Dify 工作流里的 HTTP 节点就能用了。

想顺便验证视频接口（文生视频）：
```powershell
python -m jimeng.bridge.test_bridge --sessionid 你的sessionid --video
```

## 四、在 Dify 里配置

1. 在 Dify 中导入工作流 **网剧自动生成**（`dify/网剧自动生成.yml`，已整合漫剧生成，不再需要单独的漫剧工作流）
2. 到 Dify 的「环境变量」里新增：
   - `JIMENG_SESSIONID` = 你的 sessionid
   - `JIMENG_BRIDGE_URL` = `http://127.0.0.1:8000`（若 Dify 跑在 Docker 容器里，改成 `http://host.docker.internal:8000`）
3. 运行工作流，输入剧本包文本，输出每场景的图片/视频 URL 清单
4. 用 `python -m jimeng.assemble_manifest --manifest 清单.json` 下载 URL 并合成整集 MP4

## 常见问题

- **Dify 在 Docker 里访问不到本机 8000**：把 `JIMENG_BRIDGE_URL` 设为 `http://host.docker.internal:8000`
- **报积分不足/无权限**：确认 sessionid 对应的账号有积分（标准会员 785 积分可用）
- **Seedance 视频生成失败**：确认桥接服务容器里有 Chromium（Docker 镜像自带；源码方式需 `npx playwright-core install chromium`）；部分模型首次使用需先在网页版用过一次
- **接口失效**：即梦可能调整接口，留意 jimeng-free-api-all 仓库更新
