#!/bin/bash
# 端到端测试：提交下载任务并轮询状态
RESP=$(curl -s -m 30 -X POST http://localhost:8765/api/download \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=E2Ub7KsdNRM","quality":"720","title":"e2e-test"}')
echo "SUBMIT: $RESP"
TID=$(echo "$RESP" | grep -oE '[a-f0-9]{12}')
echo "TASK=$TID"
for i in $(seq 1 15); do
  sleep 20
  S=$(curl -s -m 5 "http://localhost:8765/api/task/$TID")
  echo "[$i] $S"
  case "$S" in *'"status": "done"'*|*'"status":"done"'*) echo E2E_PASS; exit 0;; *'"status": "error"'*|*'"status":"error"'*) echo E2E_FAIL; exit 1;; esac
done
echo E2E_TIMEOUT
exit 2
