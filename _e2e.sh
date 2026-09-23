#!/bin/bash
# 端到端验证：probe -> download(360p) -> 轮询 -> 校验 -> 清理现场
set -u
BASE=http://localhost:8765
URL='https://www.youtube.com/watch?v=dQw4w9WgXcQ'
IDS=dQw4w9WgXcQ

echo "=== [1] probe ==="
RESP=$(curl -s -X POST "$BASE/api/probe" -H 'Content-Type: application/json' \
  --data "{\"url\":\"$URL\"}")
echo "$RESP"
TITLE=$(printf '%s' "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("title",""))')
DUR=$(printf '%s' "$RESP"  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("duration",0))')
echo ">>> 标题: $TITLE | 时长: ${DUR}s"
[ -z "$TITLE" ] && { echo "probe 失败，中止"; exit 1; }

echo
echo "=== [2] download quality=360 ==="
TASK=$(curl -s -X POST "$BASE/api/download" -H 'Content-Type: application/json' \
  --data "{\"url\":\"$URL\",\"quality\":\"360\",\"title\":\"$TITLE\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("task_id",""))')
echo ">>> task_id: $TASK"
[ -z "$TASK" ] && { echo "提交失败，中止"; exit 1; }

echo
echo "=== [3] 轮询状态（最长 180s） ==="
FINAL=""
for i in $(seq 1 90); do
  RAW=$(curl -s "$BASE/api/task/$TASK")
  ST=$(printf '%s' "$RAW" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(f"{d.get(\"status\")}|{d.get(\"progress\",0):.1f}%|{d.get(\"speed\",\"\")}|{(d.get(\"error\") or \"\")[:80]}")')
  echo "  t=$((i*2))s  $ST"
  S="${ST%%|*}"
  case "$S" in
    done)  FINAL="done";  break;;
    error) FINAL="error"; echo "  原始响应: $RAW"; exit 1;;
  esac
  sleep 2
done
echo ">>> 任务结果: ${FINAL:-超时}"

echo
echo "=== [4] 文件列表 ==="
curl -s "$BASE/api/files" | python3 -c '
import sys,json
d=json.load(sys.stdin)
for it in d.get("items",[]):
    print(f"  {it[\"kind\"]:6s} {it[\"size\"]/1024/1024:7.1f}MB  {it[\"name\"]}")
'

echo
echo "=== [5] 下载接口 header（Range / Content-Disposition） ==="
NEW=$(curl -s "$BASE/api/files" | python3 -c '
import sys,json,urllib.parse
for it in json.load(sys.stdin).get("items",[]):
    if f"{IDS}" in it["name"]:
        print(urllib.parse.quote(it["name"],safe=""));break
')
echo "  新文件(URL编码): $NEW"
if [ -n "$NEW" ]; then
  echo "  --- 无 Range ---"
  curl -s -D - -o /dev/null "$BASE/api/download-file?name=$NEW" | grep -iE '^(HTTP|Content-(Disposition|Length|Type)|Accept-Ranges)'
  echo "  --- 带 Range: bytes=0-1023 ---"
  curl -s -D - -o /dev/null -H "Range: bytes=0-1023" "$BASE/api/download-file?name=$NEW" | grep -iE '^(HTTP|Content-(Disposition|Length|Range|Type))'
fi

echo
echo "=== [6] 删除新下载的文件（清理现场） ==="
if [ -n "$NEW" ]; then
  curl -s -X DELETE "$BASE/api/delete-file?name=$NEW"
  echo
fi

echo
echo "=== [7] 复核剩余文件 ==="
curl -s "$BASE/api/files" | python3 -c '
import sys,json
items=json.load(sys.stdin).get("items",[])
print(f"  剩余 {len(items)} 个:")
for it in items: print(f"   - {it[\"name\"]}")
'
