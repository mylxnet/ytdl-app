# 项目状态 / 交接文档

> 项目：YouTube 下载器（ytdl-app）
> 当前版本：**V3.0.3**（2026-09-24）
> 署名：by Mr lin

---

## 一、当前版本

| 项 | 值 |
|---|---|
| 版本号 | 3.0.3 |
| 代码位置 | `e:\work\ytdl-app` |
| 镜像 | `ytdl-app:latest`（WSL `lxsyzd` 内） |
| 访问地址 | http://localhost:8765 |
| 下载目录 | `/mnt/e/Downloads/YouTube` |
| Cookie 位置 | `./config/cookies.txt` |
| 桌面工具版本 | 1.0.0（`tools/cookie-exporter`，独立版本号，见 2.4） |

**版本号三处一致性校验**：
- 后端 `app/main.py` 第 28 行 `VERSION = "3.0.3"`
- 页面 footer `V3.0.3 · by Mr lin`（实测页面 HTML：`<footer>V3.0.3  ·  by Mr lin</footer>`）
- 本文档 / README.md / DESIGN.md / DEPLOY.md 均标注 V3.0.3

---

## 二、已完成功能（V3.0.3）

### 2.1 V3 本轮重构
| 功能 | 实现位置 | 验证方式 |
|---|---|---|
| 倒计时 3 秒自动下载（可取消） | `templates/index.html` 前端 | 浏览器实测 |
| 删除「开始下载」按钮 | `templates/index.html` | 截图确认 |
| 删除子目录选择 / 新建 | `app/main.py` 移除 `_check_subdir` 等 | `/api/dirs` 返回 404 |
| 页内预览（HTTP Range seek） | `GET /api/preview` → `send_file(conditional=True)` | `Range: bytes=0-1023` 返回 206 + `Content-Range: bytes 0-1023/33824493` |
| 下载回本机（另存为） | `GET /api/download-file` → `as_attachment=True` | 返回 `Content-Disposition: attachment; filename=...` |
| Cookie 热上传 | `POST /api/cookie-upload` | 真实上传成功，HTTP 200，57 条 Cookie，4 凭证全命中 |
| 中文文件名 RFC 5987 | Flask `send_file(download_name=...)` 自动编码 | 响应头含 `filename*=UTF-8''%E9%80%9F...` |

### 2.2 端到端验证结果（V3.0.0）

**真实下载验证**（测试视频：Rick Astley - Never Gonna Give You Up，dQw4w9WgXcQ，213s）：
```
probe     -> {"ok":true,"title":"Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)","duration":213}
download  -> task_id: 29e7482177d8
task      -> status: done, progress: 100%, speed: 8.38MiB/s
file      -> 32.26 MB
download  -> HTTP 200, Content-Disposition: attachment, Content-Length: 33824493
range     -> HTTP 206, Content-Range: bytes 0-1023/33824493
delete    -> {"ok":true,"name":"Rick Astley - ..."}
```

**回归测试**（`test_v3.py`，22 项全通过）：
- 路径穿越 7 种注入全拦截（`..`、`../`、`%2e%2e`、`\..`、控制字符、空字符串、超长）
- `/api/version` 返回 3.0.0
- `/api/files` 含 name/size/mtime/kind
- `/api/preview` 支持 HTTP Range（206 + Content-Range）
- `/api/download-file` Content-Disposition 含 `filename*=UTF-8''`
- DELETE 拦截路径穿越
- Cookie 上传 5 种失败路径：无文件 / 空文件 / 非 .txt / 格式不符 / 凭证不全
- 服务存活检查
- `/api/dirs` 已下线（返回 404）

**浏览器截图验收**：
- 初始页面干净（无倒计时卡片、无遮罩）
- 预览弹窗可打开，`display:flex`，`video.readyState=4`，`paused=false`（正在播放）
- 文件列表 4 行，预览 / 下载 / 删除按钮齐备

### 2.3 V3.0.1 修复（特殊字符文件名下载失败）

**现象**：NAS 上该视频下载报错，同目录其他普通文件名均正常——
`ERROR: unable to open for writing: [Errno 2] No such file or directory: '/downloads/Deep Conscious Dub 🔊 Heavy Bass Reggae ｜ ... [MTwRIug5LlU].f399.mp4.part'`

**排查过程**：容器内 `ls -la /downloads` 确认目录存在、属主 `1000:1001`、同目录已有 64MB 文件写入成功 → 排除挂载失败与权限问题，锁定为文件名本身

**根因**：标题含 emoji `🔊` 与全角竖线 `｜`（U+FF5C），yt-dlp 默认输出模板 `%(title)s.%(ext)s` 未做跨平台字符清理，导致临时分片文件路径解析异常

**修复**：`_base_args()` 新增「跨平台文件名清理」参数——但代码里写作 `--windowsfilenames`（⚠️ **拼写错误**，yt-dlp 的正确选项名是 `--windows-filenames`），直接导致 V3.0.1 不可用，已在 2.5 修正

**验证状态**：**未做任何端到端验证即发版**（本轮按原决策跳过了本地实测，仅改代码与文档）。事后证明这是 V3.0.1 完全不可用的直接原因，见 2.5 与踩坑 #15

### 2.4 桌面工具：Cookie 导出器（`tools/cookie-exporter`，独立版本 V1.0.0）

**为什么有它**：主服务「网页热上传 Cookie」需要先有 `cookies.txt`。原流程要装浏览器插件手动导出，来源杂、格式不统一。本工具把它做成本机双击即用的小程序：选浏览器 → 选保存位置 → 点导出。

| 项 | 值 |
|---|---|
| 版本 | **V1.0.0**（2026-09-24），界面署名 `V1.0.0  by Mr lin` |
| 交付物 | `YtCookieExporter.exe`，单文件 **19,648,087 字节（18.7 MB）**；已作为 Release 附件发布：[tool-v1.0.0](https://github.com/mylxnet/ytdl-app/releases/download/tool-v1.0.0/YtCookieExporter.exe) |
| 运行前提 | Windows x64，**目标机器无需安装 Python**（Python 3.12 + yt-dlp 已打进 exe） |
| 源码 | `src/main.py`（Tkinter 界面）、`src/exporter.py`（导出 + 校验 + 验证）、`src/browsers.py`（浏览器/profile 扫描） |
| 打包素材 | `build/build.ps1`（长期保留，**必须带 UTF-8 BOM**，见踩坑 #11） |
| 构建环境 | `.venv`：Python 3.12.10 + yt-dlp 2026.8.19 + PyInstaller 6.22.3 |
| SHA256 | `5E8149CECF0D6E5F8B3DE5045D52ED8C2890291E963A941E37EDCCFF25C8C736` |

**用户硬性要求（勿打折）**：双击即用、目标机免装 Python；保存位置每次启动留空；只导出不上传；浏览器运行中只提示不代关；单文件 exe + ASCII 文件名；浅色界面、白/灰按钮（禁用红色与 danger）；实时日志真刷新；未选路径点导出必须提前拦截；无弹窗位移动画；防重复启动；导出中禁用破坏性入口。

**已裁决的隐私边界**：导出结果**只保留 `youtube.com` / `google.com` 两个域**（实测 710 条 → 58 条），其余站点凭证一律丢弃——浏览器 Cookie 库里混着上百个站点的登录态，全量落盘等于交出整机账号。

**实测验证记录（2026-09-24）**：
```
exe 启动   -> 窗口 1.9 秒出现，下拉框/按钮/进度条/署名/图标正常
真实导出   -> 58 条 Cookie、4 项凭证全命中（SID、SAPISID、__Secure-1PSID、LOGIN_INFO）
登录态验证 -> GET https://www.youtube.com/account 返回 HTTP 200（未登录会 302 → accounts.google.com）
落盘位置   -> F:\UserFiles\DeskTop\cookies.txt（用户手动选择）
产物       -> 单文件 exe，19,648,087 字节
```

**发布（2026-09-24）**：源码随仓库入库；exe 作为 **Release 附件**发布（不入 git 仓库，避免 18.7 MB 二进制反复堆进版本历史）。
```
tag        -> tool-v1.0.0（注解 tag，独立于主服务 v3.0.x 版本线），指向 main
Release    -> https://github.com/mylxnet/ytdl-app/releases/tag/tool-v1.0.0
附件       -> YtCookieExporter.exe（19,648,087 字节，ASCII 文件名）
下载回验   -> 下载后 SHA256 = 5E8149CE…C736，与本地构建产物完全一致
```

### 2.5 V3.0.2 紧急修复（V3.0.1 参数名拼写错误导致服务不可用）

**现象**：网页端解析报 `⚠ yt-dlp: error: no such option: --windowsfilenames`，任何链接都无法解析。

**根因**：`_base_args()`（[main.py](file:///e:/ytdl-app/app/main.py#L71-L80)）把 yt-dlp 的选项名写成了 `--windowsfilenames`，**正确名称是 `--windows-filenames`**（带连字符）。yt-dlp 遇到不认识的选项立即报错退出。

**影响面**：`_base_args()` 是 probe / download / Cookie 验证三处共用的参数构建函数，因此**解析、下载、Cookie 热上传全部失效**——不只是解析。

**修复**：选项名更正为 `--windows-filenames`（[main.py](file:///e:/ytdl-app/app/main.py#L72)），版本号升至 **3.0.2**（六处同步：后端 `VERSION` / 页面 footer / README / DESIGN / PROJECT_STATE / DEPLOY）。

**实测证据（2026-09-24，容器重建后）**：
```
version     -> {"ok":true,"version":"3.0.2"}
页面 footer  -> <footer>V3.0.2  ·  by Mr lin</footer>
probe 普通   -> {"duration":213,"title":"Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)","uploader":"Rick Astley"}
probe 特殊   -> {"duration":294,"title":"Deep Conscious Dub 🔊 Heavy Bass Reggae ｜ Roots Meditation, Positive Energy & Deep Bass Vibes"}
download    -> task 19e4493bd4ba：status done、progress 100%、speed 2.08MiB/s
file        -> Deep Conscious Dub 🔊 Heavy Bass Reggae ｜ ... [MTwRIug5LlU].mp3（9,143,012 字节），无 .part 写入错误
容器选项自检 -> yt-dlp --help 中 --windows-filenames 命中 1 处
```

**NAS 场景归档（2026-09-24 决定不再跟进）**：`--windows-filenames` 只清理 Windows **非法**字符（`\ / : * ? " < > |`，均为半角）；emoji `🔊` 与全角 `｜`（U+FF5C）不属于非法字符，实测文件名中原样保留。原计划在 NAS 上跑 `MTwRIug5LlU` 复验「.part 写入失败」是否真被解决（本地 WSL 的 NTFS 挂载 9p 无法复现该场景），**该复验已决定不再单独执行**，按现状归档。

**验证状态**：本机端到端已通过 ✅；NAS 场景不再单独实测（已归档）。

### 2.6 V3.0.3 修复（进度不回传 + 画质重名）

**现象**：解析成功、3 秒倒计时结束后，页面上的下载任务**没有任何动静**（进度条始终 0%、无实时速度）；但视频其实已经下载落盘到 NAS，刷新页面后文件正常出现在列表里。

**根因**：任务状态是**进程内内存变量**，而 gunicorn 以 `-w 2` 起了两个独立 worker 进程，两份 `TASKS` 互不可见。

- `POST /api/download` 落在 worker A → 任务建在 A、后台线程也在 A 跑，**下载本身是成功的**
- `GET /api/stream/<tid>`（SSE）是另一个独立请求，可能被分给 worker B → B 的 `TASKS` 里没有该 tid → `api_stream` 立即返回 `{"status":"gone"}` → 前端落到 `else` 分支显示「任务已结束」并 `es.close()`，**进度永远停在 0%**

**实测复现（修复前）**：创建任务后连查 20 次 `/api/task/<tid>`，**5 次返回 404**（25% 落在另一个 worker）。

**修复**（[Dockerfile](file:///e:/ytdl-app/Dockerfile#L25-L28)）：

```
-w 2 -b 0.0.0.0:8765
→ -w 1 -k gthread --threads 8 -b 0.0.0.0:8765
```

单进程保证状态唯一；`gthread` 线程池保证 SSE 只占一个线程、不再独占整个 worker（sync worker 下一条 SSE 会占满一只 worker 直到任务结束）。业务代码 [main.py](file:///e:/ytdl-app/app/main.py) 未改动。

**顺带修复的两个重名问题**：

1. **换画质重下被静默跳过**：输出模板 `%(title).120B [%(id)s].%(ext)s` 不含画质，同一视频同 id 必然同名 → yt-dlp 判「已存在」直接跳过（exit 0），改选 4K 也下不来。现模板改为 `%(title).120B [%(id)s][{画质}].%(ext)s`，标记取 `[1080p]` / `[2160p]` / `[720p]` / `[audio]`
2. **跳过时误报「下载完成」**：yt-dlp 跳过时打印 `has already been downloaded` 并以 0 退出，后端原样记成 `done` + 100% 并**再追加一条历史**。现识别该输出行（`ALREADY_DL_RE`），如实上报 `skipped`，前端提示「⏭ 该画质已存在，未重复下载」；`/api/stream` 终止条件同步补 `skipped`，历史不再虚增

**实测证据（2026-09-24，容器重建后）**：
```
docker top   -> 仅 1 个 worker 进程（修复前为 2 个）
gunicorn log -> Using worker: gthread
version      -> {"ok":true,"version":"3.0.3"}
页面 footer  -> <footer>V3.0.3  ·  by Mr lin</footer>
原 bug 反证  -> 连查同一任务状态 20 次，全部命中 20/20（修复前 15/20）
SSE 实时流   -> 0.0s queued / 1.0s downloading 0% / 6.0s downloading 100% 4.15MiB/s / 9.0s done，流正常结束
换画质实下   -> 720p status done，落盘 …[dQw4w9WgXcQ][720p].mp4（20.03 MB）
同画质重下   -> status skipped，历史记录保持 7 条不变（不虚增）
容器代码核对 -> --windows-filenames / _out_template / ALREADY_DL_RE / skipped 均在镜像内，V3.0.2 修复未回归
```

**说明（升级注意）**：文件名规则变更后，旧格式 `标题 [id].mp4` 与新格式 `标题 [id][1080p].mp4` 不一致，升级后首次重下同一视频会真正重新下载一份；旧文件仍在列表中，预览 / 下载 / 删除均不受影响。

---

## 三、踩坑记录

### #1 `secure_filename` 导致中文文件名 404 错配
- **现象**：上传中文标题文件后，`/api/download-file?name=中文名` 返回 404
- **根因**：早期用 Werkzeug `secure_filename()` 处理文件名，会剥离中文
- **修复**：改用白名单规则（禁 `/` `\` `..` 与控制字符）+ `resolve()` 前缀校验
- **教训**：中文文件名的安全校验要自己写，不能依赖通用工具

### #2 原 `刷新Cookie.ps1` 先覆盖后备份导致回滚失效
- **现象**：上传失败后回滚逻辑无效，cookies.txt 已是损坏状态
- **根因**：脚本顺序错误，应该先备份再覆盖
- **修复**：V3 的 `/api/cookie-upload` 严格遵循「先备份 → 再覆盖 → 失败回滚」顺序
- **教训**：涉及数据替换的操作，备份必须在覆盖之前

### #3 `_check_cookie_format` 用 `cols[6]` 取到值而非 cookie 名
- **现象**：上传一份完全正常的 cookies.txt，被判「缺少登录凭证」而拒绝
- **根因**：Netscape cookies.txt 是 7 列格式：`域 | 含子域 | 路径 | 安全 | 过期时间 | **名称** | 值`。cookie 名在**第 6 列**，0-based 索引是 **5**。代码写成 `cols[6]` 取到的是**值**
- **修复**：改为 `cols[5]`，docstring 明确记录列号
- **教训**：列格式必须看官方规范，不能凭印象数。诊断脚本也要同步修正，否则会误判

### #4 `_verify_cookie` 漏 `--remote-components ejs:github`
- **现象**：上传正常 Cookie 返回 HTTP 400「The page needs to be reloaded」
- **根因**：`_verify_cookie()` 手写了参数列表，漏了 `--remote-components ejs:github`，导致验证器使用的 EJS 求解器比真实下载流程弱，撞墙返回此错误，把正常 Cookie 误判为失败
- **修复**：改为 `args = _base_args() + ["--print", "%(title)s", COOKIE_VERIFY_URL]`，复用统一参数构建函数
- **教训**：验证环境与真实执行环境必须一致，不能各写一份参数。抽公共函数是根本解

### #5 `.hidden` 被 `.countdown` / `.modal` 的 `display:flex` 覆盖
- **现象**：初始页面就显示倒计时卡片（"3 即将自动开始下载"），且有一块半透明黑色遮罩挡住了「上传 Cookie」和「用法说明」卡片
- **根因**：CSS 选择器优先级问题。`.hidden`（第 40 行，`display:none`）与 `.countdown`（第 51 行）、`.modal`（第 59 行）的 `display:flex` 同为单类选择器，优先级都是 (0,1,0)，**后声明者胜出**，`display:flex` 压掉了 `display:none`
- **修复**：`.hidden { display:none !important; }`
- **教训**：「靠声明顺序赌赢」的写法很脆。语义为「强制隐藏」的工具类，用 `!important` 锁死是更明确的选择

### #6 buildx provenance 导致 ACR 推送失败
- **现象**：`docker push registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.0` 报 `error from registry: unknown manifest class for application/vnd.oci.empty.v1+json`
- **根因**：Docker Compose / buildx 默认开启 provenance + attestation，产物 manifest list 附带 `application/vnd.oci.empty.v1+json` 类型的 attestation 元数据，阿里云 ACR 不识别该 manifest class
- **无效方案**：`docker save ytdl-app:latest -o tar && docker load -i tar` 重打包。tar 内保留完整 OCI 元数据，push 依然报同一错误。镜像 ID 不变（`f27cc96bdc24`），说明 attestation 就是原产物的一部分
- **修复**：`docker buildx build --no-cache --provenance=false --platform linux/amd64 -t ytdl-app:latest .` 禁用 provenance 重新构建。产物变单 manifest，push 成功
- **教训**：所有面向阿里云 ACR 的构建必须显式加 `--provenance=false`，并固化到发布脚本；不要依赖 `docker compose build` 默认行为

### #7 全角竖线 `｜` 等特殊字符导致 `.part` 文件写入失败
- **现象**：NAS 下载标题含 `🔊`、全角竖线 `｜` 的视频，报 `ERROR: unable to open for writing: [Errno 2] No such file or directory: '/downloads/xxx.f399.mp4.part'`；同目录普通文件名下载正常
- **排查**：容器内 `ls -la /downloads` 显示目录存在、属主 `1000:1001`、且已有 64MB 文件写入成功 → 排除挂载与权限问题，锁定文件名本身
- **根因**：yt-dlp 默认输出模板 `%(title)s.%(ext)s` 未做跨平台字符清理，全角竖线 `｜`（U+FF5C）等字符使临时分片文件路径解析异常
- **修复**：`_base_args()` 参数列表新增文件名清理参数（⚠️ 当时写作 `--windowsfilenames`，**拼写错误**，见踩坑 #15；V3.0.2 已更正为 `--windows-filenames`）
- **教训**：面向 NAS / 跨平台部署的下载器必须显式声明文件名清理策略，不能假设目标文件系统能接受任意字符

### #8 子线程直接操作 Tkinter 控件导致崩溃（桌面工具）
- **现象**：导出任务在工作线程里调 `root.after(...)` 回传日志，界面随机崩溃或日志不刷新
- **根因**：Tkinter 不是线程安全的，只有创建控件的主线程才能碰控件；从子线程调度同样不安全
- **修复**：工作线程只往 `queue.Queue` 里塞消息，主线程用 `root.after(100, poll)` 定时轮询队列再更新界面
- **教训**：GUI 框架的线程模型必须先查清楚。跨线程一律走队列，不要图省事直接回调

### #9 网络抖动被误判成 Cookie 失效（桌面工具）
- **现象**：Cookie 明明可用，验证却报失败，用户被引导去反复重刷 Cookie
- **根因**：验证只看 HTTP 状态，且没区分「业务上明确无效」与「网络原因没验成功」；YouTube 偶发直接断开（实测一次 `Remote end closed connection without response`，紧接着连测三次均正常）
- **修复**：验证改**三态**（有效 / 明确无效 / 网络原因未验证），并对验证请求重试 3 次（间隔 1.5s）
- **教训**：验证器必须区分「确认失败」和「没能确认」，否则会给出误导性的操作指引

### #10 全量导出 Cookie 等于交出整机账号（桌面工具）
- **现象**：首次导出得到 710 条 Cookie，涉及 192 个站点——淘宝、抖音、飞书等登录凭证全在文件里
- **根因**：`yt-dlp --cookies` 导出的是浏览器 Cookie 库的全部内容，不做站点过滤
- **修复**：导出后按域过滤，**只保留 `youtube.com` / `google.com`**（710 → 58 条），下载器所需的 4 项登录凭证全部在内
- **教训**：凭据类文件必须按「最小必要」裁剪。用户只想要下载器的登录态，不该顺手把整机账号打包带走

### #11 PowerShell 5.1 按 GBK 读脚本，UTF-8 无 BOM 的中文注释解析报错（桌面工具）
- **现象**：`build.ps1` 用 UTF-8 无 BOM 保存后执行报错，提示中文注释处出现意外的字符
- **根因**：Windows PowerShell 5.1 对无 BOM 的脚本按系统 ANSI 代码页（中文环境为 GBK）解码，UTF-8 的中文注释被解成乱码字节，脚本解析失败
- **修复**：`build.ps1` **必须带 UTF-8 BOM** 保存
- **教训**：面向 Windows PowerShell 5.1 的脚本含非 ASCII 字符时，BOM 不是可选项

### #12 PyInstaller 默认把 `.spec` 写到当前工作目录，污染仓库根目录（桌面工具）
- **现象**：打包后发现仓库根目录多了 `YtCookieExporter.spec`
- **根因**：PyInstaller 默认以当前工作目录为 spec 输出位置，与 `--workpath` / `--distpath` 无关
- **修复**：`build.ps1` 显式加 `--specpath build`，把 spec 固定到 build 目录内
- **教训**：工具链的输出路径要逐个显式指定，默认值往往落在最不希望的位置

### #13 单文件 exe 运行时会分裂成父子两个进程（桌面工具）
- **现象**：脚本按进程名找窗口，抓到的是没有窗口的父进程，取窗口句柄始终为空
- **根因**：PyInstaller 单文件模式下，父进程负责解压与启动，真正的界面跑在子进程里
- **修复**：枚举进程后按 `MainWindowHandle -ne 0` 过滤，才能定位到持有窗口的那个进程
- **教训**：单文件打包的运行模型与源码运行不同，自动化取证脚本要按实际模型写

### #14 截图取证要靠 PrintWindow，不能靠 SetForegroundWindow + CopyFromScreen（桌面工具）
- **现象**：截图抓到一片空白，或抓不到目标窗口
- **根因**：`SetForegroundWindow` 常被系统限制而失效；`CopyFromScreen` 抓的是屏幕像素，窗口未置顶或正处于重绘瞬间就会得到空白
- **修复**：用 `PrintWindow(hwnd, hdc, 2)`（`PW_RENDERFULLCONTENT`）直接让窗口把自己画到目标 DC，不依赖窗口是否在前台
- **教训**：窗口取证不要依赖系统前台策略，直接从窗口自身渲染结果取图

### #15 yt-dlp 参数名拼写错误 + 未做端到端验证就发版，导致整条链路失效（最高优先级教训）
- **现象**：网页端任何链接解析都报 `⚠ yt-dlp: error: no such option: --windowsfilenames`；V3.0.1 镜像已推 ACR，**线上完全不可用**
- **根因**：两层错误叠加
  ① **选项名写错**：yt-dlp 的正确写法是 `--windows-filenames`（带连字符），代码写成 `--windowsfilenames`，yt-dlp 遇到未知选项立即报错退出
  ② **发版前未验证**：只改了代码与文档，**一次真实解析/下载都没跑**，错误因此逃过所有检查
- **影响面**：`_base_args()` 被 probe / download / Cookie 热上传三处共用，**三处全部失效**——一处拼写错误等于整个服务停摆
- **修复**：更正为 `--windows-filenames`，升版 V3.0.2；容器重建后实测 version / probe（普通 + 特殊字符标题）/ 真实下载 MP3 全部通过
- **教训**：
  1. **外部命令行工具的选项名必须核实**（`--help` 或官方文档），不能凭印象拼写。带连字符的长选项尤其容易写错
  2. **涉及外部命令调用的改动，发版前必须跑一次真实调用**。「只改代码不验证」等于把风险直接推给线上，本次代价是整版不可用
  3. **公共参数构建函数的影响面是全量的**，改 `_base_args()` 这类函数要优先验证，它是所有链路的必经之路
  4. 验证时机比验证方式更重要——本机一次 curl 就能拦住的问题，拖到了线上才发现

---

### #16 gunicorn 多 worker 导致进程内任务状态分裂（进度不回传）
- **现象**：解析成功、倒计时结束后，页面下载任务「没有动静」——进度条停在 0%、无实时速度；但文件其实已下载到 NAS，刷新页面后正常出现在列表
- **根因**：`TASKS` / `_queue` / `_worker_thread` 都是**进程内内存变量**，而 gunicorn 以 `-w 2` 起了两个独立 worker。`POST /api/download` 与 `GET /api/stream/<tid>` 是两次独立请求，若分别落到不同 worker，SSE 那个 worker 查不到任务，立刻返回 `{"status":"gone"}`，前端显示「任务已结束」并关闭连接 → 进度永远不动
- **定位方式**：创建任务后连查 20 次 `/api/task/<tid>`，**5 次 404**；`docker top` 确认容器内有 2 个 worker，日志 `Using worker: sync`
- **修复**：Dockerfile 改为 `-w 1 -k gthread --threads 8`。单进程保证状态唯一；gthread 线程池顺带解决「sync worker 被一条 SSE 独占直到任务结束」的问题
- **教训**：
  1. **多进程部署下，进程内状态必须当成「不可靠」**：任何 `dict` / 全局变量 / 队列只要靠内存，就无法跨 worker 共享。要么单进程，要么外置（Redis / SQLite / 文件）
  2. **同步 worker + SSE 长连接是天然冲突**：一条 SSE 就占满一只 sync worker，`-w 2` 时下载期间一半处理能力被吃掉。长连接场景要用线程 / 协程 worker
  3. **「下载成功了但界面没反应」优先怀疑状态回传链路，而不是下载本身**——文件落盘与状态回传是两条独立路径，可以一条通、一条不通
  4. **负载均衡下的间歇性故障要靠统计取证**：单次请求可能碰巧命中，只有连续多次请求的命中率才能把问题钉死

---

## 四、架构决策

| 决策 | 理由 |
|---|---|
| **V3：删子目录，改单层平铺** | NAS 共享给本机浏览时，深层目录增加「另存为」操作成本。文件名含 `[视频ID]` 已足够可辨识 |
| **V3：页内 Range 预览** | 浏览器原生 `<video>` + Flask `send_file(conditional=True)` 免费获得 seek 能力，无需额外转码 |
| **V3：Cookie 热上传** | 原「导出→拷文件→重启容器」链路太长，且重启会打断进行中任务。改成网页上传，上传即校验即生效 |
| **V3：倒计时 3 秒自动下载** | 减少一次点击，倒计时给「后悔窗口」可点取消 |
| **gunicorn 2 worker** | 保持 V2 配置未改。**已知限制**：跨 worker 不共享 TASKS 字典，理论上两个 worker 各跑一个下载任务，违背串行设计。V4 改为 1 worker + 内部线程队列 |
| **JSON 存历史** | 数据量小（≤200 条），免维护 |
| **子进程调 yt-dlp** | 独立进程隔离崩溃；超时可直接 kill；版本升级独立 |

---

## 五、已知限制

| 限制 | 影响 | 计划 |
|---|---|---|
| **容器重启丢进行中任务** | TASKS 在内存 | 可接受（单人使用） |
| **无鉴权** | 局域网可见，公网部署=裸奔 | V4 加单密码鉴权 |
| **磁盘耗尽未处理** | 下载中途可能失败 | V4 加提交前空间检查 |
| **不支持播放列表** | 只能单视频下载 | V4 规划 |
| **不支持字幕下载** | 仅视频 | V4 规划 |

---

## 六、待办清单

### P0（必须尽快处理）
- [ ] **md5 差异问题（未定位根因）** —— 见下文「遗留问题详解」

### P1
- [ ] Cookie 失效时首页黄色横幅提示
- [ ] 下载失败自动重试（风控类错误等 60s 重试 1 次）
- [ ] 下载中刷新页面自动恢复 SSE 监听（GET /api/tasks/active）

### P2
- [ ] 播放列表支持
- [ ] 简单访问密码
- [ ] 下载完成通知

### P3
- [ ] 磁盘空间预警
- [ ] 字幕下载
- [ ] 孤儿 .part 文件定期清理

---

## 七、遗留问题详解

### 上传成功路径下 cookies.txt md5 变化（未定位根因）

**现象**：
- 上传前 cookies.txt 与上传后字节数完全相同（8288 字节）
- 但 md5 不同
- 内容差异仅在第 7 列（值），长度不变、内容变

**已排除的假设**：
1. ❌ 非法 UTF-8 字节 —— 容器内 `iconv -f UTF-8` 检查 0 个错误
2. ❌ U+FFFD 替换 —— 检查 0 个替换字符
3. ❌ CRLF ↔ LF 转换 —— 两份文件都是 60 个单独 LF，末字节都是 `_\n`
4. ❌ 测试脚本自身问题 —— curl 与 Python 两个独立实现都复现，且差异行数还不同（5 行 / 10 行）

**功能上无影响**：
- yt-dlp 用上传后的文件真实验证通过
- 真实视频下载成功（标题正确取回）
- 线上 Cookie 可用

**怀疑方向（未证实）**：
- 某处把 multipart 字节当字符串做了非严格编解码
- Flask `request.files.get("file")` 返回的 BytesIO 在传递过程中可能经过隐式编码

**用户决定**：不深挖，如实登记。功能可用即可。

**如果未来要查**：在 `_cookie_upload` 的覆盖点前打印 `body.hex()` 与 `file.read().hex()` 对比，定位是哪一步引入差异。

---

## 八、构建发布命令

### 本机 WSL（开发 / 测试）
```bash
cd /mnt/e/work/ytdl-app

# 改代码后重建
docker compose up -d --build

# 启动 / 停止 / 重启
docker compose up -d
docker compose down
docker compose restart

# 看日志
docker logs -f ytdl-app

# 进入容器调试
docker exec -it ytdl-app bash
```

### 导出镜像给 NAS / 服务器
```bash
docker save ytdl-app:latest | gzip > ytdl-app-v3.0.3.tar.gz
```

### 推送到阿里云 ACR

**推荐：一键脚本（版本号可传参，不用再手改脚本）**
```bash
cd /mnt/e/work/ytdl-app
bash scripts/_rebuild_push.sh v3.0.3   # 省略参数则用脚本默认版本
```
脚本流程：停容器 → 清旧镜像 → buildx 无缓存构建（`--provenance=false`）→ 起容器验版本 → 打 ACR tag → 推送版本 tag 与 latest → `imagetools inspect` 远端 manifest 校验。

**手工等价命令**
```bash
# 必须用 buildx 且禁用 provenance（ACR 不识别 OCI attestation manifest，见踩坑 #6）
docker buildx build --no-cache --provenance=false \
    --platform linux/amd64 -t ytdl-app:latest .

# 打 tag
docker tag ytdl-app:latest registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.3
docker tag ytdl-app:latest registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:latest

# 推送
docker push registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.3
docker push registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:latest

# 反向验证（按 digest 拉取，跳过本机 tag 缓存）
docker pull registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app@sha256:<推送返回的 digest>
```

**最近一次推送记录（V3.0.3，2026-09-24）**
```
构建       -> buildx --no-cache --provenance=false --platform linux/amd64，02:34:29 → 02:40:48
推送返回   -> v3.0.3  digest: sha256:e26cdede047f63be3598faa8f147c5471ced8bdf5c0d288ab7ddc589f9d4c1ed size: 2382
推送返回   -> latest  digest: sha256:e26cdede047f63be3598faa8f147c5471ced8bdf5c0d288ab7ddc589f9d4c1ed size: 2382（同一镜像）
远端校验   -> MediaType: application/vnd.oci.image.manifest.v1+json（单 manifest，无 attestation，见踩坑 #6）
本地镜像   -> ID e26cdede047f（与远端 digest 前缀一致，确认为同一镜像）
容器复验   -> docker top: 仅 1 个 gunicorn worker；docker logs: Using worker: gthread；curl /api/version: {"ok":true,"version":"3.0.3"}
```
⚠️ ACR 上的 `v3.0.1` 仍是坏的（`--windowsfilenames` 参数名拼写错误，解析/下载/Cookie 验证全失效），NAS 若已拉取该 tag，需更新到 `v3.0.3`。

### NAS / 服务器部署
```bash
# 上传 ytdl-app-v3.0.3.tar.gz 和 docker-compose.server.yml 到服务器
cd /opt/ytdl
mkdir -p downloads config
gunzip -c ytdl-app-v3.0.3.tar.gz | docker load
docker compose -f docker-compose.server.yml up -d
```

### 版本号递增流程
1. 改 `app/main.py` 的 `VERSION = "3.0.3"`
2. 改 `templates/index.html` 的 footer 显示版本
3. 改 `README.md` / `DESIGN.md` / `PROJECT_STATE.md` 中的版本号
4. `docker compose up -d --build`
5. 跑回归测试
6. `git commit` 中文提交信息
7. 导出镜像 `ytdl-app-v3.0.3.tar.gz`（**附件名用 ASCII**，不要用中文文件名）
8. 推送到 ACR：`docker buildx build --no-cache --provenance=false ...`（见上一节「推送到阿里云 ACR」）

### 桌面工具打包（tools/cookie-exporter）
```powershell
# 首次准备（国内源）
cd tools\cookie-exporter
python -m venv .venv
.venv\Scripts\python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple yt-dlp pyinstaller

# 打包（在仓库根目录或任意位置均可）
powershell -ExecutionPolicy Bypass -File tools\cookie-exporter\build\build.ps1

# 产物
tools\cookie-exporter\build\dist\YtCookieExporter.exe
```

源码方式运行（调试界面时用）：
```powershell
tools\cookie-exporter\.venv\Scripts\python tools\cookie-exporter\src\main.py
```

**注意**：`build/build.ps1` 含中文注释，保存时必须带 UTF-8 BOM（见踩坑 #11）；`.spec` 已在脚本里用 `--specpath build` 固定到 build 目录内（见踩坑 #12）。

### 桌面工具发布（exe 走 Release 附件）

**铁律：exe 不提交进 git 仓库**，只作为 GitHub Release 附件发布（原则与理由见 `DESIGN.md` 8.7）。

```bash
# 1. 打注解 tag —— 独立版本线，勿用主服务的 vX.Y.Z
git tag -a tool-v1.0.0 -m "桌面工具 V1.0.0 — Cookie 导出器" <commit>
git push origin tool-v1.0.0

# 2. 建 Release，正文必备六项：
#    用途 / 运行前提 / 用法 / 隐私边界 / 实测记录 / SHA256 校验值

# 3. 上传附件（附件名必须 ASCII）
#    POST https://uploads.github.com/repos/mylxnet/ytdl-app/releases/<release_id>/assets?name=YtCookieExporter.exe
#    Content-Type: application/octet-stream

# 4. 回验：从 Release 下载回来，核对 SHA256 与本地产物一致
#    本地产物路径 tools/cookie-exporter/build/dist/YtCookieExporter.exe
```

**禁止**：用 GitHub 网页 `Add files via upload` 传 exe——该入口**绕过 `.gitignore`**，会把 18.7 MB 二进制写进 git 历史。V1.0.0 发布时踩过，最终只能以 `--force-with-lease` 覆盖远程 `main` 返工。

**当前发布记录**见 2.4 节「发布（2026-09-24）」。

---

## 九、协作约定（本项目内）

- 全程中文：沟通、代码注释、提交信息、技术文档
- 每次改动完成即提交，一轮完整改动对应一个提交
- 提交信息用中文，说清做了什么
- 版本号三处一致（后端 / 界面 / 文档）
- 技术文档三件套必须同步：`DESIGN.md` / `README.md` / `PROJECT_STATE.md`
- 改完要给可核实的证据（跑测试并给出真实输出）
- 踩过的坑要沉淀到本文档，避免重复踩
- 收尾要清理：临时脚本 / 测试脚本 / 中间产物，但打包素材保留
- 二进制交付物（exe / 镜像包等）走 GitHub Release 附件，**不入 git 仓库**；禁止用网页 `Add files via upload` 上传二进制（该入口绕过 `.gitignore`，见 `DESIGN.md` 8.7）

---

## 十、变更记录

| 版本 | 日期 | 变更摘要 |
|---|---|---|
| 文档 | 2026-09-24 | 新增「桌面工具发布规范」：exe 只作为 GitHub Release 附件发布、不入 git 仓库（`DESIGN.md` 8.7 讲原则 + 本文档第八章讲命令 + 协作约定一条）；README 与 2.4 节补 Release 下载链接与 SHA256 校验值 |
| V3.0.3 | 2026-09-24 | **修复「页面进度不动、文件其实已下载」**：gunicorn 由 `-w 2`（sync）改为 `-w 1 -k gthread --threads 8`，消除多 worker 进程内状态分裂；输出文件名加入画质标记，换画质可真正重下；识别 `has already been downloaded` 并如实上报 `skipped`，不再虚增历史。本机实测：单 worker、任务状态 20/20 命中（修复前 15/20）、SSE 实时进度正常、720p 真实下载 20.03 MB、同画质重下 skipped。新增踩坑 #16 |
| V3.0.2 | 2026-09-24 | **紧急修复 V3.0.1 引入的致命回归**：yt-dlp 参数名 `--windowsfilenames` → `--windows-filenames`，恢复解析 / 下载 / Cookie 验证三条链路；版本号六处同步；容器重建后完成真实下载取证（MP3 9,143,012 字节）；新增踩坑 #15（参数名拼写 + 未验证发版）；镜像推送 ACR（v3.0.2 + latest，digest `fc8c0c87…`，无 attestation）；发布脚本 `_rebuild_push.sh` 版本号参数化 |
| V3.0.1 | 2026-09-24 | 修复特殊字符文件名下载失败（新增文件名清理参数，**参数名拼写错误**，见踩坑 #7/#15）；项目目录重组（`doc/` `test/` `deploy/` `tools/` `scripts/`）；镜像推送 ACR（v3.0.1 + latest）⚠️ **该版本实际不可用** |
| 桌面工具 V1.0.0 | 2026-09-24 | 新增 `tools/cookie-exporter`：浏览器 Cookie 导出器（Tkinter 界面 + yt-dlp），单文件 exe 19.6 MB，目标机器免装 Python；新增踩坑 #8~#14（Tkinter 线程模型、验证三态、凭据最小化、PowerShell BOM、PyInstaller specpath、单文件双进程、PrintWindow 取证）；清理一次性调试脚本与中间产物，保留 `build/build.ps1` |
| V3.0.0 (ACR) | 2026-09-23 | 镜像推送至阿里云 ACR（v3.0.0 + latest），补充 DEPLOY.md、README 部署章节、踩坑 #6（buildx provenance） |
| V3.0.0 | 2026-09-23 | 本文件首次建立，同步 V3 全部改动与踩坑记录 |
| V2.x | 2026-09-22 | 项目交接文档首次建立 |

---

by Mr lin
