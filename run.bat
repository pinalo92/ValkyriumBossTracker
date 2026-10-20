@echo off
cd /d "%~dp0"
python -m pinalo_boss_tracker
if errorlevel 1 pause
