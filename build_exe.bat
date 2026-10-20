@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Preferir Python con PySide6
set PY=
where py >nul 2>&1 && set PY=py -3
if exist "C:\Python314\python.exe" set PY=C:\Python314\python.exe
if "%PY%"=="" set PY=python

echo === Dependencias ===
%PY% -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 (
  echo ERROR: pip install
  pause
  exit /b 1
)

rem Evitar conflicto pathlib backport con PyInstaller en Python 3.14
%PY% -m pip uninstall -y pathlib >nul 2>&1

echo === PyInstaller (puede tardar unos minutos) ===
%PY% -m PyInstaller --noconfirm --clean PinaloBossTracker.spec
if errorlevel 1 (
  echo ERROR: PyInstaller
  pause
  exit /b 1
)

rem Paquete portable listo para copiar a USB / otra carpeta
set OUT=dist\PinaloBossTracker_Portable
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"
xcopy /e /i /y "dist\PinaloBossTracker\*" "%OUT%\" >nul

(
  echo Pinalo Boss Tracker — modo portable
  echo Datos, DB y cache live van en la carpeta .\data junto al exe.
  echo No hace falta instalar Python.
) > "%OUT%\portable.txt"

%PY% -c "from pinalo_boss_tracker import __version__; open(r'%OUT%\app_version.txt','w',encoding='utf-8').write(__version__)"

if not exist "%OUT%\data" mkdir "%OUT%\data"

(
  echo @echo off
  echo cd /d "%%~dp0"
  echo set PINALO_PORTABLE=1
  echo start "" "PinaloBossTracker.exe"
) > "%OUT%\Iniciar_Portable.bat"

rem Changelog + zip de distribución
copy /y "CHANGELOG.md" "%OUT%\CHANGELOG.md" >nul
set ZIP=dist\ValkyriumBossTracker_v0.2.0.zip
if exist "%ZIP%" del /f /q "%ZIP%"
%PY% -c "import shutil; from pathlib import Path; shutil.make_archive(str(Path(r'dist')/'ValkyriumBossTracker_v0.2.0'), 'zip', r'dist', 'PinaloBossTracker_Portable')"

echo.
echo Listo.
echo   EXE:      dist\PinaloBossTracker\PinaloBossTracker.exe
echo   Portable: %OUT%\Iniciar_Portable.bat
echo   Zip:      %ZIP%
echo.
echo Copia la carpeta PinaloBossTracker_Portable donde quieras y ejecuta Iniciar_Portable.bat
pause
