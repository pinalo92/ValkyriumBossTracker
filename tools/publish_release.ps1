# Publica zip + update_manifest.json en GitHub Releases
# Uso (desde la raíz del repo, tras build_exe.bat):
#   pwsh tools/publish_release.ps1
#   pwsh tools/publish_release.ps1 -Version 0.2.1 -Notes "fix overlay"

param(
    [string]$Version = "",
    [string]$Notes = "Valkyrium Boss Tracker update"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $Version) {
    $Version = (Get-Content "pinalo_boss_tracker\__init__.py" | Select-String '__version__\s*=\s*"([^"]+)"').Matches.Groups[1].Value
}
if (-not $Version) { throw "No se pudo leer __version__" }

$ZipName = "ValkyriumBossTracker_v$Version.zip"
$ZipPath = Join-Path $Root "dist\$ZipName"
$ExePath = Join-Path $Root "dist\Valkyrium_OneFile\ValkyriumBossTracker.exe"
if (-not (Test-Path $ZipPath) -and -not (Test-Path $ExePath)) {
    throw "Falta zip u onefile — ejecuta build_exe.bat y/o build_onefile.bat"
}

$Repo = (gh repo view --json nameWithOwner -q .nameWithOwner)
if (-not $Repo) { throw "No hay repo GitHub (gh repo view falló)" }

$Tag = "v$Version"
$AssetUrl = "https://github.com/$Repo/releases/download/$Tag/$ZipName"
$ExeUrl = "https://github.com/$Repo/releases/download/$Tag/ValkyriumBossTracker.exe"

$Manifest = [ordered]@{
    version = $Version
    url     = $AssetUrl
    exe_url = $ExeUrl
    notes   = $Notes
} | ConvertTo-Json -Compress

$ManifestPath = Join-Path $Root "update_manifest.json"
Set-Content -Path $ManifestPath -Value $Manifest -Encoding utf8

Write-Host "Repo: $Repo"
Write-Host "Tag:  $Tag"
Write-Host "Zip:  $ZipPath"
Write-Host "Exe:  $ExePath"

$assets = @()
if (Test-Path $ZipPath) { $assets += $ZipPath }
if (Test-Path $ExePath) { $assets += $ExePath }

$exists = gh release view $Tag 2>$null
if ($LASTEXITCODE -eq 0) {
    foreach ($a in $assets) { gh release upload $Tag $a --clobber }
} else {
    gh release create $Tag @assets --title "Valkyrium v$Version" --notes $Notes
}

# Subir manifiesto al branch main (URL estable para auto-update)
git add update_manifest.json
git commit -m "chore: update_manifest.json v$Version" --allow-empty
git push origin HEAD

Write-Host ""
Write-Host "Listo. Manifest estable:"
$branch = (gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
if (-not $branch) { $branch = "master" }
Write-Host "https://raw.githubusercontent.com/$Repo/$branch/update_manifest.json"
