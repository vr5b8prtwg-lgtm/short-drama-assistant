# 启动即梦桥接服务（Docker 方式）。若 Docker 不可用，请改用 Node 源码方式（见 README）。
$ErrorActionPreference = "Stop"

Write-Host "== 检查 Docker =="
try {
    docker version --format "{{.Server.Version}}" | Out-Null
} catch {
    Write-Host "未检测到运行中的 Docker。请先启动 Docker Desktop，或改用 Node 源码方式（见 bridge/README.md）。" -ForegroundColor Yellow
    exit 1
}

$exists = docker ps -a --filter "name=jimeng-bridge" --format "{{.Names}}"
if ($exists) {
    Write-Host "容器已存在，直接启动..." -ForegroundColor Cyan
    docker start jimeng-bridge
} else {
    Write-Host "首次拉取并启动 jimeng-bridge（约几百 MB，请耐心等待）..." -ForegroundColor Cyan
    docker run -d --name jimeng-bridge -p 8000:8000 -e TZ=Asia/Shanghai wwwzhouhui569/jimeng-free-api-all:latest
}

Start-Sleep -Seconds 3
Write-Host ""
Write-Host "桥接服务地址: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "验证: 打开浏览器访问 http://127.0.0.1:8000/ 应看到欢迎页"
Write-Host "日志: docker logs -f jimeng-bridge"
Write-Host "下一步: 获取 sessionid 后运行 python -m jimeng.bridge.test_bridge --sessionid <你的sessionid>"
