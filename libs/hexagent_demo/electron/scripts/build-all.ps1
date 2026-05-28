$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ElectronDir = Resolve-Path "$ScriptDir\.."
$Target = if ($args.Count -gt 0) { $args[0] } else { 'win' }
$EmbedWslPrebuilt = ($env:HEXAGENT_EMBED_WSL_PREBUILT -eq "1" -or $env:OPENAGENT_EMBED_WSL_PREBUILT -eq "1")
$PrepareOfflineWsl = ($env:HEXAGENT_PREPARE_OFFLINE_WSL -ne "0")

Write-Host '========================================='
Write-Host '  HexAgent Desktop - Build ('$Target')'
Write-Host '========================================='
Write-Host ''

Write-Host '[1/3] Building frontend...'
# Check if npm command exists
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "npm command not found, please make sure Node.js is installed"
}

# Build frontend
Set-Location "$ElectronDir\..\frontend"
npm install
npm run build

Write-Host ''
Write-Host '[2/3] Skipping electron dependencies (already installed)...'
Set-Location $ElectronDir

if ($Target -eq 'win') {
    if ($PrepareOfflineWsl) {
        Write-Host ''
        Write-Host '[2.1/3] Preparing offline WSL installer assets...'
        & "$ScriptDir\prepare-wsl-offline-assets.ps1"
    }

    if ($EmbedWslPrebuilt) {
        Write-Host ''
        Write-Host '[2.2/3] Exporting prebuilt WSL VM image for offline-ready package...'
        & "$ScriptDir\prepare-wsl-prebuilt.ps1"
    }
}

Write-Host ''
Write-Host '[2.5/3] Building backend...'
# Call PowerShell version of backend build script
& "$ScriptDir\build-backend.ps1"
Write-Host 'Backend build completed successfully!'
Set-Location $ElectronDir

Write-Host ''
Write-Host '[3/3] Packaging Windows x64 installer...'
$env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'
$env:ELECTRON_BUILDER_BINARIES_MIRROR = 'https://npmmirror.com/mirrors/electron-builder-binaries/'
npx electron-builder --win --x64 --publish never
Write-Host 'Electron packaging completed successfully!'

Write-Host ''
Write-Host '========================================='
Write-Host '  Build complete! Output in dist/'
Write-Host '========================================='

# List build artifacts
Get-ChildItem "$ElectronDir\dist\*.exe", "$ElectronDir\dist\*.blockmap" | Format-Table -AutoSize
