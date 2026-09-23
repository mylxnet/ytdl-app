# ============================================================
#  YouTube 下载器 — Cookie 一键刷新脚本（双击运行）
#
#  功能：从 Helium 浏览器提取最新 YouTube 登录 Cookie，
#        更新到下载器容器并验证是否生效。
#
#  使用前提：Helium 浏览器里已登录 youtube.com
#  运行时机：下载器所有视频都报 "Sign in to confirm" 时
# ============================================================
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = 'YouTube 下载器 Cookie 刷新'

$Python     = 'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe'
$DumpScript = 'C:\Users\Administrator\bin\dump_yt_cookies.py'
$HeliumUD   = 'C:\Users\Administrator\AppData\Local\imput\Helium\User Data'
$TmpUD      = 'C:\Users\Administrator\bin\chrome_ud'
$OutCookie  = 'E:\work\ytdl-app\config\cookies.txt'
$BakCookie  = 'E:\work\ytdl-app\config\cookies.txt.bak'

function Pause-Exit($msg, $code) {
    Write-Host "`n$msg" -ForegroundColor $(if ($code -eq 0) { 'Green' } else { 'Red' })
    Read-Host '按回车键关闭窗口'
    exit $code
}

Write-Host '==== YouTube 下载器 Cookie 刷新 ====' -ForegroundColor Cyan

# ---- 0. 前置检查 ----
if (-not (Test-Path $Python))     { Pause-Exit "✗ 找不到 Python：$Python" 1 }
if (-not (Test-Path $DumpScript)) { Pause-Exit "✗ 找不到解密脚本：$DumpScript" 1 }
if (-not (Test-Path "$HeliumUD\Default\Network\Cookies")) {
    Pause-Exit "✗ 找不到 Helium 的 Cookie 数据库，请确认 Helium 已安装并登录过 youtube.com" 1
}

# ---- 1. 检查浏览器登录提醒 ----
Write-Host "`n[1/6] 确认 Helium 浏览器已登录 youtube.com（网页能显示头像/账号）" -ForegroundColor Yellow
$ok = Read-Host '已登录？(Y/n)'
if ($ok -eq 'n') {
    Pause-Exit '请先用 Helium 打开 youtube.com 登录账号，再重新运行本脚本。' 1
}

# ---- 2. 关闭 Helium（Cookie 库被进程锁定，必须先关）----
Write-Host "`n[2/6] 关闭 Helium 浏览器…" -ForegroundColor Yellow
$procs = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*imput\Helium*' }
if ($procs) {
    $procs | Stop-Process -Force
    Start-Sleep -Seconds 3
    Write-Host '   已关闭 Helium（未保存的网页内容会丢失）'
} else {
    Write-Host '   Helium 未在运行，跳过'
}

# ---- 3. 拷贝 Cookie 库到临时目录 ----
Write-Host "`n[3/6] 拷贝 Cookie 数据库…" -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "$TmpUD\Default\Network" | Out-Null
Copy-Item "$HeliumUD\Default\Network\Cookies" "$TmpUD\Default\Network\Cookies" -Force
Copy-Item "$HeliumUD\Local State" "$TmpUD\Local State" -Force
Write-Host '   完成'

# ---- 4. 解密导出 ----
Write-Host "`n[4/6] 解密并导出 YouTube Cookie…" -ForegroundColor Yellow
& $Python $DumpScript "$TmpUD\Default\Network\Cookies" $OutCookie
if ($LASTEXITCODE -ne 0) { Pause-Exit '✗ 解密失败，把上面的报错截图发给维护者。' 1 }
$lines = (Get-Content $OutCookie | Where-Object { $_ -notmatch '^#' }).Count
if ($lines -lt 10) { Pause-Exit "✗ 导出的 Cookie 只有 $lines 条，明显异常，已停止。" 1 }

# 验证登录态 Cookie 是否存在
$authNames = @('SID', 'SAPISID', '__Secure-1PSID', 'LOGIN_INFO')
$found = @()
foreach ($n in $authNames) {
    if (Select-String -Path $OutCookie -Pattern "`t$n`t" -Quiet) { $found += $n }
}
if ($found.Count -lt 3) {
    Pause-Exit "✗ 未找到登录凭证（只找到：$($found -join ', ')）。请先在 Helium 里登录 youtube.com 再运行。" 1
}
Write-Host "   登录凭证检查通过：$($found -join ', ')"

# ---- 5. 备份旧文件 & 验证新 Cookie 真实有效 ----
Write-Host "`n[5/6] 验证新 Cookie 是否有效（用一个 YouTube 视频测试）…" -ForegroundColor Yellow
if (Test-Path $OutCookie) { Copy-Item $OutCookie $BakCookie -Force }
$Ytdlp   = 'C:\Users\Administrator\bin\yt-dlp.exe'
$NodeDir = 'C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3'
$env:PATH = "$NodeDir;$env:PATH"
$test = & $Ytdlp --no-warnings --cookies $OutCookie --js-runtimes "node:$NodeDir\node.exe" --print '%(title)s' 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' 2>&1
if ($test -match 'Sign in to confirm|ERROR') {
    # 回滚
    if (Test-Path $BakCookie) { Copy-Item $BakCookie $OutCookie -Force }
    Pause-Exit "✗ 新 Cookie 验证失败（YouTube 仍要求登录）。已恢复原 Cookie 文件。`n建议：在 Helium 里重新登录一次 youtube.com（退出再登录），然后再运行本脚本。" 1
}
Write-Host "   ✓ 验证通过：$test"

# ---- 6. 重启下载器容器 ----
Write-Host "`n[6/6] 重启下载器容器加载新 Cookie…" -ForegroundColor Yellow
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if ($wsl) {
    wsl.exe -d lxsyzd -- bash -c "docker restart ytdl-app" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host '   ✓ 容器已重启，新 Cookie 已生效'
    } else {
        Write-Host '   ⚠ 容器重启失败（可能 WSL 未启动）。下次启动容器时会自动加载新 Cookie。' -ForegroundColor Yellow
    }
} else {
    Write-Host '   ⚠ 未找到 wsl，跳过容器重启。下次启动容器时自动生效。' -ForegroundColor Yellow
}

# ---- 完成 ----
Pause-Exit @"

==== 刷新完成 ====
Cookie 文件：$OutCookie
备份文件：  $BakCookie
打开 http://localhost:8765 即可继续下载视频。
"@ 0
