# YtCookieExporter 单文件 exe 打包脚本
# ---------------------------------------------------------------------------
# 本文件是**长期保留的打包素材**，不要随构建产物一起删除。
#
# 用法（在仓库根目录或任意位置均可）：
#   powershell -ExecutionPolicy Bypass -File tools\cookie-exporter\build\build.ps1
#
# 前置条件：
#   tools\cookie-exporter\.venv 已创建，并装好 yt-dlp 与 pyinstaller。
#   首次准备命令（国内源）：
#     python -m venv .venv
#     .venv\Scripts\python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple yt-dlp pyinstaller
#
# 产物：tools\cookie-exporter\build\dist\YtCookieExporter.exe（单文件，目标机器无需装 Python）
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot          # tools/cookie-exporter
$pyi  = Join-Path $root ".venv\Scripts\pyinstaller.exe"

if (-not (Test-Path $pyi)) {
    throw "未找到 PyInstaller：$pyi`n请先创建 .venv 并安装依赖（见本脚本头部注释）。"
}

$icon = Join-Path $root "assets\icon.ico"
if (-not (Test-Path $icon)) {
    throw "未找到图标：$icon"
}

Write-Host "开始打包 YtCookieExporter…"

& $pyi `
    --onefile `
    --windowed `
    --name YtCookieExporter `
    --icon $icon `
    --add-data "$icon;assets" `
    --paths (Join-Path $root "src") `
    --specpath (Join-Path $root "build") `
    --workpath (Join-Path $root "build\_pyi") `
    --distpath (Join-Path $root "build\dist") `
    --clean --noconfirm `
    (Join-Path $root "src\main.py")

$exe = Join-Path $root "build\dist\YtCookieExporter.exe"
if (-not (Test-Path $exe)) {
    throw "打包结束但未生成 exe：$exe"
}

$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "打包完成：$exe ($size MB)"