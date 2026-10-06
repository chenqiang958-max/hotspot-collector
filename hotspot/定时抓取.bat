@echo off
cd /d "%~dp0"
echo 每60分钟自动抓一次，关闭窗口即停止
python scheduler.py --loop --interval 60
pause
