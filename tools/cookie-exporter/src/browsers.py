"""浏览器与 profile 扫描。

设计要点
--------
1. yt-dlp 的 ``cookiesfrombrowser`` 只认固定的浏览器标识
   （brave / chrome / chromium / edge / firefox / opera / safari / vivaldi / whale）。
   Helium 这类基于 Chromium 的第三方浏览器**不在**该列表内，必须显式传
   profile 绝对路径，browser key 传 ``chrome`` 即可正常解密 —— 已实测导出 713 条。
2. 因此本模块统一输出「可直接喂给 yt-dlp 的 profile 绝对路径」，
   上层无需再关心浏览器之间的差异。
3. 判定一个子目录是不是可用 profile，标准是「里面真的有 Cookie 库」：
   - Chromium 系：``<profile>/Network/Cookies``
   - Firefox：``<profile>/cookies.sqlite``
   只看目录名（Default / Profile 1）会把空 profile 也选进来。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# 打包成 --windowed exe 后，调用外部命令不能再闪黑框
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_LOCAL = Path(os.environ.get("LOCALAPPDATA") or r"C:\__missing_localappdata__")
_ROAM = Path(os.environ.get("APPDATA") or r"C:\__missing_appdata__")

# Chromium 里不需要展示的 profile 目录
_SKIP_PROFILE_DIRS = {"system profile", "guest profile"}


@dataclass(frozen=True)
class _BrowserDef:
    key: str        # yt-dlp cookiesfrombrowser 的浏览器标识
    name: str       # 界面展示名
    root: Path      # Chromium 系为 User Data 根目录；Firefox 为 Firefox 配置根
    exe_name: str   # 进程名（小写，含 .exe）
    exe_hint: str   # 进程 exe 路径关键字（小写），用于区分同名的 chrome.exe
    kind: str       # "chromium" | "firefox"


# 顺序即界面下拉框的展示顺序；Helium 排在最前（本项目主力浏览器）
_BROWSERS: tuple[_BrowserDef, ...] = (
    _BrowserDef("chrome", "Helium", _LOCAL / "imput" / "Helium" / "User Data",
                "chrome.exe", "\\helium", "chromium"),
    _BrowserDef("chrome", "Google Chrome", _LOCAL / "Google" / "Chrome" / "User Data",
                "chrome.exe", "\\google\\chrome", "chromium"),
    _BrowserDef("edge", "Microsoft Edge", _LOCAL / "Microsoft" / "Edge" / "User Data",
                "msedge.exe", "\\microsoft\\edge", "chromium"),
    _BrowserDef("brave", "Brave", _LOCAL / "BraveSoftware" / "Brave-Browser" / "User Data",
                "brave.exe", "\\bravesoftware", "chromium"),
    _BrowserDef("vivaldi", "Vivaldi", _LOCAL / "Vivaldi" / "User Data",
                "vivaldi.exe", "\\vivaldi", "chromium"),
    _BrowserDef("chromium", "Chromium", _LOCAL / "Chromium" / "User Data",
                "chromium.exe", "\\chromium", "chromium"),
    _BrowserDef("opera", "Opera", _ROAM / "Opera Software" / "Opera Stable",
                "opera.exe", "\\opera", "chromium"),
    _BrowserDef("firefox", "Firefox", _ROAM / "Mozilla" / "Firefox",
                "firefox.exe", "\\firefox", "firefox"),
)


@dataclass(frozen=True)
class Profile:
    """一个可直接交给 yt-dlp 使用的浏览器 profile。"""

    browser_key: str    # cookiesfrombrowser 第 1 个参数
    browser_name: str   # 界面展示名
    profile_path: str   # cookiesfrombrowser 第 2 个参数（绝对路径）
    label: str          # profile 名（Default / Profile 1 / 随机名）
    exe_name: str       # 浏览器进程名，用于判断 Cookie 库是否被占用
    exe_hint: str       # 进程路径关键字

    @property
    def display(self) -> str:
        return f"{self.browser_name} · {self.label}"

    @property
    def ytdlp_arg(self) -> tuple[str, str, None, None]:
        """拼成 yt-dlp 的 ``cookiesfrombrowser`` 元组。"""
        return (self.browser_key, self.profile_path, None, None)


def _chromium_profiles(defn: _BrowserDef) -> list[Path]:
    """列出 Chromium 系浏览器下真正含有 Cookie 库的 profile 目录。"""
    found: list[Path] = []
    if not defn.root.is_dir():
        return found
    try:
        children = sorted(defn.root.iterdir())
    except OSError:
        return found
    for child in children:
        if not child.is_dir() or child.name.lower() in _SKIP_PROFILE_DIRS:
            continue
        if (child / "Network" / "Cookies").is_file():
            found.append(child)
    # Opera 的布局不同：Opera Stable 目录本身就是 profile，Cookie 库直接在其下
    if not found and (defn.root / "Network" / "Cookies").is_file():
        found.append(defn.root)
    return found


def _firefox_profiles(defn: _BrowserDef) -> list[Path]:
    """列出 Firefox 下含有 cookies.sqlite 的 profile 目录。"""
    profiles_dir = defn.root / "Profiles"
    found: list[Path] = []
    if not profiles_dir.is_dir():
        return found
    try:
        children = sorted(profiles_dir.iterdir())
    except OSError:
        return found
    for child in children:
        if child.is_dir() and (child / "cookies.sqlite").is_file():
            found.append(child)
    return found


def _make_profile(defn: _BrowserDef, path: Path) -> Profile:
    label = "默认" if path == defn.root else path.name
    return Profile(
        browser_key=defn.key,
        browser_name=defn.name,
        profile_path=str(path),
        label=label,
        exe_name=defn.exe_name,
        exe_hint=defn.exe_hint,
    )


def scan_profiles() -> list[Profile]:
    """扫描本机全部可用 profile；未安装或没有 Cookie 库的浏览器会被跳过。"""
    profiles: list[Profile] = []
    for defn in _BROWSERS:
        if not defn.root.is_dir():
            continue
        paths = _firefox_profiles(defn) if defn.kind == "firefox" else _chromium_profiles(defn)
        profiles.extend(_make_profile(defn, p) for p in paths)
    return profiles


def detect_running() -> list[tuple[str, str]]:
    """返回当前正在运行的浏览器进程 ``[(进程名, exe 路径), ...]``（均为小写）。

    Cookie 数据库在浏览器运行时会被独占锁定，读取会失败；
    界面需要在导出前据此给出「请先关闭浏览器」的提示。
    只查候选浏览器的进程名，避免遍历整张进程表。
    """
    if os.name != "nt":
        return []
    names = ",".join(sorted({d.exe_name[:-4] for d in _BROWSERS}))
    script = (
        f"Get-Process -Name {names} -ErrorAction SilentlyContinue | "
        'ForEach-Object { "$($_.ProcessName)|$($_.Path)" }'
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=20, creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    rows: set[tuple[str, str]] = set()
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        name, sep, path = line.partition("|")
        if sep:
            rows.add((name.strip().lower(), path.strip().lower()))
    # 同一浏览器的多个子进程会输出大量重复行，去重后便于日志展示
    return sorted(rows)


def is_locked(profile: Profile, running: list[tuple[str, str]]) -> bool:
    """判断该 profile 所属浏览器是否在运行（即 Cookie 库是否被占用）。

    进程路径读不到时按进程名宽松匹配 —— 宁可多提示一次，
    也不要漏报导致导出直接失败。
    """
    want = profile.exe_name[:-4].lower()
    for name, path in running:
        if name != want:
            continue
        if not path or not profile.exe_hint:
            return True
        if profile.exe_hint in path:
            return True
    return False


def profile_from_path(raw: str) -> Profile:
    """手动指定目录时的兜底解析；无法识别 Cookie 库则抛 ValueError。"""
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise ValueError("目录不存在")

    kind = ""
    if (path / "Network" / "Cookies").is_file():
        kind = "chromium"
    elif (path / "cookies.sqlite").is_file():
        kind = "firefox"
    else:
        raise ValueError("该目录下没有找到 Cookie 库（Network\\Cookies 或 cookies.sqlite）")

    # 尽量归到已知浏览器，好让「浏览器是否在运行」的提示依然准确
    for defn in _BROWSERS:
        if defn.kind != kind:
            continue
        try:
            path.relative_to(defn.root)
        except ValueError:
            continue
        return _make_profile(defn, path)

    return Profile(
        browser_key="firefox" if kind == "firefox" else "chrome",
        browser_name="自定义路径",
        profile_path=str(path),
        label=path.name or str(path),
        exe_name="firefox.exe" if kind == "firefox" else "chrome.exe",
        exe_hint="",
    )