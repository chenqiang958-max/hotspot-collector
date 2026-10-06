@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动发码工具...
echo 浏览器会自动打开发码界面。这个窗口别关。
python 发码工具.py
pause
