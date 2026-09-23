#!/bin/bash
# 用正确的列（第6列=cookie名）重新校验（测试完删除）
for F in /mnt/e/work/ytdl-app/config/cookies.txt /mnt/e/work/ytdl-app/config/cookies.txt.bak; do
  echo "=== $F ==="
  echo "-- 第6列(cookie名) 关键凭证命中 --"
  awk -F"\t" 'NF>=7 {print $6}' "$F" | grep -E "^(SID|SAPISID|__Secure-1PSID|LOGIN_INFO)$" | sort | uniq -c
  echo "-- 第6列前12个cookie名 --"
  awk -F"\t" 'NF>=7 {print $6}' "$F" | sort -u | head -12
  echo "-- 每行字段数 --"
  awk -F"\t" '{print NF}' "$F" | sort | uniq -c | sort -rn
  echo
done
