#!/bin/bash
# 把线上 cookies.txt 备份到项目外的安全位置做双保险（测试完删除脚本，保留备份）
set -e
SRC=/mnt/e/work/ytdl-app/config/cookies.txt
SAFE=/mnt/e/ytdl_safeback
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
