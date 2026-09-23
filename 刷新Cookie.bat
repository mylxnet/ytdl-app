@echo off
rem 双击启动器：以管理员权限不必需，直接用当前用户跑 PowerShell 脚本
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0刷新Cookie.ps1"
