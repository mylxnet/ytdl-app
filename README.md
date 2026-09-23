# YouTube 下载器（ytdl-app）

粘贴 YouTube 链接 → 解析预览 → 倒计时 3 秒自动下载 → 页内预览 / 下载回本机。
Flask + yt-dlp + ffmpeg + Node（EJS 挑战），Docker 镜像交付。部署在 NAS，浏览器访问。

**版本：V3.0.1** · by Mr lin

---

## 功能特性

- **链接解析**：标题 / 时长 / UP主 / 封面
- **画质**：1080p（默认）/ 4K / 720p / 仅音频 MP3
- **倒计时 3 秒自动下载**：解析完不用手动点按钮，倒计时期间可点「取消」中止
- **SSE 实时进度**：百分比 / 速度 / 剩余时间
- **页内预览**：弹窗播放，支持拖动 seek（HTTP Range）
- **下载回本机**：一键触发浏览器「另存为」，选择本地目录保存
- **已下载文件列表**：单层平铺，含体积 / 时间 / 类型，可预览 / 下载 / 删除
- **Cookie 热上传**：网页上传 cookies.txt，校验 → 备份 → 覆盖 → 真实视频验证 → 失败自动回滚，**无需重启服务**
- **Cookie 登录态 + Node JS 挑战**，绕过 YouTube 机器人验证

---

## 环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Docker | 任意支持 compose 版本 | NAS / WSL 均可 |
| yt-dlp | 2026.08.19 | 镜像内置 |
| ffmpeg | 7.1.5 | 音视频合并，镜像内置 |
| Node.js | v22.23.2 | EJS JS 挑战运行时，镜像内置 |
| Python | 3.12 | 后端，镜像内置 |

**无需本机安装任何运行时** —— 镜像自包含。

---

## 快速开始

### 1. 部署（本机 WSL）
```bash
cd /path/to/ytdl-app
docker compose up -d --build
# 访问 http://localhost:8765
```

### 2. 部署（NAS / 服务器）

**推荐：从阿里云 ACR 拉取**

```bash
mkdir -p downloads config
docker pull registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1
docker run -d --name ytdl-app --restart unless-stopped \
  -p 8765:8765 \
  -v "$PWD/downloads":/downloads \
  -v "$PWD/config":/config \
  -e TZ=Asia/Shanghai \
  registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1
```

**离线部署（NAS 无公网）**

```bash
# 联网机器导出
docker save registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1 -o ytdl-app-v3.0.1.tar
# 拷到 NAS 后加载
docker load -i ytdl-app-v3.0.1.tar
```

详见 [DEPLOY.md](./doc/DEPLOY.md)。

### 3. 上传 Cookie（首次必须）
1. 用浏览器登录 youtube.com
2. 用 Cookie 导出工具导出 `cookies.txt`（Netscape 格式）
3. 打开网页 → 「上传 Cookie」→ 选择文件 → 自动验证
4. 页面提示「Cookie 有效」即完成

---

## 使用说明

1. 粘贴 YouTube 链接 → 回车（或点「解析」）
2. 选择画质，点「解析」
3. 倒计时 3 秒后自动开始下载（期间可点「取消」）
4. 下载完成 → 文件列表出现新条目
5. **预览**：点「预览」在弹窗播放
6. **下载到本机**：点「下载」，浏览器弹出「另存为」，选目录保存
7. **删除**：点「删除」并确认

---

## 项目结构

```
ytdl-app/
├── app/
│   └── main.py              # Flask 后端（唯一入口）
├── templates/
│   └── index.html           # 单页前端（无框架）
├── static/
│   └── ytdl_redirect.html
├── config/                  # Google 登录凭证（不入 git）
│   └── cookies.txt
├── doc/                     # 文档
│   ├── DEPLOY.md            # NAS 部署手册
│   ├── DESIGN.md            # 设计方案
│   └── PROJECT_STATE.md     # 项目状态 / 交接文档
├── deploy/                  # Docker Compose 部署文件
│   ├── docker-compose.yml           # 本机（WSL）部署
│   └── docker-compose.server.yml    # NAS / 服务器部署
├── test/                    # 测试代码
│   ├── test_v3.py
│   ├── test_e2e.sh
│   └── test_upload.py
├── tools/                   # 用户运维工具
│   ├── 刷新Cookie.bat       # Windows 一键导出 Cookie
│   ├── 刷新Cookie.ps1
│   └── _backup.sh           # Cookie 备份脚本
├── scripts/                 # 发布脚本
│   └── _rebuild_push.sh     # 重建镜像 + 推 ACR
├── Dockerfile               # 镜像构建
├── requirements.txt
├── README.md                # 本文档
└── .gitignore
```

---

## 技术栈

| 层 | 选型 | 版本 |
|---|---|---|
| 后端 | Flask | 3.1.3 |
| WSGI 服务器 | gunicorn | 26.2.0（2 worker） |
| 下载核心 | yt-dlp | 2026.08.19 |
| 音视频合并 | ffmpeg | 7.1.5 |
| JS 挑战运行时 | Node.js | 22.23.2 |
| 前端 | 原生 HTML/CSS/JS | 无框架 |
| 交付 | Docker | 自包含镜像 |

---

## API 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/version` | 返回版本号 |
| POST | `/api/probe` | 解析链接元数据 |
| POST | `/api/download` | 提交下载任务 |
| GET | `/api/task/<id>` | 查询任务状态 |
| GET | `/api/stream/<id>` | SSE 实时进度 |
| GET | `/api/history` | 历史记录 |
| GET | `/api/files` | 已下载文件列表 |
| GET | `/api/preview?name=` | 页内预览（支持 Range） |
| GET | `/api/download-file?name=` | 下载回本机 |
| DELETE | `/api/file?name=` | 删除文件 |
| POST | `/api/open-folder` | 返回下载目录路径 |
| POST | `/api/cookie-upload` | 上传 Cookie（multipart/form-data，字段名 `file`） |

---

## Cookie 更新（失效时）

**现象**：所有视频都报 "Sign in to confirm you're not a bot"。

**推荐做法**（V3）：
1. 本机浏览器登录 youtube.com
2. 导出 `cookies.txt`
3. 网页 → 「上传 Cookie」→ 选择文件
4. 系统自动验证并生效，**无需重启**

**手动备份**（可选）：
```bash
cp config/cookies.txt /path/to/backup/cookies.txt.$(date +%Y%m%d)
```

---

## 常见问题

**Q：下载失败怎么办？**
A：先点「刷新」看文件列表有没有。如果 Cookie 过期，先上传新 Cookie。如果是 YouTube 风控，换一个视频试试。

**Q：为什么下载很慢？**
A：YouTube 限制。换画质（1080p 比 4K 快），或检查服务器网络。

**Q：如何更新版本？**
A：本机 `docker compose up -d --build`，或重新导出镜像部署到 NAS。

**Q：支持播放列表吗？**
A：暂不支持，V4 规划中。

**Q：如何查看下载目录？**
A：网页 → 「打开目录」按钮，或访问 `/api/open-folder`。

---

## 更新日志

### V3.0.1（2026-09-24）

**修复**
- 文件名含全角竖线 `｜`、emoji 等特殊字符时，`.part` 临时文件无法创建（报 `Error: unable to open for writing`）——yt-dlp 参数新增 `--windowsfilenames`，由 yt-dlp 统一清理跨平台非法字符

### V3.0.0（2026-09-23）

**新增**
- 解析后倒计时 3 秒自动开始下载（可取消中止）
- 页内预览：弹窗播放，HTTP Range 支持拖动 seek
- 下载回本机：`Content-Disposition: attachment` 触发「另存为」
- Cookie 网页热上传：校验 → 备份 → 覆盖 → 真实视频验证 → 失败自动回滚
- `GET /api/version` 返回版本号，校验部署是否为最新

**优化**
- 删除「开始下载」按钮，改为倒计时自动开始
- 删除子目录选择 / 新建，改单层平铺（文件名含视频 ID）
- 事件委托替代内联 onclick
- 中文文件名走 RFC 5987 `filename*`

**修复**
- `_check_cookie_format` 列号错误：`cols[6]` 取到值而非 cookie 名（实际在第 6 列即索引 5），导致正常 Cookie 被误判为「缺少登录凭证」
- `_verify_cookie` 漏 `--remote-components ejs:github`：验证器比真实下载流程弱，把正常 Cookie 误判为失败
- `.hidden` 被 `.countdown` / `.modal` 的 `display:flex` 覆盖（同为单类选择器，后声明胜出），导致初始页面就显示倒计时卡片和预览遮罩，改为 `display:none !important`

**调整**
- 下线 `GET /api/dirs`（子目录接口已无消费者）
- 删除文件统一走 `DELETE /api/file`

---

by Mr lin
