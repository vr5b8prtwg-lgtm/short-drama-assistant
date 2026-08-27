#!/usr/bin/env bash
# 启动即梦桥接服务（Docker 方式）。若 Docker 不可用，请改用 Node 源码方式（见 README）。
set -euo pipefail

echo "== 检查 Docker =="
if ! docker version >/dev/null 2>&1; then
  echo "未检测到运行中的 Docker。请先启动 Docker Desktop，或改用 Node 源码方式（见 bridge/README.md）。" >&2
  exit 1
fi

if docker ps -a --filter "name=jimeng-bridge" --format "{{.Names}}" | grep -q jimeng-bridge; then
  echo "容器已存在，直接启动..."
  docker start jimeng-bridge
else
  echo "首次拉取并启动 jimeng-bridge（约几百 MB，请耐心等待）..."
  docker run -d --name jimeng-bridge -p 8000:8000 -e TZ=Asia/Shanghai wwwzhouhui569/jimeng-free-api-all:latest
fi

sleep 3
echo ""
echo "桥接服务地址: http://127.0.0.1:8000"
echo "验证: 打开浏览器访问 http://127.0.0.1:8000/ 应看到欢迎页"
echo "日志: docker logs -f jimeng-bridge"
echo "下一步: 获取 sessionid 后运行 python -m jimeng.bridge.test_bridge --sessionid <你的sessionid>"
