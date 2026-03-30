$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ElectronDir = Resolve-Path "$ScriptDir\.."
$PrebuiltDir = Join-Path $ElectronDir "prebuilt"
$PrebuiltTar = Join-Path $PrebuiltDir "hexagent-prebuilt.tar"
$LegacyPrebuiltTar = Join-Path $PrebuiltDir "openagent-prebuilt.tar"
$DistroName = if ($env:HEXAGENT_WSL_DISTRO) { $env:HEXAGENT_WSL_DISTRO } else { "hexagent" }
$ForceRebuild = ($env:HEXAGENT_FORCE_REBUILD_WSL_PREBUILT -eq "1")

if ($env:OS -ne "Windows_NT") {
    Write-Host "Skipping WSL prebuilt export: non-Windows environment."
    exit 0
}

New-Item -ItemType Directory -Force -Path $PrebuiltDir | Out-Null

if ((-not (Test-Path $PrebuiltTar)) -and (Test-Path $LegacyPrebuiltTar)) {
    Write-Host "==> Found legacy prebuilt tar name, renaming to hexagent-prebuilt.tar ..."
    Move-Item -Force $LegacyPrebuiltTar $PrebuiltTar
}

if ((Test-Path $PrebuiltTar) -and (-not $ForceRebuild)) {
    $sizeMb = [math]::Round(((Get-Item $PrebuiltTar).Length / 1MB), 1)
    Write-Host "==> Reusing existing WSL prebuilt image: $PrebuiltTar (${sizeMb} MB)"
    exit 0
}

if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) {
    throw "wsl command not found. Install WSL first."
}

Write-Host "==> Ensuring distro '$DistroName' can start..."
& wsl -d $DistroName -- echo ok | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "WSL distro '$DistroName' is not available/runnable. Please initialize VM Instance first, or provide an existing hexagent-prebuilt.tar."
}

if (Test-Path $PrebuiltTar) {
    Remove-Item -Force $PrebuiltTar
}

Write-Host "==> Exporting '$DistroName' to $PrebuiltTar (this can take several minutes)..."
wsl --export $DistroName $PrebuiltTar

if (-not (Test-Path $PrebuiltTar)) {
    throw "WSL export completed but output tar was not found: $PrebuiltTar"
}

$sizeMb = [math]::Round(((Get-Item $PrebuiltTar).Length / 1MB), 1)
Write-Host "==> WSL prebuilt image ready: $PrebuiltTar (${sizeMb} MB)"
