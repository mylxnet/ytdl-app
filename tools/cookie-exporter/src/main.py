"""YouTube Cookie 导出器 —— 桌面界面（Tkinter）。

界面约定（用户明确要求，勿改）
------------------------------
- 浅色清爽，按钮统一白底灰边，不用红色按钮；
- 日志区实时刷新，长耗时操作期间显示滚动进度条；
- 未选保存位置就点导出 → 在**校验阶段**拦截并给出修正建议，不等到执行时报错；
- 不使用会位移的弹窗动画，所有提示统一走状态栏与日志；
- 保存位置每次启动都留空，绝不记忆上次路径；
- 浏览器正在运行只提示、不代用户关闭；
- 任务进行中禁用「浏览」「开始导出」，并拦截窗口关闭，避免中途打断。
"""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import tempfile
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, ttk

import browsers
import exporter

VERSION = "1.0.0"
AUTHOR = "by Mr lin"
APP_TITLE = "YouTube Cookie 导出器"

# ---- 配色（浅色主题）----
BG = "#f4f5f7"
CARD = "#ffffff"
BORDER = "#c9ced6"
TEXT = "#1f2328"
MUTED = "#6b7280"
OK_COLOR = "#1a7f37"
WARN_COLOR = "#9a6700"
ERR_COLOR = "#a4262c"
FONT = "Microsoft YaHei UI"

_MUTEX_NAME = "Local\\YtCookieExporter_SingleInstance"
_mutex_handle = None  # 保持句柄引用，避免被回收后互斥体失效


def _icon_path() -> Path | None:
    """定位图标：打包后取 _MEIPASS，源码运行取 ../assets。"""
    if getattr(sys, "_MEIPASS", None):
        path = Path(sys._MEIPASS) / "assets" / "icon.ico"
    else:
        path = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    return path if path.is_file() else None


def _ensure_single_instance() -> bool:
    """同一应用只允许一个实例；已有实例则把它的窗口唤到前台并返回 False。"""
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    _mutex_handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if kernel32.GetLastError() != 183:  # 183 = ERROR_ALREADY_EXISTS
        return True
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, APP_TITLE)
    if hwnd:
        user32.ShowWindow(hwnd, 9)        # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    return False


def _install_crash_log() -> None:
    """--windowed 打包后没有控制台，未捕获异常会无声退出；这里落一份日志便于排查。"""
    def hook(exc_type, exc, tb):  # noqa: ANN001
        try:
            (Path(tempfile.gettempdir()) / "YtCookieExporter-error.log").write_text(
                "".join(traceback.format_exception(exc_type, exc, tb)), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    sys.excepthook = hook


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.profiles: list[browsers.Profile] = []
        self.running: list[tuple[str, str]] = []
        self.busy = False
        self.out_path = ""          # 每次启动都为空，不记忆上次路径
        # 子线程与界面之间只通过队列通信（见 _pump 的说明）
        self._events: queue.Queue[tuple] = queue.Queue()
        self._closing = False

        self._build_ui()
        self.root.after(50, self._refresh_browsers)
        self.root.after(80, self._pump)

    # ---------------- 界面搭建 ----------------

    def _build_ui(self) -> None:
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        icon = _icon_path()
        if icon:
            try:
                self.root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass

        width, height = 780, 610
        x = (self.root.winfo_screenwidth() - width) // 2
        y = max((self.root.winfo_screenheight() - height) // 3, 0)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=(FONT, 9))
        style.configure("TCombobox", fieldbackground=CARD, background=CARD,
                        foreground=TEXT, arrowcolor=MUTED, borderwidth=1)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)])
        style.configure("TProgressbar", background="#8a8f98", troughcolor="#e4e6ea",
                        borderwidth=0)

        pad = 18
        # ---- 标题区 ----
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=pad, pady=(16, 8))
        tk.Label(head, text=APP_TITLE, bg=BG, fg=TEXT,
                 font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(head, text="从浏览器导出 YouTube 登录 Cookie，供下载器使用。"
                            "全程本地处理，除一次只读验证外不发任何网络请求。",
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w", pady=(4, 0))

        card = tk.Frame(self.root, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=pad, pady=(0, 10))

        body = tk.Frame(card, bg=CARD)
        body.pack(fill="both", expand=True, padx=14, pady=14)

        # ---- 浏览器配置 ----
        tk.Label(body, text="浏览器配置", bg=CARD, fg=TEXT,
                 font=(FONT, 9)).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.combo = ttk.Combobox(body, state="readonly", font=(FONT, 9), width=52)
        self.combo.grid(row=1, column=0, sticky="we", pady=(0, 4))
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self._on_profile_change())
        self.refresh_btn = self._button(body, "重新检测", self._refresh_browsers)
        self.refresh_btn.grid(row=1, column=1, sticky="e", padx=(8, 0), pady=(0, 4))

        # ---- 保存位置 ----
        tk.Label(body, text="保存位置", bg=CARD, fg=TEXT,
                 font=(FONT, 9)).grid(row=2, column=0, sticky="w", pady=(10, 4))
        self.path_var = tk.StringVar(value="")
        self.path_entry = tk.Entry(body, textvariable=self.path_var, font=(FONT, 9),
                                   bg="#fbfbfc", fg=TEXT, relief="solid", bd=1,
                                   highlightthickness=0, state="readonly",
                                   readonlybackground="#fbfbfc")
        self.path_entry.grid(row=3, column=0, sticky="we", pady=(0, 4), ipady=4)
        self.browse_btn = self._button(body, "浏览…", self._pick_path)
        self.browse_btn.grid(row=3, column=1, sticky="e", padx=(8, 0), pady=(0, 4))

        body.columnconfigure(0, weight=1)

        # ---- 操作按钮 ----
        actions = tk.Frame(body, bg=CARD)
        actions.grid(row=4, column=0, columnspan=2, sticky="we", pady=(10, 4))
        self.export_btn = self._button(actions, "开始导出", self._start_export, primary=True)
        self.export_btn.pack(side="left")
        self.open_btn = self._button(actions, "打开所在文件夹", self._open_folder)
        self.open_btn.pack(side="left", padx=(8, 0))
        self.open_btn.configure(state="disabled")
        self.clear_btn = self._button(actions, "清空日志", self._clear_log)
        self.clear_btn.pack(side="right")

        # ---- 进度条（空闲时隐藏：一条空槽看起来像多余的分隔线）----
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.grid(row=5, column=0, columnspan=2, sticky="we", pady=(6, 0))
        self.progress.grid_remove()

        # ---- 日志 ----
        tk.Label(body, text="运行日志", bg=CARD, fg=TEXT,
                 font=(FONT, 9)).grid(row=6, column=0, sticky="w", pady=(12, 4))
        log_wrap = tk.Frame(body, bg=BORDER, highlightthickness=0)
        log_wrap.grid(row=7, column=0, columnspan=2, sticky="nsew")
        body.rowconfigure(7, weight=1)
        self.log_text = tk.Text(log_wrap, height=11, font=(FONT, 9), bg="#fbfbfc",
                                fg=TEXT, relief="flat", bd=0, wrap="word",
                                padx=10, pady=8, state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        scroll = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y", pady=1, padx=(0, 1))
        self.log_text.configure(yscrollcommand=scroll.set)

        # ---- 底部状态栏 ----
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=pad, pady=(0, 12))
        self.status_label = tk.Label(footer, text="就绪", bg=BG, fg=MUTED,
                                     font=(FONT, 9), anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        tk.Label(footer, text=f"V{VERSION}  {AUTHOR}", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="right")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _button(self, parent, text: str, command, primary: bool = False) -> tk.Button:
        """统一的白底灰边按钮；主按钮仅加粗，不使用任何彩色底。"""
        return tk.Button(
            parent, text=text, command=command,
            bg=CARD, fg=TEXT, activebackground="#eceef1", activeforeground=TEXT,
            font=(FONT, 9, "bold" if primary else "normal"),
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground="#a9aeb8" if primary else BORDER,
            highlightcolor="#a9aeb8" if primary else BORDER,
            padx=14, pady=5, cursor="hand2", disabledforeground="#a9aeb8",
        )

    # ---------------- 日志与状态 ----------------

    def _append_log(self, msg: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log(self, msg: str) -> None:
        """线程安全：子线程只把消息塞进队列，绝不直接碰任何 Tk 对象。

        早期写法是在子线程里调 ``root.after(0, ...)``，实测会炸出
        ``RuntimeError: main thread is not in main loop`` —— 该调用依赖主线程
        此刻正好在事件循环内部，并不可靠。改成队列 + 主线程轮询后彻底规避。
        """
        self._events.put(("log", msg))

    def _pump(self) -> None:
        """主线程定时消费事件队列 —— 所有界面操作都留在主线程执行。"""
        if self._closing:
            return
        try:
            while True:
                event = self._events.get_nowait()
                if event[0] == "log":
                    self._append_log(event[1])
                elif event[0] == "done":
                    self._finish(event[1], event[2])
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _set_status(self, text: str, color: str = MUTED) -> None:
        self.status_label.configure(text=text, fg=color)

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ---------------- 浏览器检测 ----------------

    def _refresh_browsers(self) -> None:
        if self.busy:
            return
        self._set_status("正在检测本机浏览器…")
        self.root.update_idletasks()
        try:
            self.profiles = browsers.scan_profiles()
            self.running = browsers.detect_running()
        except Exception as exc:  # noqa: BLE001
            self.profiles, self.running = [], []
            self._append_log(f"检测浏览器失败：{exc}")

        names = [p.display for p in self.profiles]
        self.combo["values"] = names
        if not names:
            self.combo.set("")
            self.export_btn.configure(state="disabled")
            self._append_log("未检测到任何可用的浏览器配置。"
                             "请先在浏览器里登录 youtube.com，再点「重新检测」。")
            self._set_status("未检测到可用的浏览器配置", WARN_COLOR)
            return

        self.combo.current(0)
        self.export_btn.configure(state="normal")
        self._on_profile_change()
        self._append_log(f"检测到 {len(names)} 个浏览器配置："
                         + "、".join(names))

    def _current_profile(self) -> browsers.Profile | None:
        idx = self.combo.current()
        if 0 <= idx < len(self.profiles):
            return self.profiles[idx]
        return None

    def _on_profile_change(self) -> None:
        profile = self._current_profile()
        if profile is None:
            return
        self._append_log(f"已选择：{profile.display}")
        if browsers.is_locked(profile, self.running):
            self._append_log(f"提示：{profile.browser_name} 正在运行，它的 Cookie 数据库会被独占。"
                             "本工具不会替你关闭浏览器；若导出失败，请手动完全退出后重试。")
            self._set_status(f"{profile.browser_name} 正在运行，导出失败时请先关闭它", WARN_COLOR)
        else:
            self._set_status("就绪，选择保存位置后即可导出")

    # ---------------- 交互 ----------------

    def _pick_path(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择 cookies.txt 的保存位置",
            defaultextension=".txt",
            initialfile="cookies.txt",
            filetypes=[("Cookie 文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not path:
            return          # 用户取消：保持原样，不残留半截路径
        self.path_var.set(path)
        self.out_path = path
        self.open_btn.configure(state="normal")
        self._set_status("已选择保存位置，可以开始导出")
        self._append_log(f"保存位置：{path}")

    def _open_folder(self) -> None:
        target = Path(self.out_path).parent if self.out_path else Path.home()
        if target.is_dir():
            os.startfile(target)  # noqa: S606 —— Windows 桌面工具的标准做法

    def _validate(self) -> bool:
        """提交前校验：不合规的输入在这里就拦下，并给出明确的修正建议。"""
        profile = self._current_profile()
        if profile is None:
            self._append_log("请先选择「浏览器配置」—— 列表为空时点「重新检测」。")
            self._set_status("尚未选择浏览器配置", WARN_COLOR)
            self.combo.focus_set()
            return False
        if not self.out_path.strip():
            self._append_log("请先选择保存位置：点右侧「浏览…」按钮，"
                             "指定 cookies.txt 要保存到哪里（例如桌面）。")
            self._set_status("尚未选择保存位置，请在「浏览…」里指定", WARN_COLOR)
            self.browse_btn.focus_set()
            return False
        if not Path(self.out_path).parent.is_dir():
            self._append_log(f"保存目录不存在：{Path(self.out_path).parent}，请重新选择。")
            self._set_status("保存目录不存在，请重新选择", ERR_COLOR)
            self.path_var.set("")
            self.out_path = ""
            self.browse_btn.focus_set()
            return False
        return True

    def _start_export(self) -> None:
        if self.busy or not self._validate():
            return
        profile = self._current_profile()
        assert profile is not None
        out_path = Path(self.out_path)

        self.busy = True
        self.export_btn.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        self.refresh_btn.configure(state="disabled")
        self.combo.configure(state="disabled")
        self.progress.grid()
        self.progress.start(80)
        self._set_status("正在导出…")
        self._append_log("")
        self._append_log("=" * 52)
        self._append_log(f"开始导出（工具版本 V{VERSION}）")

        threading.Thread(target=self._worker, args=(profile, out_path), daemon=True).start()

    def _worker(self, profile: browsers.Profile, out_path: Path) -> None:
        try:
            result = exporter.export_and_verify(profile, out_path, self._log)
        except Exception as exc:  # noqa: BLE001
            self._events.put(("done", None, f"导出过程中发生未预期的错误：{exc}"))
            return
        self._events.put(("done", result, ""))

    def _finish(self, result: exporter.ExportResult | None, fatal: str) -> None:
        self.progress.stop()
        self.progress.grid_remove()
        self.busy = False
        self.export_btn.configure(state="normal")
        self.browse_btn.configure(state="normal")
        self.refresh_btn.configure(state="normal")
        self.combo.configure(state="readonly")

        if fatal:
            self._append_log(fatal)
            self._set_status("导出失败", ERR_COLOR)
            return
        assert result is not None

        for hint in result.hints:
            self._append_log(f"建议：{hint}")

        if not result.ok:
            self._append_log(f"导出失败：{result.error}")
            self._set_status("导出失败，请按日志中的建议处理", ERR_COLOR)
            return

        if result.verified:
            self._append_log(f"导出完成：{result.count} 条 Cookie，登录状态已验证。")
            self._set_status(f"导出成功（{result.count} 条，已验证）", OK_COLOR)
        else:
            self._append_log(f"导出完成：{result.count} 条 Cookie，但未能验证登录状态。")
            self._set_status(f"已导出（{result.count} 条，未验证）", WARN_COLOR)
        self._append_log("注意：该文件包含 YouTube 登录凭证，等同于账号密码，请勿外发。")

    def _on_close(self) -> None:
        """导出进行中拦截关闭，避免中途打断留下半成品。"""
        if self.busy:
            self._set_status("正在导出，请等待完成后再关闭", WARN_COLOR)
            self._append_log("任务进行中，已忽略关闭操作。")
            return
        self._closing = True     # 停掉轮询，否则销毁后 after 回调会报错
        self.root.destroy()


def main() -> int:
    if not _ensure_single_instance():
        return 0
    _install_crash_log()
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())