$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ElectronDir = Resolve-Path "$ScriptDir\.."
$Target = if ($args.Count -gt 0) { $args[0] } else { 'win' }
$EmbedWslPrebuilt = ($env:HEXAGENT_EMBED_WSL_PREBUILT -eq "1" -or $env:OPENAGENT_EMBED_WSL_PREBUILT -eq "1")
$PrepareOfflineWsl = ($env:HEXAGENT_PREPARE_OFFLINE_WSL -eq "1")
$SourcePrebuiltTar = Join-Path $ElectronDir "prebuilt\hexagent-prebuilt.tar"
$DistDir = Join-Path $ElectronDir "dist"
$DistPrebuiltTar = Join-Path $DistDir "hexagent-prebuilt.tar"
$ProductNameEn = "UniClaw-Work"
$ProductNameZh = "UniClaw-工作虾"
$InstallerExeName = "$ProductNameEn.exe"
$DistReadme = Join-Path $DistDir "${ProductNameEn}使用说明.txt"
$DistBundleZip = Join-Path $DistDir "${ProductNameZh}.zip"
$RulesFile = Join-Path $ScriptDir "WINDOWS_PACKAGING_RULES.md"

Write-Host '========================================='
Write-Host '  UniClaw Desktop - Build ('$Target')'
Write-Host '========================================='
Write-Host ''

if ($Target -eq 'win') {
    if (Test-Path $RulesFile) {
        Write-Host '[Preflight] Reading Windows packaging rules...'
        Write-Host ''
        Get-Content $RulesFile | ForEach-Object { Write-Host $_ }
        Write-Host ''
    } else {
        Write-Warning "Windows packaging rules file not found: $RulesFile"
    }
}

Write-Host '[1/3] Building frontend...'
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Write-Error "npm command not found, please make sure Node.js is installed"
}

Set-Location "$ElectronDir\..\frontend"
npm.cmd install
npm.cmd run build

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
npx.cmd electron-builder --win --x64 --publish never
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

# Clean up old legacy-named artifacts to avoid confusing release folders.
Get-ChildItem "$DistDir\ClawWork-*.exe", "$DistDir\ClawWork-*.exe.blockmap", "$DistDir\INSTALL-WINDOWS.txt" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

$installGuide = @"
UniClaw-Work 使用说明

1) 分发或安装前，请确保以下文件放在同一个文件夹：
   - $InstallerExeName
   - hexagent-prebuilt.tar
   - $(Split-Path $DistReadme -Leaf)

2) 运行 $InstallerExeName 安装桌面应用。

3) 离线加速（可选）：
   - 如果运行时可找到 hexagent-prebuilt.tar，
     VM 初始化会优先从本地镜像导入。
   - 如果找不到该文件，VM 初始化会自动回退为联网安装。

4) 打包脚本会自动生成分发压缩包：
   - ${ProductNameZh}.zip
   其中包含：$InstallerExeName、hexagent-prebuilt.tar、$(Split-Path $DistReadme -Leaf)
"@
Set-Content -Path $DistReadme -Value $installGuide -Encoding UTF8

$InstallerExePath = Join-Path $DistDir $InstallerExeName
if (-not (Test-Path $InstallerExePath)) {
    $FallbackExe = Get-ChildItem "$DistDir\*.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne 'Uninstall.exe' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($FallbackExe) {
        Write-Warning "Expected installer name not found. Renaming '$($FallbackExe.Name)' to '$InstallerExeName'."
        Move-Item -Force $FallbackExe.FullName $InstallerExePath

        $FallbackBlockmap = "$($FallbackExe.FullName).blockmap"
        $InstallerBlockmap = "$InstallerExePath.blockmap"
        if (Test-Path $FallbackBlockmap) {
            Move-Item -Force $FallbackBlockmap $InstallerBlockmap
        }
    } else {
        Write-Warning "Installer exe not found in dist directory."
    }
}

$BundleItems = @($InstallerExePath, $DistPrebuiltTar, $DistReadme) | Where-Object { $_ -and (Test-Path $_) }
if ($BundleItems.Count -eq 3) {
    if (Test-Path $DistBundleZip) {
        Remove-Item -Force $DistBundleZip
    }

    $BundleCreated = $false
    $TarExe = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($TarExe) {
        $BundleEntryNames = @($InstallerExeName, 'hexagent-prebuilt.tar', (Split-Path $DistReadme -Leaf))
        Push-Location $DistDir
        try {
            & $TarExe.Source -a -c -f $DistBundleZip @BundleEntryNames
            if ($LASTEXITCODE -eq 0 -and (Test-Path $DistBundleZip)) {
                $BundleCreated = $true
            }
        } finally {
            Pop-Location
        }
    }

    if (-not $BundleCreated) {
        Write-Warning "tar.exe zip creation failed or unavailable, falling back to Compress-Archive."
        Compress-Archive -Path $BundleItems -DestinationPath $DistBundleZip -Force
        $BundleCreated = $true
    }

    Write-Host "Created bundle: $DistBundleZip"
} else {
    Write-Warning "Bundle creation skipped. Missing files:"
    if (-not (Test-Path $InstallerExePath)) { Write-Warning " - $InstallerExePath" }
    if (-not (Test-Path $DistPrebuiltTar)) { Write-Warning " - $DistPrebuiltTar" }
    if (-not (Test-Path $DistReadme)) { Write-Warning " - $DistReadme" }
}

Get-ChildItem "$DistDir\*.exe", "$DistDir\*.blockmap", "$DistDir\hexagent-prebuilt.tar", $DistReadme, $DistBundleZip -ErrorAction SilentlyContinue | Format-Table -AutoSize
