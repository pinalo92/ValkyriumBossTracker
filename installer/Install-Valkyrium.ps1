# Instalador PowerShell (sin Inno): copia EXE, acceso directo, desinstalador
# Ejecutar: clic derecho → Ejecutar con PowerShell   (o: pwsh -File Install-Valkyrium.ps1)

param(
    [string]$SourceExe = ""
)

$ErrorActionPreference = "Stop"
$AppName = "Valkyrium Boss Tracker"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\ValkyriumBossTracker"
$ExeName = "ValkyriumBossTracker.exe"

if (-not $SourceExe) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Path
    $cand = @(
        (Join-Path $here "..\dist\Valkyrium_OneFile\$ExeName"),
        (Join-Path $here $ExeName),
        (Join-Path (Get-Location) $ExeName)
    )
    foreach ($c in $cand) {
        if (Test-Path $c) { $SourceExe = (Resolve-Path $c).Path; break }
    }
}
if (-not $SourceExe -or -not (Test-Path $SourceExe)) {
    throw "No encuentro ValkyriumBossTracker.exe. Pasalo con -SourceExe o ponlo junto a este script."
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Force $SourceExe (Join-Path $InstallDir $ExeName)

$Wsh = New-Object -ComObject WScript.Shell
$desk = [Environment]::GetFolderPath("Desktop")
$sc = $Wsh.CreateShortcut((Join-Path $desk "$AppName.lnk"))
$sc.TargetPath = Join-Path $InstallDir $ExeName
$sc.WorkingDirectory = $InstallDir
$sc.Description = $AppName
$sc.Save()

$start = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Valkyrium"
New-Item -ItemType Directory -Force -Path $start | Out-Null
$sc2 = $Wsh.CreateShortcut((Join-Path $start "$AppName.lnk"))
$sc2.TargetPath = Join-Path $InstallDir $ExeName
$sc2.WorkingDirectory = $InstallDir
$sc2.Save()

$uninst = Join-Path $InstallDir "Uninstall-Valkyrium.ps1"
@"
`$dir = '$InstallDir'
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('Desktop')) '$AppName.lnk')
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path `$env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Valkyrium')
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `$dir
Write-Host 'Valkyrium desinstalado.'
"@ | Set-Content -Path $uninst -Encoding UTF8

$sc3 = $Wsh.CreateShortcut((Join-Path $start "Desinstalar Valkyrium.lnk"))
$sc3.TargetPath = "powershell.exe"
$sc3.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$uninst`""
$sc3.Save()

Write-Host "Instalado en: $InstallDir"
Write-Host "Icono en escritorio creado."
Start-Process (Join-Path $InstallDir $ExeName)
