$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ElectronDir = Resolve-Path "$ScriptDir\.."
$Target = if ($args.Count -gt 0) { $args[0] } else { 'win' }
$EmbedWslPrebuilt = ($env:HEXAGENT_EMBED_WSL_PREBUILT -eq "1" -or $env:OPENAGENT_EMBED_WSL_PREBUILT -eq "1")
$PrepareOfflineWsl = ($env:HEXAGENT_PREPARE_OFFLINE_WSL -eq "1")
$SourcePrebuiltTar = Join-Path $ElectronDir "prebuilt\hexagent-prebuilt.tar"
$SourceOfflineWslDir = Join-Path $ElectronDir "resources\wsl"
$DistDir = Join-Path $ElectronDir "dist"
$DistPrebuiltTar = Join-Path $DistDir "hexagent-prebuilt.tar"
$DistOfflineRootfs = Join-Path $DistDir "ubuntu-base-24.04-amd64.tar.gz"
$ProductNameEn = "UniClawWorkSetup"
$ProductNameZh = "UniClaw安装程序"
$InstallerExeName = "$ProductNameEn.exe"
$DistReadme = Join-Path $DistDir "安装说明.txt"
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

$DistOfflineWslMsi = $null
if (Test-Path $SourceOfflineWslDir) {
    $SourceOfflineWslMsi = Get-ChildItem "$SourceOfflineWslDir\wsl*.x64.msi" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($SourceOfflineWslMsi) {
        $DistOfflineWslMsi = Join-Path $DistDir $SourceOfflineWslMsi.Name
        Copy-Item -Force $SourceOfflineWslMsi.FullName $DistOfflineWslMsi
        Write-Host "Copied offline WSL MSI to dist/: $($SourceOfflineWslMsi.Name)"
    } else {
        Write-Warning "Offline WSL MSI not found under $SourceOfflineWslDir"
    }

    $SourceOfflineRootfs = Join-Path $SourceOfflineWslDir "ubuntu-base-24.04-amd64.tar.gz"
    if (Test-Path $SourceOfflineRootfs) {
        Copy-Item -Force $SourceOfflineRootfs $DistOfflineRootfs
        Write-Host "Copied offline Ubuntu rootfs to dist/: $(Split-Path $DistOfflineRootfs -Leaf)"
    } else {
        Write-Warning "Offline Ubuntu rootfs not found: $SourceOfflineRootfs"
    }
}

# Clean up old legacy-named artifacts to avoid confusing release folders.
Get-ChildItem "$DistDir\ClawWork-*.exe", "$DistDir\ClawWork-*.exe.blockmap", "$DistDir\INSTALL-WINDOWS.txt" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

$installGuide = @"
UniClaw-Work Windows 安装说明

请将以下文件放在同一个文件夹后再安装：
1. UniClaw-Work.exe
2. hexagent-prebuilt.tar
3. wsl*.x64.msi（例如 wsl.2.6.3.0.x64.msi）
4. ubuntu-base-24.04-amd64.tar.gz

安装流程说明：
1. 双击 UniClaw-Work.exe 完成安装。
2. 首次进入「沙盒/虚拟机」时，程序会优先使用同目录离线包安装 WSL 并导入 VM。
3. 如离线导入失败，会自动回退到网络安装。
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

$CoreBundleItems = @($InstallerExePath, $DistPrebuiltTar, $DistReadme)
$OptionalBundleItems = @()
if ($DistOfflineWslMsi -and (Test-Path $DistOfflineWslMsi)) { $OptionalBundleItems += $DistOfflineWslMsi }
if (Test-Path $DistOfflineRootfs) { $OptionalBundleItems += $DistOfflineRootfs }
$BundleItems = @($CoreBundleItems + $OptionalBundleItems) | Where-Object { $_ -and (Test-Path $_) }
if ((Test-Path $InstallerExePath) -and (Test-Path $DistPrebuiltTar) -and (Test-Path $DistReadme)) {
    if (Test-Path $DistBundleZip) {
        Remove-Item -Force $DistBundleZip
    }

    $BundleCreated = $false
    $TarExe = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($TarExe) {
        $BundleEntryNames = $BundleItems | ForEach-Object { Split-Path $_ -Leaf }
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

Get-ChildItem "$DistDir\*.exe", "$DistDir\*.blockmap", "$DistDir\hexagent-prebuilt.tar", "$DistDir\wsl*.x64.msi", "$DistDir\ubuntu-base-24.04-amd64.tar.gz", $DistReadme, $DistBundleZip -ErrorAction SilentlyContinue | Format-Table -AutoSize
