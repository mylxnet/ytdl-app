"""YouTube 下载器 V3 — 本地网页应用后端

架构：Flask + yt-dlp 子进程 + SSE 进度推送。
V3 交互模型：粘贴链接 → 解析预览 → 倒计时自动下载（落 NAS 磁盘）
             → 列表逐行「预览 / 下载 / 删除」。
下载输出统一落在 DOWNLOAD_DIR（部署时挂载宿主机目录）。
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context
from werkzeug.utils import secure_filename

APP_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/downloads"))
COOKIES_FILE = Path(os.environ.get("COOKIES_FILE", "/config/cookies.txt"))
COOKIE_BACKUP = COOKIES_FILE.with_name(COOKIES_FILE.name + ".bak")
NODE_PATH = os.environ.get("NODE_PATH", "")
HISTORY_FILE = DOWNLOAD_DIR / ".history.json"

VERSION = "3.0.4"

# Cookie 上传限制：正常 cookies.txt 只有几 KB，1MB 足够且能挡住异常大文件
MAX_COOKIE_SIZE = 1024 * 1024
# YouTube 登录凭证关键字段（Netscape 格式，Tab 分隔第 7 列为 cookie 名）
AUTH_COOKIES = ("SID", "SAPISID", "__Secure-1PSID", "LOGIN_INFO")
COOKIE_VERIFY_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 代理配置：与 Cookie 同目录持久化，仅允许明确协议，避免任意参数进入命令行
PROXY_FILE = COOKIES_FILE.parent / "proxy.txt"
PROXY_PROTOCOLS = ("http", "https", "socks4", "socks5")
MAX_PROXY_SIZE = 4096

# 预览/播放支持的后缀
VIDEO_EXT = {".mp4", ".webm", ".m4v", ".ogv", ".mkv", ".avi", ".mov"}
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg"}
MEDIA_EXT = VIDEO_EXT | AUDIO_EXT

YOUTUBE_RE = re.compile(r"https?://(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com|music\.youtube\.com)/")

app = Flask(__name__, template_folder=str(APP_DIR.parent / "templates"))

# ---------------- 任务管理 ----------------

TASKS: dict[str, dict] = {}
_queue_lock = threading.Lock()
_queue: list[str] = []
_worker_thread: threading.Thread | None = None


def _load_history() -> list[dict]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_history(entries: list[dict]) -> None:
    try:
        HISTORY_FILE.write_text(json.dumps(entries[-200:], ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _yt_dlp_cmd() -> str:
    return os.environ.get("YTDLP_PATH", "yt-dlp")


# ---------------- 代理配置 ----------------

def _parse_proxy_url(value: str) -> str:
    """校验并规范化代理 URL，返回完整地址供 yt-dlp 使用。

    仅允许 http/https/socks4/socks5，要求合法主机与 1-65535 端口；
    拒绝控制字符、缺失主机、非法端口和其他协议。
    带认证的 URL（user:pass@host:port）保留认证字段，但任何对外展示
    都必须走 _mask_proxy_url()，不得把认证字段返回给前端或日志。
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("代理地址不能为空")
    if len(raw) > MAX_PROXY_SIZE:
        raise ValueError(f"代理地址过长（>{MAX_PROXY_SIZE} 字符）")
    if any(ord(c) < 32 for c in raw):
        raise ValueError("代理地址包含控制字符")
    parts = urlsplit(raw)
    scheme = (parts.scheme or "").lower()
    if scheme not in PROXY_PROTOCOLS:
        raise ValueError(f"仅支持 {'/'.join(PROXY_PROTOCOLS)} 代理，如 http://127.0.0.1:7890")
    if not parts.hostname:
        raise ValueError("代理缺少主机名")
    if parts.port is not None and not (1 <= parts.port <= 65535):
        raise ValueError("代理端口必须在 1-65535 之间")
    return raw


def _mask_proxy_url(value: str) -> str:
    """返回仅含协议、主机、端口的脱敏展示值，绝不包含用户名/密码。"""
    parts = urlsplit((value or "").strip())
    host = parts.hostname or ""
    if parts.port:
        return f"{parts.scheme}://{host}:{parts.port}"
    return f"{parts.scheme}://{host}"


def _read_proxy() -> str | None:
    """读取当前代理配置；文件不存在、损坏或超限时按未配置处理。"""
    try:
        text = PROXY_FILE.read_text(encoding="utf-8").strip()
        if len(text) > MAX_PROXY_SIZE:
            return None
        return _parse_proxy_url(text)
    except Exception:
        return None


def _write_proxy(value: str) -> str:
    """校验并持久化代理；临时文件 + 原子替换 + 0600 权限。"""
    url = _parse_proxy_url(value)
    PROXY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROXY_FILE.with_name(PROXY_FILE.name + ".tmp")
    tmp.write_text(url + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, PROXY_FILE)
    return url


def _clear_proxy() -> None:
    """删除代理配置文件；只删代理文件，不影响 Cookie 文件。"""
    try:
        PROXY_FILE.unlink()
    except FileNotFoundError:
        pass


def _test_proxy(value: str) -> tuple[bool, str]:
    """用候选代理实际访问一次 YouTube，验证连通性与认证；不写入配置。

    返回 (是否可用, 脱敏说明)。命令复用 _base_args()，但会先移除
    _base_args() 里已有的 --proxy（测试候选代理时不应受已保存代理干扰），
    再注入候选代理执行 yt-dlp --print 抓标题；超时 60 秒。
    """
    url = _parse_proxy_url(value)
    cmd = _base_args()
    try:
        i = cmd.index("--proxy")
        del cmd[i:i + 2]
    except ValueError:
        pass
    cmd += ["--proxy", url, "--print", "%(title)s", COOKIE_VERIFY_URL]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return False, "测试超时（60 秒内无响应），代理可能不可达"
    out = (r.stdout or "").strip()
    if r.returncode == 0 and out:
        return True, f"代理可用，成功获取视频标题：{out}"
    tail = (r.stderr or "").strip().splitlines()
    detail = tail[-1][:300] if tail else f"exit {r.returncode}"
    parts = urlsplit(url)
    if parts.username:
        detail = detail.replace(parts.username, "***")
    if parts.password:
        detail = detail.replace(parts.password, "***")
    detail = detail.replace(url, _mask_proxy_url(url))
    return False, f"代理不可用：{detail}"


def _base_args() -> list[str]:
    args = [_yt_dlp_cmd(), "--no-warnings", "--newline", "--no-color", "--windows-filenames"]
    proxy = _read_proxy()
    if proxy:
        args += ["--proxy", proxy]
    if COOKIES_FILE.exists():
        args += ["--cookies", str(COOKIES_FILE)]
    if NODE_PATH:
        args += ["--js-runtimes", f"node:{NODE_PATH}"]
    else:
        args += ["--js-runtimes", "node"]
    args += ["--remote-components", "ejs:github"]
    return args


def _probe(url: str) -> dict:
    """取标题/时长/封面，用于提交前确认。"""
    cmd = _base_args() + ["--dump-single-json", "--no-playlist", url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        tail = r.stderr.strip().splitlines()
        raise RuntimeError(tail[-1][:300] if tail else "probe failed")
    info = json.loads(r.stdout)
    return {
        "title": info.get("title") or url,
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("thumbnail") or "",
        "uploader": info.get("uploader") or "",
    }


# ---------------- Cookie 上传 ----------------

def _check_cookie_format(text: str) -> tuple[int, list[str]]:
    """校验 Netscape cookies.txt 格式，返回 (有效条目数, 命中的登录凭证)。

    Netscape 格式 7 列：域 | 含子域 | 路径 | 安全 | 过期时间 | **名称** | 值
    cookie 名是第 6 列，即 0-based 索引 5 —— 取错成 cols[6] 会读到值，
    导致正常 Cookie 被误判为「缺少登录凭证」（实测踩坑，已修）。
    """
    count = 0
    names: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("://"):
            continue
        cols = line.split("\t")
        if len(cols) < 7:
            continue
        count += 1
        names.add(cols[5])
    return count, [n for n in AUTH_COOKIES if n in names]


def _verify_cookie() -> tuple[bool, str]:
    """用一个真实视频验证当前 COOKIES_FILE 是否真的能绕过机器人验证。

    必须复用 _base_args() —— 那里带 --remote-components ejs:github。
    早期版本手写了参数列表、漏了 EJS 组件，导致验证器用的求解器比真实下载弱，
    正常 Cookie 也被判为失败（返回「The page needs to be reloaded」）。已修。
    """
    args = _base_args() + ["--print", "%(title)s", COOKIE_VERIFY_URL]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return False, "验证超时（YouTube 无响应）"
    out = (r.stdout or "").strip()
    if r.returncode == 0 and out:
        return True, out
    tail = (r.stderr or "").strip().splitlines()
    return False, (tail[-1][:200] if tail else f"exit {r.returncode}")


@app.post("/api/cookie/upload")
def api_cookie_upload():
    """上传 cookies.txt：格式校验 → 备份 → 覆盖 → 真实视频验证 → 失败回滚。

    无需重启容器：_base_args() 每次下载都重读 COOKIES_FILE，新任务自动用新 Cookie。
    """
    f = request.files.get("file")
    if not f:
        return jsonify(ok=False, error="未收到文件"), 400
    name = secure_filename(f.filename or "")
    if not name.lower().endswith(".txt"):
        return jsonify(ok=False, error="仅支持 Netscape 格式的 .txt（cookies.txt）"), 400

    data = f.stream.read(MAX_COOKIE_SIZE + 1)
    if len(data) > MAX_COOKIE_SIZE:
        return jsonify(ok=False, error=f"文件过大（>{MAX_COOKIE_SIZE // 1024}KB），已拒绝"), 400
    text = data.decode("utf-8", errors="replace")

    count, found = _check_cookie_format(text)
    if count < 10:
        return jsonify(ok=False, error=f"有效 Cookie 只有 {count} 条，文件疑似不完整"), 400
    if len(found) < 3:
        return (jsonify(ok=False, error=f"缺少登录凭证（仅找到：{', '.join(found) or '无'}）"
                                   f"，请确认浏览器已登录 youtube.com 再导出"), 400)

    had_backup = COOKIES_FILE.exists()
    if had_backup:
        shutil.copyfile(COOKIES_FILE, COOKIE_BACKUP)
    try:
        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_FILE.write_text(text, encoding="utf-8")
        os.chmod(COOKIES_FILE, 0o600)
        ok, msg = _verify_cookie()
        if not ok:
            if had_backup:
                shutil.copyfile(COOKIE_BACKUP, COOKIES_FILE)
            return (jsonify(ok=False, error=f"新 Cookie 验证失败，已回滚原文件。原因：{msg}"
                                       f"。建议在 Helium 里重新登录 youtube.com（退出再登录）后重新导出"), 400)
        return jsonify(ok=True, count=count, auths=found, title=msg)
    except Exception as e:  # noqa: BLE001
        if had_backup:
            try:
                shutil.copyfile(COOKIE_BACKUP, COOKIES_FILE)
            except Exception:
                pass
        return jsonify(ok=False, error=f"写入失败，已回滚：{e}"), 500


# ---------------- 代理设置 ----------------

@app.get("/api/proxy")
def api_proxy_get():
    """查询当前代理配置；只返回脱敏展示值，不返回密码或完整认证 URL。"""
    url = _read_proxy()
    return jsonify(ok=True, configured=bool(url), display=_mask_proxy_url(url) if url else "")


@app.post("/api/proxy")
def api_proxy_set():
    """保存代理配置；校验通过后持久化，立即作用于后续 yt-dlp 命令。"""
    data = request.json or {}
    value = data.get("proxy", "")
    try:
        url = _write_proxy(value)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400
    except OSError as e:
        return jsonify(ok=False, error=f"写入代理配置失败：{e}"), 500
    return jsonify(ok=True, configured=True, display=_mask_proxy_url(url))


@app.delete("/api/proxy")
def api_proxy_delete():
    """清除代理配置；不影响 Cookie 文件。"""
    try:
        _clear_proxy()
    except OSError as e:
        return jsonify(ok=False, error=f"清除代理配置失败：{e}"), 500
    return jsonify(ok=True, configured=False, display="")


@app.post("/api/proxy/test")
def api_proxy_test():
    """用候选代理实际访问一次 YouTube，验证连通性与认证；不写入配置。"""
    data = request.json or {}
    value = (data.get("proxy") or _read_proxy() or "").strip()
    if not value:
        return jsonify(ok=False, error="请先输入代理地址或保存代理后再测试"), 400
    try:
        ok, msg = _test_proxy(value)
        return jsonify(ok=ok, message=msg)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400
    except OSError as e:
        return jsonify(ok=False, error=f"测试失败：{e}"), 500


# ---------------- 文件安全解析 ----------------

def _secure_media(name: str) -> Path:
    """把用户提交的文件名解析为 DOWNLOAD_DIR 内的真实文件路径，否则抛 ValueError。

    注意：这里的 name 来自 yt-dlp 落盘文件名（可能含中文/括号/空格），
    不能跑 secure_filename —— 那会把非 ASCII 字符替换成下划线，导致
    「列表里是原名、请求里查不到」的错配（实测已踩坑）。
    防护改用白名单规则 + resolve() 前缀校验：
      1) 必须是非空、单层文件名
      2) 禁止路径分隔符 / \\ 与父目录引用 ..（彻底堵死 ../ 穿越）
      3) 禁止控制字符与空字节（防日志注入/参数污染）
      4) resolve() 后必须仍位于 DOWNLOAD_DIR 内
    """
    name = (name or "").strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError("非法文件名")
    if ".." in name or "\x00" in name or "\n" in name or "\r" in name:
        raise ValueError("非法文件名")
    root = DOWNLOAD_DIR.resolve()
    target = (root / name).resolve()
    if target != root and str(target).startswith(str(root)) and target.is_file() \
            and not target.name.startswith("."):
        return target
    raise ValueError("文件不存在或路径越界")


# ---------------- 下载任务 ----------------

def _quality_args(quality: str) -> list[str]:
    if quality == "audio":
        return ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    if quality == "2160":
        return ["-f", "bestvideo[height<=2160]+bestaudio/best"]
    if quality == "720":
        return ["-f", "bestvideo[height<=720]+bestaudio/best"]
    return ["-f", "bestvideo[height<=1080]+bestaudio/best"]


# 画质档位 → 文件名标记。画质必须写进文件名：模板若不带画质，同一视频换画质重下
# 会得到完全相同的目标文件名，yt-dlp 判定「已存在」直接跳过，表现为「换了画质却没下」。
_QUALITY_TAG = {"audio": "audio", "2160": "2160p", "720": "720p"}
_QUALITY_DEFAULT_TAG = "1080p"


def _out_template(quality: str) -> str:
    tag = _QUALITY_TAG.get(quality, _QUALITY_DEFAULT_TAG)
    return str(DOWNLOAD_DIR / f"%(title).120B [%(id)s][{tag}].%(ext)s")


# yt-dlp 判定目标文件已存在时会打印这句并直接返回 0（一个字节都没下），
# 必须识别出来如实上报，否则会被当成「下载完成」并虚增一条历史记录。
ALREADY_DL_RE = re.compile(r"has already been downloaded")


def _run_download(task_id: str) -> None:
    task = TASKS[task_id]
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out_tmpl = _out_template(task["quality"])
    cmd = (
        _base_args()
        + _quality_args(task["quality"])
        + ["--merge-output-format", "mp4", "--no-playlist", "-o", out_tmpl, task["url"]]
    )
    task.update(status="downloading", progress=0.0, speed="", eta="", log_tail=[])
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        task["proc"] = proc
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if ALREADY_DL_RE.search(line):
                task["skipped"] = True
            m = re.search(r"\[download\]\s+([\d.]+)%.+?at\s+([\d.]+\w+/s|Unknown B/s)"
                          r"(?:\s+ETA\s+([\d:]+|Unknown))?", line)
            if m:
                task["progress"] = min(float(m.group(1)), 100.0)
                task["speed"] = m.group(2)
                task["eta"] = m.group(3) or ""
            task.setdefault("log_tail", []).append(line)
            task["log_tail"] = task["log_tail"][-30:]
        proc.wait(timeout=3600)
        if proc.returncode == 0 and task.get("skipped"):
            task.update(status="skipped", progress=100.0)
        elif proc.returncode == 0:
            task.update(status="done", progress=100.0)
        else:
            tail = " / ".join(task.get("log_tail", [])[-2:])
            raise RuntimeError(tail or f"exit {proc.returncode}")
    except Exception as e:  # noqa: BLE001
        task.update(status="error", error=str(e)[:400])
    finally:
        task.pop("proc", None)
        if task["status"] == "done":
            entries = _load_history()
            entries.append({
                "id": task_id, "title": task["title"], "url": task["url"],
                "quality": task["quality"], "finished_at": int(time.time()),
            })
            _save_history(entries)


def _worker() -> None:
    while True:
        with _queue_lock:
            tid = _queue.pop(0) if _queue else None
        if tid is None:
            time.sleep(0.5)
            continue
        _run_download(tid)


def _ensure_worker() -> None:
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = threading.Thread(target=_worker, daemon=True)
        _worker_thread.start()


# ---------------- 路由 ----------------

@app.get("/")
def index():
    return render_template("index.html", version=VERSION)


@app.get("/api/version")
def api_version():
    return jsonify(ok=True, version=VERSION)


@app.post("/api/probe")
def api_probe():
    url = (request.json or {}).get("url", "").strip()
    if not YOUTUBE_RE.match(url):
        return jsonify(ok=False, error="不是有效的 YouTube 链接"), 400
    try:
        info = _probe(url)
        return jsonify(ok=True, **info)
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, error=str(e)), 500


@app.post("/api/download")
def api_download():
    data = request.json or {}
    url = data.get("url", "").strip()
    quality = data.get("quality", "1080")
    if not re.match(r"https?://", url):
        return jsonify(ok=False, error="无效链接"), 400
    tid = uuid.uuid4().hex[:12]
    TASKS[tid] = {
        "id": tid, "url": url, "quality": quality,
        "status": "queued", "progress": 0.0,
        "title": data.get("title") or url, "created_at": time.time(),
    }
    with _queue_lock:
        _queue.append(tid)
    _ensure_worker()
    return jsonify(ok=True, task_id=tid)


@app.get("/api/task/<tid>")
def api_task(tid: str):
    t = TASKS.get(tid)
    if not t:
        return jsonify(ok=False, error="no such task"), 404
    return jsonify(ok=True, **{k: t.get(k) for k in ("id", "status", "progress", "speed", "eta", "title", "error")})


@app.get("/api/stream/<tid>")
def api_stream(tid: str):
    def gen():
        last = None
        while True:
            t = TASKS.get(tid)
            if not t:
                yield "data: {\"status\": \"gone\"}\n\n"
                return
            snap = {k: t.get(k) for k in ("status", "progress", "speed", "eta", "error")}
            if snap != last:
                yield f"data: {json.dumps(snap)}\n\n"
                last = snap
            if snap["status"] in ("done", "error", "skipped"):
                return
            time.sleep(1)

    return Response(stream_with_context(gen()), mimetype="text/event-stream")


@app.get("/api/history")
def api_history():
    return jsonify(ok=True, items=_load_history()[-50:][::-1])


@app.get("/api/files")
def api_files():
    """列出 DOWNLOAD_DIR 根目录下的媒体文件（按修改时间倒序，最多 100 个）。"""
    items = []
    try:
        for p in sorted(DOWNLOAD_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if not (p.is_file() and not p.name.startswith(".") and p.suffix.lower() in MEDIA_EXT):
                continue
            st = p.stat()
            items.append({
                "name": p.name,
                "size": st.st_size,
                "mtime": int(st.st_mtime),
                "kind": "video" if p.suffix.lower() in VIDEO_EXT else "audio",
            })
            if len(items) >= 100:
                break
    except Exception:
        pass
    return jsonify(ok=True, root=str(DOWNLOAD_DIR), items=items)


@app.get("/api/preview")
def api_preview():
    """在线预览：Flask send_file 原生支持 HTTP Range，<video> 可拖动 seek。"""
    try:
        p = _secure_media(request.args.get("name", ""))
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 404
    return send_file(str(p), conditional=True)


@app.get("/api/download-file")
def api_download_file():
    """下载回本地：as_attachment 触发浏览器「另存为」，由用户选择本地目录。"""
    try:
        p = _secure_media(request.args.get("name", ""))
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 404
    return send_file(str(p), as_attachment=True, download_name=p.name, conditional=True)


@app.delete("/api/file")
def api_delete_file():
    try:
        p = _secure_media(request.args.get("name", ""))
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 404
    try:
        p.unlink()
    except OSError as e:
        return jsonify(ok=False, error=f"删除失败：{e}"), 500
    return jsonify(ok=True, name=p.name)


@app.post("/api/open-folder")
def api_open_folder():
    return jsonify(ok=True, path=str(DOWNLOAD_DIR))


if __name__ == "__main__":
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=8765, threaded=True)
