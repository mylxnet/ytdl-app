#!/bin/bash
# 方案 B：禁用 buildx provenance 重新构建镜像，然后推送 ACR
# 用法：在项目根目录执行  bash scripts/_rebuild_push.sh [版本号]
#       版本号省略时用脚本内默认值（发布新版本时请显式传入）
# 例：  bash scripts/_rebuild_push.sh v3.0.2
set -e

REG="registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app"
VER="${1:-v3.0.2}"          # 目标版本 tag，可由第一个参数覆盖
# 脚本所在目录的上一级 = 项目根
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== 目标版本：$VER ==="

echo ""
echo "=== 0. 检查 buildx 版本 ==="
docker buildx version 2>&1 || docker buildx 2>&1 | head -3

echo ""
echo "=== 1. 停止运行中容器（释放镜像占用） ==="
docker stop ytdl-app 2>&1 || true
docker rm ytdl-app 2>&1 || true

echo ""
echo "=== 2. 清理旧镜像 ==="
docker rmi ytdl-app:latest 2>/dev/null || true
docker rmi "$REG:$VER" 2>/dev/null || true
docker rmi "$REG:latest" 2>/dev/null || true

echo ""
echo "=== 3. 用 buildx 重新构建，禁用 provenance ==="
date +"%H:%M:%S  start build"
cd "$SRC_DIR"
docker buildx build \
    --no-cache \
    --provenance=false \
    --platform linux/amd64 \
    -t ytdl-app:latest \
    . 2>&1 | tail -30
date +"%H:%M:%S  end build"

echo ""
echo "=== 4. 验证新镜像无 attestation ==="
docker image inspect ytdl-app:latest --format 'ID:{{.ID}}'
echo "RepoDigests: $(docker image inspect ytdl-app:latest --format '{{.RepoDigests}}' 2>/dev/null)"

echo ""
echo "=== 5. 起容器确认能跑 ==="
cd "$SRC_DIR"
docker compose -f deploy/docker-compose.yml up -d 2>&1 | tail -5
sleep 3
curl -s http://localhost:8765/api/version || true

echo ""
echo "=== 6. 打 ACR tag ==="
docker tag ytdl-app:latest "$REG:$VER"
docker tag ytdl-app:latest "$REG:latest"
docker images "$REG" --format '  {{.Repository}}:{{.Tag}}  {{.Size}}  {{.ID}}'

echo ""
echo "=== 7. 推送 $VER ==="
date +"%H:%M:%S  start $VER"
docker push "$REG:$VER" 2>&1 | tail -30
date +"%H:%M:%S  end $VER"

echo ""
echo "=== 8. 推送 latest ==="
date +"%H:%M:%S  start latest"
docker push "$REG:latest" 2>&1 | tail -30
date +"%H:%M:%S  end latest"

echo ""
echo "=== 9. 远端 manifest 校验（只取元信息，不下载镜像本体） ==="
docker buildx imagetools inspect "$REG:$VER" 2>&1 | head -12 || true
docker buildx imagetools inspect "$REG:latest" 2>&1 | head -12 || true

echo ""
echo "=== 完成：$VER + latest 已推送 ==="
