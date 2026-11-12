@echo off
setlocal
cd /d "%~dp0"
py -3.10 -m pip install --upgrade pip
if errorlevel 1 exit /b 1
py -3.10 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1
py -3.10 packaging\build.py --archive --clean
if errorlevel 1 exit /b 1
echo.
echo Build complete. See the dist folder.
endlocal
