# YouTube 下载器 — 设计方案 V3

> 版本：V3.0.3（2026-09-24）
> 现状：V3 已上线并验证（Flask + yt-dlp + Docker，NAS 部署 / 浏览器访问 / 文件回传本机）
> 本文档：完整设计方案 + 关键问题清单，作为后续演进与部署的依据
> by Mr lin

---

## 一、系统定位

**一句话**：自托管的 YouTube 视频下载站——部署在 NAS 上，浏览器访问，文件在 NAS 生成后通过浏览器「另存为」拷回本机。

**设计原则**（按优先级）：
1. **可用性优先**——YouTube 风控是最大敌人，一切设计围绕「能稳定下到视频」
2. **零配置使用**——不装客户端、不改浏览器设置，浏览器打开即用
3. **单人/家庭使用**——不做多用户体系
4. **容器化交付**——任何有 Docker 的机器（NAS / 本机 WSL）一条命令跑起来
5. **零外部依赖**——不依赖第三方下载 API，全部本地完成

---

## 二、总体架构

```
┌───────────────────────────────────────────────────┐
│ 浏览器（单页，无框架）                                │
│  粘贴链接 → 解析预览 → 倒计时 3s → 自动下载           │
│  进度条 → 文件列表（预览 / 下载 / 删除）               │
│  上传 Cookie（无需重启生效）                           │
└──────────────┬────────────────────────────────────┘
               │ HTTP / SSE（实时进度）/ Range（预览拖动）
┌──────────────▼────────────────────────────────────┐
│ Flask 后端（gunicorn，容器内 8765）                   │
│  ┌───────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ 任务队列    │→│ yt-dlp    │  │ /api/* 路由     │  │
│  │ (线程串行)  │  │ 子进程管理 │  │ probe/download │  │
│  └───────────┘  └────┬─────┘  │ preview/stream │  │
│                      │         │ cookie/file    │  │
│                      │         └────────────────┘  │
└──────────────────────┼─────────────────────────────┘
                       │
        ┌──────────────▼──────────────────────┐
        │ yt-dlp 三件套（风控对抗核心）            │
        │  ① cookies.txt（Google 登录态）        │
        │  ② Node 22（EJS JS 挑战运行时）        │
        │  ③ --remote-components ejs:github     │
        │  + ffmpeg（音视频合并）                  │
        └──────────────┬──────────────────────┘
                       │ 卷挂载
        ┌──────────────▼──────────────────────┐
        │ /downloads → NAS 共享目录              │
        │  （单层平铺，文件名含视频 ID）             │
        └─────────────────────────────────────┘
```

**关键设计决策与理由**：

| 决策 | 理由 | 放弃的方案 |
|---|---|---|
| 串行队列（同时只下 1 个） | 同 IP 并发多任务极易触发 YouTube 风控，且共享同一 Cookie 身份风险叠加 | 并发池 |
| 子进程调 yt-dlp 而非 import 库 | 官方 exe/独立进程隔离崩溃；超时可直接 kill；版本升级独立 | yt_dlp Python API |
| SSE 而非 WebSocket | 单向推送够用，实现简单，无需额外依赖 | WebSocket / 轮询 |
| JSON 文件存历史而非 SQLite | 数据量小（≤200 条），免维护 | SQLite/MySQL |
| **V3：单层平铺目录** | NAS 共享给本机浏览时，深层目录增加「另存为」操作成本；单层 + 文件名含视频 ID 已足够可辨识 | V1/V2 的 4 层子目录 |
| **V3：页内 HTTP Range 预览** | 浏览器原生 `<video>` + `send_file(conditional=True)` 免费获得 seek，无需额外转码服务 | 服务端转码预览 / 外挂播放器 |
| **V3：Cookie 热上传** | 原「导出→拷文件→重启容器」链路太长，且重启会打断进行中任务；改成网页上传，上传即校验即生效 | 仍走本地脚本 + restart |
| **V3：倒计时 3 秒自动下载** | 减少一次点击，倒计时给「后悔窗口」可点取消 | V2 的「解析后手动点开始下载」 |

---

## 三、功能清单

### 3.1 V3 已实现（本轮已验证）
| 功能 | 状态 |
|---|---|
| 链接解析（标题/时长/UP主/封面） | ✅ |
| 画质选择：1080p 默认 / 4K / 720p / 仅音频 MP3 | ✅ |
| **解析 → 倒计时 3 秒 → 自动下载**（可点取消中止） | ✅ |
| SSE 实时进度（百分比/速度/ETA） | ✅ |
| 串行下载队列 | ✅ |
| 已下载文件列表（单层平铺，含体积/时间/类型） | ✅ |
| **页内预览**：`<video>`/`<audio>` 弹窗，HTTP Range 支持拖动 seek | ✅ |
| **下载回本机**：`Content-Disposition: attachment` 触发浏览器「另存为」 | ✅ |
| 文件删除（带确认） | ✅ |
| Cookie 登录态 + Node JS 挑战，绕过 YouTube 机器人验证 | ✅ |
| **Cookie 热上传**：网页上传 cookies.txt，校验→备份→覆盖→真实视频验证→失败回滚 | ✅ |
| 历史记录 | ✅ |
| 版本号三处一致（后端 `/api/version` / 页面 footer / 文档） | ✅ |

### 3.2 相比 V1/V2 的删改
| 变更 | 说明 |
|---|---|
| ❌ 删除「保存位置自定义」（子目录选择/新建） | NAS 场景下单层平铺更省事，见决策表 |
| ❌ 删除「开始下载」按钮 | 改为解析后倒计时 3 秒自动开始 |
| ❌ 下线 `GET /api/dirs` | 子目录接口已无消费者（回归测试已验证返回 404） |
| ✅ 新增 `POST /api/cookie-upload` | 热上传 Cookie |
| ✅ 新增 `GET  /api/preview` | 页内预览（Range） |
| ✅ 新增 `GET  /api/download-file` | 下载回本机（attachment） |
| 🔁 删除文件统一走 `DELETE /api/file` | 前端与回归测试均以 `/api/file` 为唯一入口 |

### 3.3 V4 规划（按优先级）
| 优先级 | 功能 | 说明 |
|---|---|---|
| P0 | Cookie 失效时首页黄色横幅 | 定期用轻量请求探测，失效时提示「需要更新 Cookie」并给出指引 |
| P1 | 下载失败自动重试 | 风控类错误自动等 60s 重试 1 次 |
| P1 | 播放列表支持 | 探测到 playlist 时列出条目，支持勾选批量下载 |
| P2 | 简单访问密码 | 单密码（环境变量注入），防止公网陌生人消耗你的 YouTube 身份 |
| P2 | 下载完成通知 | 界面内 toast + 可选 Telegram / Server酱 |
| P3 | 磁盘空间预警 | 提交前查剩余空间，低于阈值拒绝大任务 |
| P3 | 字幕下载 | 可选下载 srt/vtt 字幕 |

---

## 四、需要注意的问题（核心章节）

### 4.1 YouTube 风控对抗 ⚠️ 最大风险源

**问题本质**：YouTube 用「IP 信誉 + Cookie 身份 + JS 挑战 + PO Token」四层组合识别机器人，2025 年起持续收紧，且**按视频随机触发**。

**实测确认的现象**（2026-09）：
- 同一 Cookie、同一时刻：视频 A 可下载，视频 B 报 "Sign in to confirm you're not a bot" ——**这不是 Cookie 失效，重试即可**
- 缺少 EJS 挑战脚本时只给缩略图流（storyboard），报 "Only images are available"
- pip 安装的 yt-dlp 不自带挑战脚本，必须 `--remote-components ejs:github`

**应对策略**：
1. 三件套齐全是底线：登录 Cookie + Node 运行时 + EJS 脚本，缺一不可
2. **验证器的参数必须与真实下载完全一致**（见 PROJECT_STATE.md 踩坑记录 #4）——否则验证器比真实流程弱，会把正常 Cookie 误判为失败
3. 错误分类必须区分「整体失效」与「个别失败」——**不要在个别失败时引导用户重刷 Cookie**
4. 保持串行；未来若加并发，上限 2 且不同时启用 4K
5. yt-dlp 版本升级走「灰度」：先跑 3 个已知视频回归，通过再替换主服务
6. IP 信誉是隐藏变量：家宽 IP 通常健康；云服务器 IP（尤其海外 VPS）信誉差，**服务器部署可能需要配代理**

**Cookie 生命周期管理**：
- 有效期一般 2-6 个月
- V3 起刷新流程：**本机浏览器登录 → 导出 cookies.txt → 网页上传**（无需重启容器）
- 上传时会先用真实视频验证有效性，验证失败自动回滚到上传前的备份

### 4.2 安全问题

| 问题 | 现状 | 后续措施 |
|---|---|---|
| 路径穿越 | ✅ 已拦截：白名单规则（禁 `/` `\` `..` 与控制字符）+ `resolve()` 前缀校验 | 保持 |
| 无鉴权暴露 | 局域网可见，公网部署=裸奔 | 单密码鉴权（P2）；公网必加 |
| SSRF | probe 接口已限 YouTube 域名正则 | 保持白名单正则 |
| 子进程注入 | 参数全部列表传参（不经 shell） | 保持 |
| 磁盘耗尽 | 未处理 | P3：提交前查剩余空间 |
| Cookie 泄露 | cookies.txt 含 Google 登录凭证，等价账号 | 权限 600；不入 git（.gitignore）；上传时先备份再覆盖 |
| **上传接口滥用** | 1MB 上限 + 格式校验（≥10 条、4 类登录凭证 ≥3 个命中）+ 仅接受 .txt | 保持 |
| 公网合规 | 下载 YouTube 内容视地区/内容涉版权 | 仅自用；不在公网开放目录浏览/下载 |

### 4.3 稳定性与资源

| 问题 | 影响 | 对策 |
|---|---|---|
| yt-dlp 卡死（进程 hang） | 任务永久排队 | 已有 `proc.wait(timeout=3600)`；后续加进度 5 分钟无变化自动 kill |
| 大文件占满带宽 | 家用网络卡顿 | 预留 `--limit-rate` 环境变量配置 |
| 磁盘写满中途失败 | 半成品 .part 文件 | yt-dlp 自带 .part 机制；加定期清理孤儿 .part |
| **gunicorn 2 worker** | 双任务并发下载（违背串行设计） | 当前实际是「gunicorn 2 worker + 每个 worker 内部线程队列」，**跨 worker 不共享 TASKS**；已知限制，V4 改为 1 worker |
| 容器重启丢任务 | TASKS 在内存 | 可接受（单人使用） |
| 时区/文件名乱码 | 容器默认无中文 locale | 镜像内设 `LANG=C.UTF-8` + `TZ=Asia/Shanghai`（已做 TZ） |

### 4.4 部署形态差异

| 环境 | 差异点 | 注意 |
|---|---|---|
| **NAS（当前部署目标）** | 浏览器访问，文件回传本机靠「另存为」 | 需保证端口可达；建议先跑 1 个短视频验证 |
| 本机 WSL（开发/测试） | 挂载 `/mnt/e/...`，Windows 文件系统 I/O 慢 | 4K 大文件下载建议挂 Linux 原生路径再搬运 |
| 1Panel 服务器 | IP 信誉风险 ↑；需反代+密码；磁盘配额 | 准备好 proxy 配置项 |
| 群晖/QNAP | 老内核可能缺 node22 镜像支持 | 换 debian bookworm base 或直接跑在本机 |

### 4.5 用户体验细节（实测踩过的坑）

1. **个别视频失败 ≠ 系统坏了**——界面必须把这两者区分开，否则用户会反复重刷 Cookie
2. 下载中刷新页面 → 任务在后台继续跑，但进度条丢了 → 后续：页面加载时自动恢复进行中任务的 SSE 监听
3. `%(ext)s` 模板在 Windows shell 转义地狱——代码里已用列表传参规避
4. 中文文件名在 Windows/NAS 正常（卷挂载 UTF-8），但 SMB 共享给旧设备可能乱码——保留 `[视频ID]` 后缀兜底可辨识
5. 4K 视频体积巨大（实测 41 分钟 4K ≈ 1.6GB）——UI 上 4K 选项旁标注预估体积
6. **CSS `.hidden` 必须 `!important`**（见 PROJECT_STATE.md 踩坑记录 #5）——否则被后声明的 `display:flex` 压掉，初始页面就出现倒计时卡片和遮罩

---

## 五、接口清单（V3）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/version` | 返回版本号，校验部署是否为最新 |
| POST | `/api/probe` | 解析链接元数据（标题/时长/UP主/封面） |
| POST | `/api/download` | 提交下载任务，返回 task_id |
| GET | `/api/task/<tid>` | 轮询任务状态（progress/speed/eta/error） |
| GET | `/api/stream/<tid>` | SSE 实时进度推送 |
| GET | `/api/history` | 最近 50 条历史记录 |
| GET | `/api/files` | 单层媒体文件列表（按修改时间倒序） |
| GET | `/api/preview?name=` | 页内预览，`send_file(conditional=True)` 支持 Range seek |
| GET | `/api/download-file?name=` | 下载回本机，`as_attachment=True` 触发「另存为」 |
| DELETE | `/api/file?name=` | 删除文件 |
| POST | `/api/open-folder` | 返回下载目录绝对路径 |
| POST | `/api/cookie-upload` | 热上传 cookies.txt（multipart/form-data，字段名 `file`） |

---

## 六、部署方案

### 6.1 本机 WSL（开发/测试）
```bash
cd /mnt/e/work/ytdl-app && docker compose up -d
# 访问 http://localhost:8765
```

### 6.2 NAS / 服务器（生产）
1. 本机导出：`docker save ytdl-app:latest | gzip > ytdl-app.tar.gz`
2. 上传 NAS 挂载目录，`docker load`
3. 目录规划：`{downloads,config}`，cookies.txt 放 config
4. `docker compose -f docker-compose.server.yml up -d`
5. 浏览器访问 `http://NAS-IP:8765`
6. **部署后首验**：跑 1 个短视频 → 确认无机器人验证 → 再投入使用

### 6.3 升级流程
1. 改代码 → `docker compose up -d --build`
2. 跑回归：短视频下载 + Range 预览 + Cookie 上传 + 路径穿越拦截
3. 通过后再 `docker save` 导出给 NAS

---

## 七、里程碑

| 阶段 | 内容 | 状态 |
|---|---|---|
| V1（已完成） | 核心下载 + 自定义目录 + Docker 化 | ✅ |
| V2（已规划未落地） | Cookie 健康自检 + 错误分类提示 + 进行中任务恢复 | ⏸ 被 V3 取代 |
| **V3.0.0（已完成）** | **NAS 场景重构：删子目录 / 删开始按钮 / 倒计时自动下载 / 页内预览 / 下载回本机 / Cookie 热上传** | ✅ |
| V3.0.1（已发版，不可用） | 特殊字符文件名下载修复（参数名拼写错误，见 V3.0.2）；项目目录结构重组 | ⚠️ 已被 V3.0.2 取代 |
| **V3.0.2（已完成，本机实测通过）** | **修复 V3.0.1 的 yt-dlp 参数名错误（`--windowsfilenames` → `--windows-filenames`），恢复解析 / 下载 / Cookie 验证；真实下载 MP3 取证** | ✅ |
| **V3.0.3（已完成，本机实测通过）** | **修复「页面进度不动、文件其实已下载」：gunicorn 改单进程 + gthread，消除多 worker 进程内状态分裂；文件名加入画质标记，换画质可真正重下；已存在文件如实上报 `skipped`** | ✅ |
| **桌面工具 V1.0.0（已完成）** | **Cookie 导出器：浏览器 Cookie → cookies.txt，单文件 exe 交付** | ✅ |
| V4.0 | Cookie 健康横幅 + 失败自动重试 + 播放列表 + 访问密码 | 待排期 |
| V4.x | 通知 + 磁盘预警 + 字幕 | 按需 |

---

## 八、Cookie 导出桌面工具（tools/cookie-exporter，独立版本 V1.0.0）

### 8.1 为什么需要它

主服务的 Cookie 刷新链路原本是「装浏览器插件 → 手动导出 → 找文件 → 网页上传」，插件来源杂、导出格式不统一。本工具把第一步做成本机双击即用的小程序：选浏览器 → 选保存位置 → 点导出，产出标准 Netscape 格式 `cookies.txt`，再拿去网页上传即可。

### 8.2 交付形态与边界

| 项 | 值 |
|---|---|
| 交付物 | `tools/cookie-exporter/build/dist/YtCookieExporter.exe`（**单文件，约 18.7 MB**） |
| 运行前提 | Windows x64，**目标机器无需安装 Python**（Python 与 yt-dlp 已打进 exe） |
| 版本 | V1.0.0（2026-09-24），界面署名 `V1.0.0  by Mr lin` |
| 语言 / 界面 | Python 3.12 + Tkinter（浅色主题，白底灰边按钮，无红色按钮） |
| 核心依赖 | yt-dlp 2026.8.19（读浏览器 Cookie 库并解密） |

**刻意不做的事**（用户明确裁决，勿擅自扩展）：
1. **不代关浏览器**——检测到目标浏览器正在运行只提示「请先关闭」，由用户自行处理
2. **不自动上传**——只在本机生成文件，除一次只读 GET 校验外不发任何网络请求
3. **不记忆上次保存路径**——每次启动路径框留空，避免误用旧文件

### 8.3 项目结构与流程

```
tools/cookie-exporter/
├── src/
│   ├── main.py       # Tkinter 界面 + 单实例互斥 + 主线程队列轮询
│   ├── exporter.py   # yt-dlp 导出 → 校验 → 登录态验证 → 落盘
│   └── browsers.py   # 浏览器 / profile 扫描（输出可直喂 yt-dlp 的绝对路径）
├── assets/icon.ico   # 应用图标（多尺寸）
└── build/
    ├── build.ps1     # 打包素材（长期保留，带 UTF-8 BOM）
    └── dist/         # 产物 exe
```

流程：`选浏览器 profile` → `yt-dlp 读 Cookie 落临时文件` → `格式校验（≥10 条 + 4 项登录凭证命中 ≥3）` → `HTTP 只读验证 https://www.youtube.com/account（不跟随重定向）` → **全部通过才写入用户选定路径**。

### 8.4 关键设计决策

| 决策 | 理由 | 放弃的方案 |
|---|---|---|
| **只保留 youtube.com / google.com 域** | 浏览器 Cookie 库混着淘宝/抖音/飞书等上百个站点凭证，全量落盘等于交出整机账号。实测 710 条中只留 58 条，下载器所需 4 项凭证全部在内 | 全量导出 |
| **先落临时文件，验证通过再落盘** | 验证不通过的文件对用户毫无价值，直接落盘会让用户「以为成功」而误用 | 直接写目标路径 |
| **登录态验证用三态**（有效 / 明确无效 / 网络原因未验证） | YouTube 偶发直接断连，若把网络抖动判成 Cookie 失效，会误导用户反复重刷 Cookie | 二态（成功/失败） |
| **UI 线程与工作线程用队列通信** | Tkinter 不是线程安全的，子线程直接调 `root.after` 会崩 | 子线程直接操作控件 |
| **单实例互斥体 + 唤起已有窗口** | 防止重复启动产生多个导出进程抢占浏览器 Cookie 库 | 允许重复启动 |
| **Helium 等第三方 Chromium 传 profile 绝对路径** | yt-dlp 的 `cookiesfrombrowser` 只认固定浏览器标识，Helium 不在列表内；显式传 profile 路径 + browser key 用 `chrome` 即可正常解密（实测 713 条） | 只支持内置 9 种浏览器 |
| **判定 profile 是否可用看「里面真有 Cookie 库」** | 只看目录名（Default / Profile 1）会把空 profile 也列进来 | 按目录名枚举 |

### 8.5 界面约定（用户明确要求，勿改）

- 浅色清爽，按钮统一白底灰边，**禁用红色 / danger 样式**
- 日志区实时刷新，长耗时操作期间显示滚动进度条
- **提前拦截**：未选保存位置就点导出，在校验阶段拦截并给出修正建议，不等到执行时报错
- 不使用会位移的弹窗动画，提示统一走状态栏与日志
- 任务进行中禁用「浏览」「开始导出」，并拦截窗口关闭，避免中途打断

### 8.6 打包（可复现）

```powershell
# 前置：tools\cookie-exporter\.venv 已装 yt-dlp + pyinstaller（国内源）
python -m venv .venv
.venv\Scripts\python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple yt-dlp pyinstaller

# 打包
powershell -ExecutionPolicy Bypass -File tools\cookie-exporter\build\build.ps1
```

---

## 九、变更记录

| 版本 | 日期 | 新增 | 优化 | 修复 | 调整 |
|---|---|---|---|---|---|
| V3.0.0 | 2026-09-23 | 倒计时 3 秒自动下载；页内 Range 预览；下载回本机（另存为）；Cookie 网页热上传（校验→备份→验证→回滚）；`/api/version` | 删除「开始下载」按钮与子目录选择，改单层平铺；事件委托替代内联 onclick；中文文件名走 RFC 5987 `filename*` | `_check_cookie_format` 列号错（`cols[6]` 取到值而非 cookie 名）；`_verify_cookie` 漏 `--remote-components ejs:github` 导致正常 Cookie 被误判失败；`.hidden` 被 `.countdown`/`.modal` 的 `display:flex` 覆盖需 `!important` | 下线 `/api/dirs`；删除文件统一走 `DELETE /api/file` |
| V3.0.1 | 2026-09-24 | — | — | 文件名含全角竖线 `｜`、emoji 等特殊字符时 `.part` 写入失败（yt-dlp 参数新增 `--windowsfilenames` —— **参数名拼写错误，导致解析/下载/Cookie 验证三处全部失效，该版本实际不可用**） | 项目目录重组：`doc/` `test/` `deploy/` `tools/` `scripts/`，清理一次性调试脚本 |
| V3.0.2 | 2026-09-24 | — | — | **紧急修复 V3.0.1 引入的致命回归**：yt-dlp 参数名 `--windowsfilenames` 更正为 `--windows-filenames`，恢复 `/api/probe`、`/api/download`、`/api/cookie-upload` 三条链路 | 版本号同步六处（后端 / 页面 footer / README / DESIGN / PROJECT_STATE / DEPLOY） |
| V3.0.3 | 2026-09-24 | 前端新增 `skipped` 状态提示「该画质已存在，未重复下载」 | gunicorn 由 `-w 2` 改为 `-w 1 -k gthread --threads 8`：单进程保证任务状态唯一，线程池避免 SSE 独占 worker | ①「进度不动、文件已下载」——多 worker 各持一份 `TASKS`，SSE 落到另一 worker 即刻返回 `gone`；② 换画质重下被静默跳过（文件名不含画质）；③ 跳过时误报 done + 虚增历史（现识别 `has already been downloaded` → `skipped`） | 输出文件名模板加入画质标记 `[1080p]/[2160p]/[720p]/[audio]`；`/api/stream` 终止条件补 `skipped` |
| 桌面工具 V1.0.0 | 2026-09-24 | `tools/cookie-exporter` 独立子模块：浏览器 Cookie → cookies.txt，单文件 exe（18.7 MB，目标机器免装 Python）；浏览器/profile 扫描；登录态三态验证；单实例防重复启动；应用图标 | 只保留 youtube.com / google.com 域（710 → 58 条），避免泄露整机账号凭证；提前拦截未选保存路径；浅色界面 + 白底灰边按钮 | 子线程直接操作 Tkinter 崩溃（改队列 + 主线程轮询）；网络抖动被误判 Cookie 失效（改三态 + 重试 3 次） | 打包脚本 `build.ps1` 固化保留（UTF-8 BOM）；`.gitignore` 忽略 exe 产物但保留打包素材 |
