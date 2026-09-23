# YouTube 下载器 — 部署文档

> 版本：**V3.0.1**（2026-09-24）  
> 署名：by Mr lin  
> 目标环境：家用 NAS（Docker / Docker Compose）

---

## 一、快速开始（NAS 用户看这里）

### 前提

- NAS 已装好 Docker Engine 或 Docker Desktop（推荐 Docker 24+）
- NAS 能访问 `registry.cn-hangzhou.aliyuncs.com`（阿里云 ACR 华东 1）
- 一个可读写目录作为下载落盘位置（例如 `/volume1/docker/ytdl/downloads`）

### 三步部署

```bash
# 1. 建工作目录
mkdir -p ~/ytdl-app/downloads && cd ~/ytdl-app

# 2. 拉镜像（v3.0.1 = 固定版本；latest = 最新）
docker pull registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1

# 3. 起容器（下面命令见「完整命令」章节）
docker run -d \
  --name ytdl-app \
  --restart unless-stopped \
  -p 8765:8765 \
  -v ~/ytdl-app/downloads:/downloads \
  -v ~/ytdl-app/config:/config \
  -e TZ=Asia/Shanghai \
  registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1
```

### 访问

浏览器打开 `http://<NAS 内网 IP>:8765`，粘贴 YouTube 链接回车即可。

---

## 二、完整命令

### 2.1 `docker run` 单容器部署

```bash
mkdir -p ~/ytdl-app/downloads ~/ytdl-app/config

docker run -d \
  --name ytdl-app \
  --restart unless-stopped \
  --memory 2g \
  --memory-swap 2g \
  -p 8765:8765 \
  -v ~/ytdl-app/downloads:/downloads \
  -v ~/ytdl-app/config:/config \
  -e TZ=Asia/Shanghai \
  registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1
```

### 2.2 Docker Compose 部署（推荐）

新建 `docker-compose.yml`：

```yaml
services:
  ytdl:
    image: registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1
    container_name: ytdl-app
    restart: unless-stopped
    mem_limit: 2g
    ports:
      - "8765:8765"
    volumes:
      - ./downloads:/downloads
      - ./config:/config
    environment:
      - TZ=Asia/Shanghai
```

启动：

```bash
mkdir -p downloads config
docker compose up -d
```

### 2.3 私有 NAS（无公网）部署

如果 NAS 无法访问外网 ACR：

1. 在联网机器上 `docker pull` + `docker save`：

```bash
docker pull registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1
docker save registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1 \
  -o ytdl-app-v3.0.1.tar.gz  # 约 400MB 压缩后
```

2. 拷到 NAS 后加载：

```bash
docker load -i ytdl-app-v3.0.1.tar.gz
docker run ... registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1 ...
```

---

## 三、目录结构

```
~/ytdl-app/
├── docker-compose.yml        # 你创建
├── downloads/                # 下载的视频落这里（挂到容器 /downloads）
└── config/
    └── cookies.txt           # 可选，Cookie 过期时上传（挂载后由容器读写）
```

---

## 四、Cookie 更新

Cookie 一般有效期 3-7 天。失效表现：所有下载都报 `Sign in to confirm you're not a bot`。

### 4.1 网页上传（推荐，无需重启容器）

1. 在**你自己电脑**的浏览器（Edge/Chrome）登录 `youtube.com`
2. 导出 `cookies.txt`，二选一：
   - **用项目自带桌面工具**（推荐）：`tools/cookie-exporter/build/dist/YtCookieExporter.exe`，双击 → 选浏览器 → 选保存位置 → 点导出。**本机无需安装 Python**，且只保留 YouTube / Google 域凭证，不会泄露其他站点登录态
   - 装浏览器插件 **Get cookies.txt LOCALLY**（不要走 Google 服务器中转的在线版），打开 `youtube.com` 点插件图标导出
3. 在 ytdl-app 网页上点右上角「⚙ Cookie 设置」展开，选上传
4. 上传后自动验证，成功会显示 `✓ 上传成功（N 条 Cookie），验证视频：xxx`

### 4.2 直接替换 config/cookies.txt

```bash
# Linux NAS
scp cookies.txt nasuser@<NAS>:/path/to/ytdl-app/config/cookies.txt

# Windows
# 用 FileZilla / WinSCP 上传，或把 NAS 共享目录拖进去
```

替换后**无需重启容器**，下一次下载自动用新 Cookie。

---

## 五、常用运维命令

```bash
# 查看日志（跟随）
docker logs -f ytdl-app

# 查看当前进程
docker ps --filter name=ytdl-app

# 重启
docker restart ytdl-app

# 停止并保留数据
docker stop ytdl-app

# 停止并删除容器（数据在宿主机，不会丢）
docker stop ytdl-app && docker rm ytdl-app

# 更新到新版本
docker pull registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1
docker stop ytdl-app && docker rm ytdl-app
# 重新 docker run（把 image tag 改成 v3.0.1）

# 清理悬空镜像
docker image prune -f
```

---

## 六、健康检查

```bash
# 服务是否活着
curl -s http://localhost:8765/api/version
# 期望：{"ok":true,"version":"3.0.1"}

# 磁盘空间（下载大文件必备）
df -h ~/ytdl-app/downloads
```

---

## 七、常见问题

**Q1: 视频一直报 `Sign in to confirm you're not a bot`？**  
Cookie 过期，按第四节上传新 Cookie。

**Q2: 4K 视频下载失败，1080p 正常？**  
4K 需要 Node.js + yt-dlp EJS 组件支持。镜像已内置 Node 22 与 `--remote-components ejs:github`，一般不会遇到。若遇到，检查 Docker 容器是否能访问 `github.com`。

**Q3: 下载到一半中断，任务卡住不动？**  
浏览器页面刷新任务不丢（后台 gunicorn worker 继续跑）。刷新页面重新进入即可看到进度。如果 5 分钟以上无进度变化，`docker logs ytdl-app` 看有没有 yt-dlp 报错。

**Q4: 内存吃满？**  
1080p 下载约 300-600MB 内存，4K 合并阶段可能 1.5GB+。已给容器 `--memory 2g`，NAS 内存小的用户建议限制最高画质为 1080p。

**Q5: 下载的文件在哪里？**  
在容器的 `/downloads` 目录，映射到宿主机你 `-v` 挂载的目录（默认 `~/ytdl-app/downloads`）。浏览器页面上的「下载」按钮会把它从 NAS 拷回你电脑。

**Q6: 端口 8765 被占用？**  
改 `docker run` / `docker-compose.yml` 里的 `-p` 左边，例如 `-p 8865:8765`，然后用 `http://<IP>:8865` 访问。

**Q7: 镜像太大，拉取慢？**  
1.2GB 属正常（内置 Python 3.12 + yt-dlp + ffmpeg 7 + Node 22 + EJS）。首次拉取后 NAS 本地缓存，重启不会重拉。

---

## 八、升级与回滚

### 升级

```bash
docker pull registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1   # 新 tag
docker stop ytdl-app && docker rm ytdl-app
# 修改 compose.yml 里的 image tag，或重新 docker run 指定新 tag
docker compose up -d    # 或者用第一节的一键命令
```

### 回滚

```bash
docker pull registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1
docker stop ytdl-app && docker rm ytdl-app
docker run ... registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app:v3.0.1 ...
```

数据（视频、Cookie）都在宿主机挂载目录，升级/回滚不丢。

---

## 九、镜像元信息

| 字段 | 值 |
|---|---|
| 仓库 | `registry.cn-hangzhou.aliyuncs.com/mylxnet/ytdl-app` |
| 当前版本 | `v3.0.1` |
| 镜像大小 | 约 1.2 GB（含 Node/ffmpeg/yt-dlp） |
| 基础镜像 | `python:3.12-slim` |
| 端口 | `8765` |
| 运行进程 | gunicorn（2 worker，timeout 7200s） |
| 系统语言 | 中文界面 |
| 目标硬件 | NAS / x86_64 Linux |

---

署名：by Mr lin
