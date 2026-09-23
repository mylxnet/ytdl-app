#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实上传闭环验证：把现有正常 cookies.txt 原样上传，走完整链路。
   备份→覆盖→真实视频验证→成功。验证完删除本文件。"""
import json
import subprocess
import urllib.error
import urllib.request

BASE = "http://localhost:8765"
SRC = "/mnt/e/work/ytdl-app/config/cookies.txt"


def md5(p):
    """取文件 md5，用于验证上传后内容未变。"""
    return subprocess.run(["md5sum", p], capture_output=True, text=True).stdout.split()[0]


before = md5(SRC)
print("上传前线上 cookies.txt md5 :", before)

with open(SRC, "rb") as fh:
    payload = fh.read()

boundary = "----V3RealUploadBoundary"
body = bytearray()
body += ("--%s\r\n" % boundary).encode()
body += b'Content-Disposition: form-data; name="file"; filename="cookies.txt"\r\n'
body += b"Content-Type: text/plain\r\n\r\n"
body += payload
body += ("\r\n--%s--\r\n" % boundary).encode()

print("上传文件大小:", len(payload), "字节")
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

print("HTTP 状态码:", code)
print("响应体:")
try:
    parsed = json.loads(resp_body)
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
except Exception:
    print(resp_body.decode("utf-8", "replace"))

print()
after = md5(SRC)
print("上传后线上 cookies.txt md5 :", after)
print("MD5 一致(内容未变):", before == after)

print()
print("容器内备份文件时间戳:")
print(subprocess.run(["docker", "exec", "ytdl-app", "ls", "-la", "/config/"],
                     capture_output=True, text=True).stdout)

ok = code == 200 and before == after
print()
print("=" * 50)
print("结论:", "闭环验证通过 ✓" if ok else "闭环验证失败 ✗")
