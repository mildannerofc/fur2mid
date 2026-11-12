@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed. Make sure Python 3.10+ is installed.
  pause
  exit /b 1
)
py -3 main.py
if errorlevel 1 pause
endlocal
