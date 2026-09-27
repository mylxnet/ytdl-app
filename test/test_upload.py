#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实上传闭环验证：把线上 cookies.txt 原样上传，走完整链路
（格式校验 → 备份 → 覆盖 → 真实视频验证 → 成功）。

关于 md5：**不能**断言「上传前后 md5 一致」。服务端落盘确实是
COOKIES_FILE.write_text(text) 逐字写入，但紧接着的 _verify_cookie() 会执行
yt-dlp --cookies /config/cookies.txt 做真实视频校验，而 yt-dlp 在退出时会把
内存里的 cookie jar 回写进该文件（合并跨域重复项、剔除已过期项、刷新服务端
下发的值），所以落盘文件与上传原文必然不完全一致，字节数也会变。
故本脚本改为断言「上传成功 + 关键登录凭证仍在」，md5 变化只作说明性输出，
不计入判定（详见 doc/PROJECT_STATE.md 第七节、踩坑 #17）。

在 WSL 中运行（需容器已启动）：
    python3 test/test_upload.py
"""
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8765"
SRC = "/mnt/e/work/ytdl-app/config/cookies.txt"
# 上传后必须仍然存在的关键凭证。
# LOGIN_INFO 会被 yt-dlp 回写时丢弃，故不列入；其余 4 项是认证的核心。
CRITICAL = ("SID", "SAPISID", "__Secure-1PSID", "__Secure-3PSID")

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (("  -> " + str(detail)) if detail else ""))


def md5(p):
    return subprocess.run(["md5sum", p], capture_output=True, text=True).stdout.split()[0]


def parse(p):
    """按 app.main._check_cookie_format 同规则解析，返回 (有效条目数, cookie 名集合)。"""
    names, count = set(), 0
    for raw in pathlib.Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("://"):
            continue
        cols = line.split("\t")
        if len(cols) < 7:
            continue
        count += 1
        names.add(cols[5])
    return count, names


before_md5 = md5(SRC)
before_count, _ = parse(SRC)
print("上传前 cookies.txt : md5=%s  %d 字节  有效条目=%d"
      % (before_md5, pathlib.Path(SRC).stat().st_size, before_count))

payload = pathlib.Path(SRC).read_bytes()
boundary = "----V3RealUploadBoundary"
body = bytearray()
body += ("--%s\r\n" % boundary).encode()
body += b'Content-Disposition: form-data; name="file"; filename="cookies.txt"\r\n'
body += b"Content-Type: text/plain\r\n\r\n"
body += payload
body += ("\r\n--%s--\r\n" % boundary).encode()

print("开始上传（含 yt-dlp 真实视频验证，约需 30-60 秒）...")
req = urllib.request.Request(
    BASE + "/api/cookie/upload",
    data=bytes(body),
    headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        code, resp_body = resp.status, resp.read()
except urllib.error.HTTPError as e:
    code, resp_body = e.code, e.read()
except urllib.error.URLError as e:
    print("  服务不可达：%s" % e)
    sys.exit(1)

try:
    parsed = json.loads(resp_body)
except ValueError:
    parsed = {}

print()
print("=" * 62)
print("一、上传接口")
print("=" * 62)
check("HTTP 200", code == 200, (code, resp_body[:160]))
check("ok=true", parsed.get("ok") is True, parsed)
check("解析条目数与原文件一致", parsed.get("count") == before_count,
      (parsed.get("count"), before_count))
check("命中关键凭证 >=3", len(parsed.get("auths") or []) >= 3, parsed.get("auths"))

print()
print("=" * 62)
print("二、上传后落盘内容仍可用于认证")
print("=" * 62)
after_count, after_names = parse(SRC)
print("     上传后文件 : md5=%s  %d 字节  有效条目=%d"
      % (md5(SRC), pathlib.Path(SRC).stat().st_size, after_count))
missing = [n for n in CRITICAL if n not in after_names]
check("关键登录凭证全部保留", not missing, missing or "全部保留")

print()
print("=" * 62)
print("三、md5 差异说明（不计入判定）")
print("=" * 62)
print("     yt-dlp 退出时会把 cookie jar 回写进 --cookies 指定的文件：")
print("     合并跨域重复项 / 剔除已过期项 / 刷新服务端下发的值。")
print("     故上传前后 md5 变化、字节数变化均为预期行为。")
print("     上传前 md5 : %s" % before_md5)
print("     上传后 md5 : %s" % md5(SRC))
print()
print("容器内 /config 目录:")
print(subprocess.run(["docker", "exec", "ytdl-app", "ls", "-la", "/config/"],
                     capture_output=True, text=True).stdout)

print("=" * 50)
print("汇总：PASS=%d  FAIL=%d" % (len(PASS), len(FAIL)))
if FAIL:
    print("结论: 闭环验证失败 ✗")
    for x in FAIL:
        print("  - " + x)
    sys.exit(1)
print("结论: 闭环验证通过 ✓")
