#!/bin/bash
BASE=http://localhost:8765
echo "=== HTTP 状态 ==="
curl -s -o /dev/null -w "HTTP %{http_code}  size %{size_download}\n" "$BASE/"
echo "=== 版本 ==="
curl -s "$BASE/api/version"
echo
echo "=== 关键文案检查 ==="
HTML=$(curl -s "$BASE/")
for key in "已缓存文件" "已下载文件" "Cookie 设置" "cookie-body hidden" "toggle-cookie" "上传 Cookie"; do
  n=$(echo "$HTML" | grep -o "$key" | wc -l)
  echo "  $key  -> $n 处"
done
