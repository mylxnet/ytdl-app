"""Cookie 导出与登录态验证。

流程
----
yt-dlp 从浏览器 profile 读 Cookie → 先落临时文件 → 格式与登录凭证校验
→ HTTP 只读验证登录态 → **全部通过后**才写入用户选定路径。

为什么先落临时文件：验证不通过的文件对用户毫无价值，直接落盘只会让用户
「以为成功」而误用。所以任何一步失败都不留文件。

隐私边界
--------
1. 只在本地读浏览器数据，除一次只读 GET 之外不发任何网络请求，更不上传 Cookie。
2. 浏览器 Cookie 库里混着淘宝、抖音、飞书等上百个站点的登录凭证，
   全量落盘等于把整台机器的账号都交出去。所以导出后**只保留
   youtube.com / google.com 两个域**，其余一律丢弃（实测 710 条中只留 58 条，
   下载器所需的 4 项登录凭证全部在内）。
"""

from __future__ import annotations

import http.client
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from yt_dlp import YoutubeDL

import browsers

LogFn = Callable[[str], None]

# YouTube 登录凭证关键字段（Netscape 格式，第 7 列 = cookie 名）
AUTH_COOKIES = ("SID", "SAPISID", "__Secure-1PSID", "LOGIN_INFO")
# 只保留这两个域的 Cookie：YouTube 下载所需凭证全在内，其余站点一律丢弃
KEEP_DOMAINS = ("youtube.com", "google.com")
MIN_COOKIES = 10   # 正常的登录态 Cookie 数量远大于此
MIN_AUTH = 3       # 4 项凭证中至少命中 3 项
VERIFY_HOST = "www.youtube.com"
VERIFY_PATH = "/account"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
# 验证请求的重试：YouTube 偶发直接断开连接（实测过一次
# "Remote end closed connection without response"，紧接着连测三次都正常）
VERIFY_ATTEMPTS = 3
VERIFY_RETRY_WAIT = 1.5

# 失败原因关键字 → 可操作指引。yt-dlp 的原始报错对普通用户没有意义。
_ABE_MARKS = ("failed to decrypt", "dpapi", "app-bound", "app_bound", "could not decrypt")
_LOCK_MARKS = ("could not copy chrome cookie database", "being used by another process",
               "database is locked", "permission denied", "unable to open database")


@dataclass
class ExportResult:
    ok: bool = False
    verified: bool | None = None   # True 已验证 / False 明确无效 / None 网络原因未能验证
    count: int = 0
    auth: list[str] = field(default_factory=list)
    note: str = ""
    error: str = ""
    hints: list[str] = field(default_factory=list)


class _YtdlpLogger:
    """把 yt-dlp 的告警/错误转成界面日志；info/debug 过于啰嗦，丢弃。"""

    def __init__(self, log: LogFn) -> None:
        self._log = log

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        self._log(f"  [警告] {msg}")

    def error(self, msg: str) -> None:
        self._log(f"  [错误] {msg}")


def _iter_netscape(path: Path) -> Iterator[tuple[str, str, str]]:
    """解析 Netscape cookies.txt，逐行产出 ``(域, 名称, 值)``。

    两个必须注意的格式细节（都是踩过的坑）：
    1. cookie 名在**第 6 列**（0-based 索引 5）。写成 ``cols[6]`` 取到的是值，
       会把完全正常的文件判成「缺少登录凭证」。
    2. HttpOnly 的 Cookie 行带 ``#HttpOnly_`` 前缀，必须剥掉前缀再解析，
       不能当注释整行跳过 —— 否则会漏掉 ``__Secure-1PSID`` 这类关键凭证。
    """
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 7:
            continue
        yield cols[0], cols[5], cols[6]


def _inspect(path: Path) -> tuple[int, list[str]]:
    """统计有效条目数，并列出命中的登录凭证。"""
    count = 0
    names: set[str] = set()
    for _domain, name, _value in _iter_netscape(path):
        count += 1
        names.add(name)
    return count, [n for n in AUTH_COOKIES if n in names]


def _cookie_header(path: Path) -> str:
    """拼出请求 youtube.com 时该带的 Cookie 头（只取 youtube 域的 Cookie）。"""
    return "; ".join(f"{name}={value}"
                     for domain, name, value in _iter_netscape(path)
                     if "youtube.com" in domain)


def _short(exc: Exception, limit: int = 300) -> str:
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    return text[:limit]


def _export_hints(msg: str) -> list[str]:
    """把底层报错翻译成用户能照做的指引。"""
    low = msg.lower()
    hints: list[str] = []
    if any(mark in low for mark in _ABE_MARKS):
        hints.append("Chrome / Edge 的新版本启用了 App-Bound Encryption，外部工具无法解密其 Cookie。"
                     "请改用 Firefox 或 Brave 登录 youtube.com 后再导出。")
        hints.append("或右键选择「以管理员身份运行」本工具后重试。")
    if any(mark in low for mark in _LOCK_MARKS):
        hints.append("浏览器运行时会独占 Cookie 数据库。请完整退出该浏览器"
                     "（含托盘常驻进程与后台扩展）后重试。")
    if not hints:
        hints.append("请确认所选浏览器已安装并登录过 youtube.com，"
                     "且当前 Windows 账号有权读取它的配置目录。")
    return hints


def _filter_domains(path: Path) -> tuple[int, int]:
    """只保留 KEEP_DOMAINS 里的域，返回 ``(保留条数, 丢弃条数)``。

    就地重写文件，行序与注释头保持不变，便于人工查看时与标准格式一致。
    """
    out_lines: list[str] = []
    kept = dropped = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        # 注释行与空行原样保留（表头、yt-dlp 说明行）
        if not stripped or (stripped.startswith("#") and not stripped.startswith("#HttpOnly_")):
            out_lines.append(raw)
            continue
        body = stripped[len("#HttpOnly_"):] if stripped.startswith("#HttpOnly_") else stripped
        cols = body.split("\t")
        if len(cols) >= 7 and any(domain in cols[0] for domain in KEEP_DOMAINS):
            out_lines.append(raw)
            kept += 1
        else:
            dropped += 1
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return kept, dropped


def _dump(profile: browsers.Profile, out_file: Path, log: LogFn) -> None:
    """调用 yt-dlp 把 profile 里的 Cookie 写成 Netscape 格式的 cookies.txt。"""
    opts = {
        "cookiesfrombrowser": profile.ytdlp_arg,
        "cookiefile": str(out_file),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _YtdlpLogger(log),
    }
    with YoutubeDL(opts) as ydl:
        ydl.save_cookies()


def _request_account(cookie_header: str) -> tuple[int, str]:
    """发一次不跟随重定向的 GET，返回 ``(状态码, Location 头)``。"""
    conn = http.client.HTTPSConnection(VERIFY_HOST, timeout=30)
    try:
        conn.request("GET", VERIFY_PATH, headers={
            "Cookie": cookie_header,
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        resp = conn.getresponse()
        status = resp.status
        location = resp.getheader("Location") or ""
        resp.read()
        return status, location
    finally:
        conn.close()


def _verify(cookie_header: str, log: LogFn) -> tuple[bool | None, str]:
    """只读验证登录态，返回 ``(结果, 说明)``。

    结果分三态：``True`` 已登录 / ``False`` 明确未登录 / ``None`` 未能验证。

    必须区分后两者。早期实现把所有失败都当成「Cookie 无效」，结果一次
    偶发的 ``Remote end closed connection without response`` 就提示用户
    「请退出账号重新登录」—— 用户白折腾一轮，问题其实只是网络抖了一下。
    因此这里先重试，重试仍失败才报「未能验证」。

    判定依据：``/account`` 未登录时会 302 跳到 accounts.google.com，已登录返回 200。
    早先试过的 ``/feed/subscriptions`` 不可用 —— 未登录时它也返回 200，判不出来。
    """
    if not cookie_header:
        return False, "导出的文件里没有任何 youtube.com 域的 Cookie"

    last_error = ""
    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        try:
            status, location = _request_account(cookie_header)
        except Exception as exc:  # noqa: BLE001 —— 网络异常在此统一处理
            last_error = _short(exc)
            if attempt < VERIFY_ATTEMPTS:
                log(f"  第 {attempt} 次验证失败（{last_error}），{VERIFY_RETRY_WAIT:g} 秒后重试…")
                time.sleep(VERIFY_RETRY_WAIT)
                continue
            return None, f"网络请求连续 {VERIFY_ATTEMPTS} 次失败：{last_error}"

        if status == 200:
            return True, "HTTP 200：账号页可直接访问，登录状态有效"
        if 300 <= status < 400 and "accounts.google.com" in location:
            return False, "被重定向到 Google 登录页，说明这份 Cookie 没有登录态"
        return False, f"意外的响应：HTTP {status} {location[:120]}".strip()

    return None, f"网络请求失败：{last_error}"


def export_and_verify(profile: browsers.Profile, out_path: Path, log: LogFn) -> ExportResult:
    """完整流程：导出 → 只留 youtube/google 域 → 格式校验 → 登录态验证 → 落盘。

    ``ok=True`` 表示文件已成功写入用户选定的路径；``verified`` 表示登录态验证结果
    （``None`` 代表因网络原因未能验证，此时文件仍会写入，但不算「已验证」）。
    """
    result = ExportResult()
    tmp_dir = Path(tempfile.mkdtemp(prefix="ytck-"))
    tmp_file = tmp_dir / "cookies.txt"
    try:
        log(f"浏览器配置：{profile.display}")
        log(f"配置路径：{profile.profile_path}")
        log("正在读取浏览器 Cookie 数据库…")
        try:
            _dump(profile, tmp_file, log)
        except Exception as exc:  # noqa: BLE001
            msg = _short(exc)
            result.error = f"读取浏览器 Cookie 失败：{msg}"
            result.hints = _export_hints(msg)
            return result

        if not tmp_file.is_file():
            result.error = "导出流程结束，但没有生成 Cookie 文件"
            result.hints = ["请确认所选浏览器确实已登录 youtube.com 后再试。"]
            return result

        kept, dropped = _filter_domains(tmp_file)
        log(f"已丢弃 {dropped} 条其他站点的 Cookie，只保留 {kept} 条 "
            f"（{' / '.join(KEEP_DOMAINS)}）")

        count, auth = _inspect(tmp_file)
        result.count, result.auth = count, auth
        log(f"已读取 {count} 条 Cookie，命中登录凭证：{', '.join(auth) or '无'}")

        if count < MIN_COOKIES:
            result.error = f"只读到 {count} 条 youtube.com / google.com 域的 Cookie，过少"
            result.hints = ["请先用该浏览器打开 youtube.com 并登录账号，再重新导出。",
                            "也可以换一个已登录 YouTube 的浏览器（如 Firefox / Brave）重试。"]
            return result

        if len(auth) < MIN_AUTH:
            result.error = f"缺少 YouTube 登录凭证（仅找到：{', '.join(auth) or '无'}）"
            result.hints = ["请先用该浏览器打开 youtube.com 登录账号，再重新导出。"]
            return result

        log("正在验证登录状态（只读访问 youtube.com/account，不上传任何数据）…")
        verified, note = _verify(_cookie_header(tmp_file), log)
        result.verified = verified
        result.note = note
        log(f"验证结果：{note}")
        if verified is False:
            result.error = f"登录态验证未通过：{note}"
            result.hints = ["若浏览器里确实已登录，请退出 YouTube 账号后重新登录一次，再导出。",
                            "请确认系统日期时间准确 —— 偏差过大会导致 Cookie 被判失效。"]
            return result
        if verified is None:
            # 网络问题不等于 Cookie 无效：文件照常交付，但必须如实标注「未验证」
            result.hints = ["本机当前无法访问 youtube.com，没能验证登录状态。",
                            "文件已导出，可上传到下载器，由下载器再做一次校验（失败会自动回滚）。"]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmp_file, out_path)
        result.ok = True
        log(f"已写入文件：{out_path}")
        return result
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)