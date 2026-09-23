# 项目状态 / 交接文档

> 项目：YouTube 下载器（ytdl-app）
> 当前版本：**V3.0.0**（2026-09-23）
> 署名：by Mr lin

---

## 一、当前版本

| 项 | 值 |
|---|---|
| 版本号 | 3.0.0 |
| 代码位置 | `e:\work\ytdl-app` |
| 镜像 | `ytdl-app:latest`（WSL `lxsyzd` 内） |
| 访问地址 | http://localhost:8765 |
| 下载目录 | `/mnt/e/Downloads/YouTube` |
| Cookie 位置 | `./config/cookies.txt` |

**版本号三处一致性校验**：
- 后端 `app/main.py` 第 28 行 `VERSION = "3.0.0"`
- 页面 footer `V3.0.0 · by Mr lin`
- 本文档 / README.md / DESIGN.md 均标注 V3.0.0

---

## 二、已完成功能（V3.0.0）

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
| **gunicorn 2 worker 跨进程不共享 TASKS** | 极端情况下可能并发下载两个任务，违背串行设计 | V4 改 1 worker |
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
- [ ] gunicorn 改 1 worker

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
docker save ytdl-app:latest | gzip > ytdl-app-v3.0.0.tar.gz
```

### NAS / 服务器部署
```bash
# 上传 ytdl-app-v3.0.0.tar.gz 和 docker-compose.server.yml 到服务器
cd /opt/ytdl
mkdir -p downloads config
gunzip -c ytdl-app-v3.0.0.tar.gz | docker load
docker compose -f docker-compose.server.yml up -d
```

### 版本号递增流程
1. 改 `app/main.py` 的 `VERSION = "3.0.0"`
2. 改 `templates/index.html` 的 footer 显示版本
3. 改 `README.md` / `DESIGN.md` / `PROJECT_STATE.md` 中的版本号
4. `docker compose up -d --build`
5. 跑回归测试
6. `git commit` 中文提交信息
7. 导出镜像 `ytdl-app-v3.0.0.tar.gz`（**附件名用 ASCII**，不要用中文文件名）

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

---

## 十、变更记录

| 版本 | 日期 | 变更摘要 |
|---|---|---|
| V3.0.0 | 2026-09-23 | 本文件首次建立，同步 V3 全部改动与踩坑记录 |
| V2.x | 2026-09-22 | 项目交接文档首次建立 |

---

by Mr lin
