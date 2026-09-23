#!/bin/bash
# 复核脚本：查任务状态 + 文件列表 + 下载接口 header + 删除 + 复核
set -u
BASE=http://localhost:8765
TID=${1:-29e7482177d8}
IDS=dQw4w9WgXcQ

echo "=== [A] 任务 $TID 最终状态 ==="
curl -s "$BASE/api/task/$TID" | python3 -m json.tool

echo
echo "=== [B] 当前文件列表 ==="
curl -s "$BASE/api/files" | python3 -c '
import sys,json
for it in json.load(sys.stdin).get("items",[]):
    print("  %-6s %8.2f MB  %s" % (it["kind"], it["size"]/1048576, it["name"]))
'

echo
echo "=== [C] 新下载文件的下载接口 header ==="
NEW=$(curl -s "$BASE/api/files" | python3 -c "
import sys,json,urllib.parse
ids='${IDS}'
for it in json.load(sys.stdin).get('items',[]):
    if ids in it['name']:
        print(urllib.parse.quote(it['name'],safe=''));break
")
echo "  URL编码名: $NEW"
if [ -n "$NEW" ]; then
  echo "  --- 完整下载(无 Range) ---"
  curl -s -D - -o /dev/null "$BASE/api/download-file?name=$NEW" \
    | grep -iE '^(HTTP|Content-(Disposition|Length|Type)|Accept-Ranges)'
  echo "  --- Range: bytes=0-1023 ---"
  curl -s -D - -o /dev/null -H "Range: bytes=0-1023" "$BASE/api/download-file?name=$NEW" \
    | grep -iE '^(HTTP|Content-(Disposition|Length|Range|Type))'
  echo
  echo "=== [D] 删除新下载文件（清理现场） ==="
  curl -s -X DELETE "$BASE/api/file?name=$NEW"
  echo
  echo
  echo "=== [E] 复核剩余文件 ==="
  curl -s "$BASE/api/files" | python3 -c '
import sys,json
items=json.load(sys.stdin).get("items",[])
print("  剩余 %d 个:" % len(items))
for it in items: print("   - %s" % it["name"])
'
fi
