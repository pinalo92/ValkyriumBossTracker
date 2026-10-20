@echo off
cd /d "%~dp0"
if not exist "portable.txt" (
  echo Pinalo Boss Tracker — modo portable> portable.txt
)
set PINALO_PORTABLE=1
python launch.py
if errorlevel 1 pause
