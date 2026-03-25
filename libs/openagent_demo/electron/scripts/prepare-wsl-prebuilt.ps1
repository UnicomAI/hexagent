$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OpenagentRoot = Resolve-Path "$ScriptDir\..\..\.."
$PrebuiltDir = Join-Path $OpenagentRoot "openagent\sandbox\vm\wsl\prebuilt"
$PrebuiltTar = Join-Path $PrebuiltDir "openagent-prebuilt.tar"
$DistroName = "openagent"

if ($env:OS -ne "Windows_NT") {
    Write-Host "Skipping WSL prebuilt export: non-Windows environment."
    exit 0
}

if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) {
    throw "wsl command not found. Install WSL first."
}

Write-Host "==> Ensuring distro '$DistroName' can start..."
& wsl -d $DistroName -- echo ok | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "WSL distro '$DistroName' is not available/runnable. Please initialize VM Instance first."
}

New-Item -ItemType Directory -Force -Path $PrebuiltDir | Out-Null
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
