#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3 回归测试：路径穿越 / 接口结构 / 预览流式 / 上传失败路径。
在 WSL 内运行，输出真实 HTTP 响应作为可核实证据。测试完删除。"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8765"
PASS, FAIL = [], []


def req(method, path, data=None, headers=None, timeout=25):
    """发请求，返回 (status, headers, body_bytes)。"""
    r = urllib.request.Request(BASE + path, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (("  -> " + str(detail)) if detail else ""))


print("=" * 62)
print("一、路径穿越拦截（预期全部 404）")
print("=" * 62)
traversal = [
    "../../etc/passwd",
    "..%2F..%2Fetc%2Fpasswd",
    "..",
    "",
    "/etc/passwd",
    "....//....//etc/passwd",
    "a\ninjected.txt",
]
for raw in traversal:
    encoded = urllib.parse.quote(raw, safe="%")
    code, _, body = req("GET", "/api/preview?name=" + encoded)
    print("    name=%r -> %d %s" % (raw, code, body[:80]))
    check("preview 拦截 %r" % raw, code == 404)

print()
print("=" * 62)
print("二、接口结构")
print("=" * 62)
code, _, body = req("GET", "/api/version")
v = json.loads(body)
print("    GET /api/version  -> %d  %s" % (code, body[:120]))
check("/api/version 返回 3.0.3", code == 200 and v.get("version") == "3.0.3")

code, _, body = req("GET", "/api/files")
f = json.loads(body)
names = [i["name"] for i in f.get("items", [])]
kinds = {i.get("kind") for i in f.get("items", [])}
print("    GET /api/files    -> %d  文件数=%d  kind=%s" % (code, len(names), kinds))
check("/api/files 含 name/size/mtime/kind", all(
    all(k in i for k in ("name", "size", "mtime", "kind")) for i in f["items"]))

print()
print("=" * 62)
print("三、预览流式（HTTP Range，取体积最小的文件）")
print("=" * 62)
if names:
    target = min(f["items"], key=lambda i: i["size"])["name"]
    print("    测试文件: %s" % target[:60])
    full_code, full_h, _ = req("GET", "/api/preview?name=" + urllib.parse.quote(target), timeout=30)
    print("    完整请求  -> %d  Content-Length=%s" % (full_code, full_h.get("Content-Length")))
    rng_code, rng_h, rng_body = req(
        "GET", "/api/preview?name=" + urllib.parse.quote(target),
        headers={"Range": "bytes=0-999"}, timeout=30)
    print("    Range 0-999 -> %d  Content-Range=%s  实收=%d 字节"
          % (rng_code, rng_h.get("Content-Range"), len(rng_body)))
    check("预览支持 206 Partial Content", rng_code == 206,
          "%d, Content-Range=%s" % (rng_code, rng_h.get("Content-Range")))
    check("Range 实收 1000 字节", len(rng_body) == 1000, len(rng_body))

    print()
    print("=" * 62)
    print("四、下载接口 Content-Disposition")
    print("=" * 62)
    dl_code, dl_h, dl_body = req(
        "GET", "/api/download-file?name=" + urllib.parse.quote(target),
        headers={"Range": "bytes=0-199"}, timeout=30)
    print("    GET /api/download-file -> %d" % dl_code)
    print("      Content-Disposition = %s" % dl_h.get("Content-Disposition"))
    print("      Content-Range       = %s" % dl_h.get("Content-Range"))
    check("下载接口返回附件头", "attachment" in (dl_h.get("Content-Disposition") or ""))
    check("下载接口支持 Range", dl_code == 206 and len(dl_body) == 200, len(dl_body))

    print()
    print("=" * 62)
    print("五、删除接口拦截（不真删现有文件）")
    print("=" * 62)
    for raw in ["__no_such_file__.mp4", "../../etc/passwd"]:
        c2, _, b2 = req("DELETE", "/api/file?name=" + urllib.parse.quote(raw))
        print("    DELETE name=%r -> %d %s" % (raw, c2, b2[:80]))
        check("DELETE 拦截 %r" % raw, c2 == 404)

print()
print("=" * 62)
print("六、Cookie 上传失败路径（multipart/form-data, 字段名 file）")
print("=" * 62)


def upload(filename, content: bytes):
    """构造 multipart 请求体上传 cookies 文件。"""
    boundary = "----V3TestBoundary7MA4YWxkTrZu0gW"
    body = bytearray()
    body += ("--%s\r\n" % boundary).encode()
    body += ('Content-Disposition: form-data; name="file"; filename="%s"\r\n' % filename).encode()
    body += b"Content-Type: text/plain\r\n\r\n"
    body += content
    body += b"\r\n"
    body += ("--%s--\r\n" % boundary).encode()
    return req("POST", "/api/cookie/upload", data=bytes(body),
               headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})


print()
print("  6.1 未提供文件（空 multipart）")
c, _, b = req("POST", "/api/cookie/upload",
              data=b"--b\r\n--b--\r\n",
              headers={"Content-Type": "multipart/form-data; boundary=b"})
print("    -> %d %s" % (c, b[:220]))
check("未提供文件返回 400", c == 400)

print()
print("  6.2 非 .txt 扩展名")
c, _, b = upload("bad.exe", b"foo")
print("    -> %d %s" % (c, b[:220]))
check("非 .txt 被拒绝", c == 400)

print()
print("  6.3 内容格式错误")
c, _, b = upload("notacookie.txt", b"this is not a cookie file\njust random text\n")
print("    -> %d %s" % (c, b[:280]))
check("格式错误被拒绝", c == 400)

print()
print("  6.4 行数不足")
c, _, b = upload("too_few.txt",
                 b"www.youtube.com\tTRUE\t/\tTRUE\t0\taaaa\tbbbb\n")
print("    -> %d %s" % (c, b[:280]))
check("行数不足被拒绝", c == 400)

print()
print("  6.5 行数够但缺关键凭证")
rows = ["www.youtube.com\tTRUE\t/\tTRUE\t9999999999\tp%d\tv%d\n" % (i, i) for i in range(12)]
c, _, b = upload("no_auth.txt", "".join(rows).encode())
print("    -> %d %s" % (c, b[:320]))
check("缺关键凭证被拒绝", c == 400)

print()
print("  6.6 上传失败后服务存活（服务未被破坏）")
c, _, b = req("GET", "/api/version")
print("    服务仍存活 -> %d" % c)
check("上传失败后服务存活", c == 200)

print()
print("=" * 62)
print("七、旧接口 /api/dirs 应已下线")
print("=" * 62)
c, _, b = req("GET", "/api/dirs")
print("    GET /api/dirs -> %d %s" % (c, b[:100]))
check("/api/dirs 已下线", c == 404)

print()
print("=" * 62)
print("汇总：PASS=%d  FAIL=%d" % (len(PASS), len(FAIL)))
if FAIL:
    print("失败项：")
    for x in FAIL:
        print("  - " + x)
    sys.exit(1)
print("全部通过")
