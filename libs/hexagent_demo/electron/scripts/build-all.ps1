$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ElectronDir = Resolve-Path "$ScriptDir\.."
$Target = if ($args.Count -gt 0) { $args[0] } else { 'win' }
$EmbedWslPrebuilt = ($env:HEXAGENT_EMBED_WSL_PREBUILT -eq "1" -or $env:OPENAGENT_EMBED_WSL_PREBUILT -eq "1")
$PrepareOfflineWsl = ($env:HEXAGENT_PREPARE_OFFLINE_WSL -eq "1")
$HexagentRoot = Resolve-Path "$ElectronDir\..\.."
$SourcePrebuiltTar = Join-Path $HexagentRoot "hexagent\sandbox\vm\wsl\prebuilt\hexagent-prebuilt.tar"
$DistDir = Join-Path $ElectronDir "dist"
$DistPrebuiltTar = Join-Path $DistDir "hexagent-prebuilt.tar"
$DistReadme = Join-Path $DistDir "INSTALL-WINDOWS.txt"

Write-Host '========================================='
Write-Host '  HexAgent Desktop - Build ('$Target')'
Write-Host '========================================='
Write-Host ''

Write-Host '[1/3] Building frontend...'
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "npm command not found, please make sure Node.js is installed"
}

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

if (-not (Test-Path $DistPrebuiltTar)) {
    if (Test-Path $SourcePrebuiltTar) {
        Write-Host 'Copying split prebuilt VM image to dist/...'
        Copy-Item -Force $SourcePrebuiltTar $DistPrebuiltTar
    } else {
        Write-Warning "Prebuilt tar source not found: $SourcePrebuiltTar"
    }
}

$installGuide = @"
ClawWork Windows 安装说明

1) 分发或安装前，请确保以下文件放在同一个文件夹：
   - ClawWork-0.0.1-win-x64.exe
   - hexagent-prebuilt.tar

2) 运行 ClawWork-0.0.1-win-x64.exe 安装桌面应用。

3) 离线加速（可选）：
   - 如果运行时可找到 hexagent-prebuilt.tar，
     VM 初始化会优先从本地镜像导入。
   - 如果找不到该文件，VM 初始化会自动回退为联网安装。

4) 建议同时保留：
   - ClawWork-0.0.1-win-x64.exe.blockmap
   便于后续升级与问题排查。
"@
Set-Content -Path $DistReadme -Value $installGuide -Encoding UTF8

Get-ChildItem "$ElectronDir\dist\*.exe", "$ElectronDir\dist\*.blockmap", "$ElectronDir\dist\hexagent-prebuilt.tar", "$ElectronDir\dist\INSTALL-WINDOWS.txt" -ErrorAction SilentlyContinue | Format-Table -AutoSize
