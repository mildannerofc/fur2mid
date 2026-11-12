@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1
py -3 -m PyInstaller --noconfirm --clean --windowed --name fur2mid --collect-all tkinterdnd2 main.py
if errorlevel 1 exit /b 1
echo Build complete: dist\fur2mid\fur2mid.exe
endlocal
