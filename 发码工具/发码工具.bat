@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   HOTSPOT KEYGEN
echo ============================================
echo.
set "PY="
where python >nul 2>&1
if %ERRORLEVEL%==0 set "PY=python"
if not defined PY (
  where py >nul 2>&1
  if %ERRORLEVEL%==0 set "PY=py -3"
)
if not defined PY if exist "%LocalAppData%\Programs\Python\Python314\python.exe" set "PY=%LocalAppData%\Programs\Python\Python314\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY (
  echo [ERROR] python.exe not found
  goto end
)
echo Using: %PY%
%PY% --version
echo.
%PY% "%~dp0keygen_app.py"
:end
echo.
pause
