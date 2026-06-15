# brain 发布：同步源码到服务器 → 在服务器上构建并重启容器
#
# 与后端不同：opincer-brain 在服务器上通过 docker-compose 的 `build: ./brain`
# 从源码直接构建（不走 ACR 镜像）。因此发布流程是：
#   1. 备份服务器现有 brain 目录（兜底）。
#   2. 用 scp 覆盖式同步本地源码到服务器（覆盖同名文件，不删除服务器独有文件，
#      因此服务器上未纳入本仓库的本地改动——如 OCR 扩展——会被保留）。
#   3. 在服务器上 docker compose build brain && up -d --force-recreate brain。
#   4. 健康检查 + /embed 路由校验。
#
# 用法：在 PowerShell 中执行  ./scripts/deploy-brain.ps1
# 注意：DASHSCOPE_API_KEY 等密钥由服务器 /opt/deploy/opincer/.env 管理，本脚本不涉及。

$ErrorActionPreference = "Stop"

$ECS_HOST = "root@121.199.37.162"
$ECS_KEY = "$env:USERPROFILE\.ssh\id_ed25519"
$REMOTE_DIR = "/opt/deploy/opincer"
$REMOTE_BRAIN = "$REMOTE_DIR/brain"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BrainDir = Split-Path -Parent $ScriptDir   # claw-works/opincer-brain

# 国内网络下 git 常走代理，但 scp/ssh 直连服务器；如本机 ssh 走了不可达代理可在此排查。
$SSH = "ssh -i `"$ECS_KEY`" -o StrictHostKeyChecking=no"

function Invoke-RemoteSsh($cmd) {
    & ssh -i $ECS_KEY -o StrictHostKeyChecking=no $ECS_HOST $cmd
    if ($LASTEXITCODE -ne 0) { throw "远程命令失败 (exit $LASTEXITCODE): $cmd" }
}

Write-Host "=== [1/4] 备份服务器现有 brain 目录 ==="
# 用时间戳 tar 备份，保留最近一次即可（仅兜底，验证无误后可手动清理）。
Invoke-RemoteSsh "cd $REMOTE_DIR && tar czf brain.bak.tar.gz brain && echo BACKUP_OK"

Write-Host "=== [2/4] 同步源码到服务器（覆盖同名文件，保留服务器独有文件）==="
# 仅同步构建所需内容：app/ 源码、requirements*.txt、Dockerfile。
# scp 不会删除服务器上多出的文件，因此服务器本地改动（未提交到本仓库的）得以保留。
& scp -i $ECS_KEY -o StrictHostKeyChecking=no -r `
    "$BrainDir\app" `
    "$BrainDir\requirements.txt" `
    "$BrainDir\Dockerfile" `
    "${ECS_HOST}:$REMOTE_BRAIN/"
if ($LASTEXITCODE -ne 0) { throw "scp 同步失败 (exit $LASTEXITCODE)" }

# requirements-dev.txt 仅本地测试用，存在则一并同步（可选）。
if (Test-Path "$BrainDir\requirements-dev.txt") {
    & scp -i $ECS_KEY -o StrictHostKeyChecking=no `
        "$BrainDir\requirements-dev.txt" "${ECS_HOST}:$REMOTE_BRAIN/" | Out-Null
}

Write-Host "=== [3/4] 在服务器上构建并重启 brain ==="
Invoke-RemoteSsh "cd $REMOTE_DIR && docker compose build brain && docker compose up -d --force-recreate brain"

Write-Host "=== [4/4] 健康检查 ==="
# 等待容器就绪后校验状态、/embed 路由与 DASHSCOPE 注入。
Invoke-RemoteSsh @"
sleep 6
echo '--- 容器状态 ---'
docker ps --filter name=opincer-brain --format '{{.Names}} {{.Status}}'
echo '--- 路由 ---'
docker exec opincer-brain python -c "from app.main import app; print([r.path for r in app.routes])"
echo '--- DASHSCOPE_API_KEY 注入 ---'
docker exec opincer-brain printenv DASHSCOPE_API_KEY >/dev/null 2>&1 && echo SET || echo MISSING
"@

Write-Host ""
Write-Host "=== brain 发布完成 ==="
Write-Host "提示：服务器备份在 $REMOTE_DIR/brain.bak.tar.gz，确认无误后可删除。"
Write-Host "可选冒烟测试 /embed："
Write-Host "  curl -s -X POST http://localhost:8000/embed -H 'Content-Type: application/json' -d '{\""texts\"":[\""你好\""],\""text_type\"":\""document\"",\""dimension\"":1024}'"
