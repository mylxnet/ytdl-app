#!/bin/bash
# 把 config/cookies.txt 备份到项目外的安全位置做双保险
# 用法：在项目根目录执行  bash tools/_backup.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/config/cookies.txt"
SAFE="${YTDL_SAFE_BACKUP_DIR:-$ROOT/../ytdl_safeback}"
mkdir -p "$SAFE"
cp -p "$SRC" "$SAFE/cookies.txt.$(date +%Y%m%d-%H%M%S).safe"
echo "=== 项目外安全备份 ==="
ls -la "$SAFE/"
echo
echo "=== 线上文件 md5（验证前基线）==="
md5sum "$SRC"
echo
echo "=== 备份文件 md5（应与线上完全一致）==="
md5sum "$SAFE"/*.safe
