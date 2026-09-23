#!/bin/bash
# 用 curl 重传备份，定位损坏发生在接口层还是测试脚本层（不打印 cookie 明文）
set -e
SRC=/mnt/e/work/ytdl-app/config/cookies.txt
SAFE=/mnt/e/ytdl_safeback/cookies.txt.20260923-213712.safe
BASE=http://localhost:8765/api/cookie/upload

md5() { md5sum "$1" | cut -d' ' -f1; }

echo "=== 上传前 ==="
echo "  安全备份 md5 : $(md5 $SAFE)"
echo "  线上文件 md5 : $(md5 $SRC)"
echo
echo "=== curl 上传安全备份 ==="
curl -s -w "\n[HTTP %{http_code}]\n" -F "file=@$SAFE;filename=cookies.txt" "$BASE" | python3 -c "
import sys, json
raw = sys.stdin.read()
lines = raw.strip().split('\n')
body = '\n'.join(l for l in lines if not l.startswith('[HTTP'))
code = lines[-1] if lines[-1].startswith('[HTTP') else ''
print('  ' + code)
try:
    d = json.loads(body)
    print('  ok   :', d.get('ok'))
    print('  count:', d.get('count'))
    print('  auths:', d.get('auths'))
    print('  title:', d.get('title'))
except Exception:
    print('  原始响应:', raw[:300])
"
echo
echo "=== 上传后 ==="
echo "  线上文件 md5 : $(md5 $SRC)"
echo
python3 - "$SAFE" "$SRC" <<'PY'
import sys
a = open(sys.argv[1], 'rb').read()
b = open(sys.argv[2], 'rb').read()
print("  安全备份字节数 :", len(a))
print("  线上文件字节数 :", len(b))
print("  两者完全一致   :", a == b)
if a != b:
    A = a.decode('utf-8', 'replace').split('\n')
    B = b.decode('utf-8', 'replace').split('\n')
    print("  行数         : 备份=%d 线上=%d" % (len(A), len(B)))
    diff_idx = [i for i in range(min(len(A), len(B))) if A[i] != B[i]]
    print("  内容不同的行 : %d 个 (索引 %s)" % (len(diff_idx), diff_idx))
    if diff_idx:
        i = diff_idx[0]
        da, db = A[i].split('\t'), B[i].split('\t')
        print("  示例行 %d 列数 : 备份=%d 线上=%d" % (i, len(da), len(db)))
        print("  示例行 %d 列长度: 备份=%s 线上=%s" % (
            i, [len(x) for x in da], [len(x) for x in db]))
        print("  差异位置  : 第 %d 列（长度 %d → %d）" % (
            next(k for k in range(7) if da[k] != db[k]), len(da[6]), len(db[6])))
PY
