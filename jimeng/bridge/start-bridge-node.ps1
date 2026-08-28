# 启动即梦桥接服务（Node 源码方式，本机已部署）
# 服务目录: C:\Users\24620\jimeng-free-api-all（已改用系统 Edge，无需下载 Chromium）
$dir = "C:\Users\24620\jimeng-free-api-all"
$out = Join-Path $dir "bridge.out.log"
$err = Join-Path $dir "bridge.err.log"

$running = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "端口 8000 已有服务在监听，无需重复启动。" -ForegroundColor Green
    Write-Host "验证: curl http://127.0.0.1:8000/ping 应返回 pong"
    exit 0
}

Write-Host "启动桥接服务（node dist/index.js --port 8000）..." -ForegroundColor Cyan
$proc = Start-Process -FilePath "node" `
    -ArgumentList "--enable-source-maps","--no-node-snapshot","dist/index.js","--port","8000" `
    -WorkingDirectory $dir `
    -RedirectStandardOutput $out -RedirectStandardError $err `
    -WindowStyle Hidden -PassThru

Start-Sleep -Seconds 5
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "桥接服务已启动 (pid=$($proc.Id)): http://127.0.0.1:8000" -ForegroundColor Green
    Write-Host "验证: curl http://127.0.0.1:8000/ping 应返回 pong"
} else {
    Write-Host "启动可能失败，请查看日志:" -ForegroundColor Yellow
    Get-Content $err -Tail 20 -ErrorAction SilentlyContinue
    exit 1
}
