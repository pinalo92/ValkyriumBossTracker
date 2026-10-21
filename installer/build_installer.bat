@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set ISCC=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" (
  echo Inno Setup 6 no encontrado.
  echo Instala con: winget install JRSoftware.InnoSetup
  echo O descarga: https://jrsoftware.org/isdl.php
  exit /b 1
)

if not exist "dist\Valkyrium_OneFile\ValkyriumBossTracker.exe" (
  echo Falta el EXE onefile. Ejecuta build_onefile.bat antes.
  exit /b 1
)

echo Compilando instalador con:
echo   %ISCC%
"%ISCC%" "installer\Valkyrium.iss"
if errorlevel 1 exit /b 1
echo.
echo Listo en dist\ValkyriumSetup_v*.exe
dir /b dist\ValkyriumSetup_v*.exe
