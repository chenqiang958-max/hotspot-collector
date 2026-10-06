@echo off
cd /d "%~dp0"
echo 正在启动热点收集器...
echo 会用一个独立浏览器打开操作页面，登录也在这个浏览器里进行
echo 本窗口请勿关闭（关了软件就停了）
echo.
python start.py
pause
