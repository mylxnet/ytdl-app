#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代理设置功能测试：URL 校验 / API 路由 / _base_args() 注入。

使用临时目录替换 app.main.PROXY_FILE，避免触碰真实 /config 与 Cookie 文件。
在仓库根目录（E:\\work\\ytdl-app）运行：
    python test/test_proxy.py
"""
import importlib
import json
import pathlib
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.main as m  # noqa: E402  (在设置 sys.path 后导入)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (("  -> " + str(detail)) if detail else ""))


def proxy_set(value):
    body = json.dumps({"proxy": value}).encode()
    req = urllib.request.Request("http://localhost:8765/api/proxy", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    return _send(req)


def _send(req):
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        # 不抛异常，交由调用方判定。服务不可达必须记为失败项，不能被吞成「跳过」
        return 0, "服务不可达：%s" % e


def main():
    # 临时目录替换 PROXY_FILE；结束时恢复原值
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="ytdl_proxy_test_"))
    original = m.PROXY_FILE
    m.PROXY_FILE = tmp / "proxy.txt"

    print("=" * 62)
    print("一、_parse_proxy_url 校验")
    print("=" * 62)
    valid = [
        "http://127.0.0.1:7890",
        "https://proxy.example.com:8443",
        "socks5://127.0.0.1:1080",
        "socks4://127.0.0.1:1080",
        "http://user:pass@127.0.0.1:7890",
    ]
    for v in valid:
        try:
            out = m._parse_proxy_url(v)
            check("合法代理 %r" % v, out == v, out)
        except ValueError as e:
            check("合法代理 %r" % v, False, str(e))
    invalid = [
        ("ftp://127.0.0.1:21", "非法协议"),
        ("http://", "缺失主机"),
        ("http://127.0.0.1:99999", "非法端口"),
        ("http://127.0.0.1:0", "端口为 0"),
        ("http://127.0.0.1:78\t90", "控制字符"),
        ("", "空字符串"),
    ]
    for v, label in invalid:
        try:
            m._parse_proxy_url(v)
            check("非法代理 %s 应拒绝" % label, False, v)
        except ValueError:
            check("非法代理 %s 应拒绝" % label, True)

    print()
    print("=" * 62)
    print("二、_mask_proxy_url 脱敏")
    print("=" * 62)
    masked = m._mask_proxy_url("http://user:secret@127.0.0.1:7890")
    check("脱敏不含用户名密码", "secret" not in masked and "user" not in masked, masked)
    check("脱敏保留协议主机端口", masked == "http://127.0.0.1:7890", masked)

    print()
    print("=" * 62)
    print("三、代理配置文件读写")
    print("=" * 62)
    check("初始未配置", m._read_proxy() is None)
    m._write_proxy("http://127.0.0.1:7890")
    check("写入后读取", m._read_proxy() == "http://127.0.0.1:7890", m._read_proxy())
    check("配置脱敏", m._mask_proxy_url(m._read_proxy()) == "http://127.0.0.1:7890")
    m._clear_proxy()
    check("清除后未配置", m._read_proxy() is None)

    print()
    print("=" * 62)
    print("四、_base_args() 注入")
    print("=" * 62)
    m._clear_proxy()
    no_proxy = m._base_args()
    check("无代理不含 --proxy", "--proxy" not in no_proxy, no_proxy)
    m._write_proxy("http://127.0.0.1:7890")
    with_proxy = m._base_args()
    check("有代理含 --proxy", "--proxy" in with_proxy, with_proxy)
    check("有代理仅一个 --proxy", with_proxy.count("--proxy") == 1, with_proxy)
    idx = with_proxy.index("--proxy")
    check("--proxy 值为配置地址", with_proxy[idx + 1] == "http://127.0.0.1:7890", with_proxy[idx + 1])

    print()
    print("=" * 62)
    print("五、_test_proxy 单元测试（打桩，不真跑网络）")
    print("=" * 62)
    orig_run = m.subprocess.run
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["kw"] = kw
        if "badproxy" in " ".join(cmd):
            class R:
                returncode = 1
                stdout = ""
                stderr = "ERROR: unable to connect to proxy  http://user:pass@127.0.0.1:7890"
            return R()
        class R:
            returncode = 0
            stdout = "Rick Astley - Never Gonna Give You Up\n"
            stderr = ""
        return R()

    m.subprocess.run = fake_run
    try:
        ok, msg = m._test_proxy("http://user:pass@127.0.0.1:7890")
        check("_test_proxy 成功返回标题", ok and "Never Gonna" in msg, msg)
        check("_test_proxy 注入候选代理", " ".join(captured["cmd"]).count("--proxy") >= 1,
              captured["cmd"])
        ok2, msg2 = m._test_proxy("http://user:pass@badproxy:7890")
        check("_test_proxy 失败不泄露密码", (not ok2) and "pass" not in msg2 and "user" not in msg2,
              msg2)
    finally:
        m.subprocess.run = orig_run

    print()
    print("=" * 62)
    print("六、HTTP 路由（服务必须在线；不可达即判 FAIL，不允许跳过）")
    print("=" * 62)
    st, body = _send(urllib.request.Request("http://localhost:8765/api/proxy"))
    if st == 0:
        # 曾经这里用 try/except 吞掉异常只打印「服务未在线，跳过」，
        # 结果代理路由 404 被掩盖成 24 项全通过。服务不可达必须记为失败项。
        check("GET /api/proxy（服务须在线）", False, body)
    else:
        try:
            j = json.loads(body)
        except ValueError:
            j = {}
        check("GET /api/proxy 结构", st == 200 and "configured" in j and "display" in j, (st, body[:120]))

    print()
    print("=" * 62)
    print("汇总：PASS=%d  FAIL=%d" % (len(PASS), len(FAIL)))
    m.PROXY_FILE = original
    if FAIL:
        print("失败项：")
        for x in FAIL:
            print("  - " + x)
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()