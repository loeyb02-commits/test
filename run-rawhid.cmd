@echo off
cd /d "%~dp0"
if exist dist\PenASMR\PenASMR.exe (
  start "" /wait "dist\PenASMR\PenASMR.exe" --backend rawhid
) else (
  call run.cmd --backend rawhid
)
