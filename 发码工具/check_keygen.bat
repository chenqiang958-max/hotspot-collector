@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   HOTSPOT KEYGEN SELF-CHECK
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

if not defined PY (
  echo [FAIL] python.exe not found
  echo [FAIL] python.exe not found > "%~dp0check_keygen_report.txt"
  goto :end
)

echo Using: %PY%
%PY% --version
echo.
%PY% "%~dp0diag_keygen.py"

:end
echo.
echo Report: check_keygen_report.txt
pause
