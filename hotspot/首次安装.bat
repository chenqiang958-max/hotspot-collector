@echo off
cd /d "%~dp0"
echo 正在安装依赖（很快）...
pip install -r requirements.txt
echo.
echo 安装完成！双击"启动.bat"打开软件。
pause
