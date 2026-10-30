@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.13 -m venv .venv
  if errorlevel 1 exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name PenASMR run.py
if errorlevel 1 exit /b 1
echo Output: dist\PenASMR\PenASMR.exe - distribute the entire folder.
pause
