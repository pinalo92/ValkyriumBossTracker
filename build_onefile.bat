@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set PY=
where py >nul 2>&1 && set PY=py -3
if exist "C:\Python314\python.exe" set PY=C:\Python314\python.exe
if "%PY%"=="" set PY=python

echo === Dependencias ===
%PY% -m pip install -q -r requirements.txt pyinstaller
%PY% -m pip uninstall -y pathlib >nul 2>&1

echo === PyInstaller ONEFILE (puede tardar) ===
%PY% -m PyInstaller --noconfirm --clean PinaloBossTracker_onefile.spec
if errorlevel 1 (
  echo ERROR: PyInstaller onefile
  pause
  exit /b 1
)

set OUT=dist\Valkyrium_OneFile
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"
copy /y "dist\ValkyriumBossTracker.exe" "%OUT%\ValkyriumBossTracker.exe" >nul
(
  echo Valkyrium Boss Tracker — EXE portable ^(un solo archivo^)
  echo Al arrancar crea .\data junto al exe ^(ajustes, DB, cache^).
) > "%OUT%\LEEME.txt"

echo.
echo Listo: %OUT%\ValkyriumBossTracker.exe
dir "%OUT%\ValkyriumBossTracker.exe"
pause
