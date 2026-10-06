@echo off
chcp 65001 >nul
cd /d "%~dp0"
python 制作分享版.py
if errorlevel 1 pause
