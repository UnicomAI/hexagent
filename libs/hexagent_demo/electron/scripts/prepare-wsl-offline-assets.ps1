$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ElectronDir = Resolve-Path "$ScriptDir\.."
$OfflineDir = Join-Path $ElectronDir "resources\wsl"

$WslMsiName = "wsl.2.6.3.0.x64.msi"
$UbuntuRootfsName = "ubuntu-base-24.04-amd64.tar.gz"
$UseCnMirrors = ($env:CLAWWORK_USE_CN_MIRRORS -ne "0")

if ($env:OS -ne "Windows_NT") {
    Write-Host "Skipping offline WSL asset preparation: non-Windows environment."
    exit 0
}

New-Item -ItemType Directory -Force -Path $OfflineDir | Out-Null

function Ensure-DownloadedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Urls,
        [long]$MinBytes = 1024,
        [long]$MaxBytes = 0,
        [string]$Kind = "generic"
    )

    $target = Join-Path $OfflineDir $Name
    function Test-AssetValidity {
        param(
            [Parameter(Mandatory = $true)][string]$Path,
            [Parameter(Mandatory = $true)][string]$AssetKind,
            [long]$AssetMinBytes = 1024,
            [long]$AssetMaxBytes = 0
        )
        if (-not (Test-Path $Path)) { return $false }
        $item = Get-Item $Path -ErrorAction SilentlyContinue
        if (-not $item) { return $false }
        if ($item.Length -lt $AssetMinBytes) { return $false }
        if ($AssetMaxBytes -gt 0 -and $item.Length -gt $AssetMaxBytes) { return $false }

        try {
            $fs = [System.IO.File]::OpenRead($Path)
            try {
                $header = New-Object byte[] 4
                [void]$fs.Read($header, 0, 4)
            } finally {
                $fs.Dispose()
            }

            if ($AssetKind -eq "msi") {
                # MSI is a CFB container: D0 CF 11 E0
                return ($header[0] -eq 0xD0 -and $header[1] -eq 0xCF -and $header[2] -eq 0x11 -and $header[3] -eq 0xE0)
            }
            if ($AssetKind -eq "tar_gz") {
                # Gzip magic: 1F 8B
                return ($header[0] -eq 0x1F -and $header[1] -eq 0x8B)
            }
            return $true
        } catch {
            return $false
        }
    }

    if (Test-Path $target) {
        if (Test-AssetValidity -Path $target -AssetKind $Kind -AssetMinBytes $MinBytes -AssetMaxBytes $MaxBytes) {
            $sizeMb = [math]::Round(((Get-Item $target).Length / 1MB), 1)
            Write-Host "==> Reusing cached offline asset: $Name (${sizeMb} MB)"
            return
        }
        Write-Host "==> Cached file is invalid, redownloading: $Name"
        Remove-Item -Force $target
    }

    $lastError = $null
    foreach ($url in $Urls) {
        if (-not $url) { continue }
        Write-Host "==> Downloading $Name from $url ..."
        try {
            Invoke-WebRequest -Uri $url -OutFile $target
            if (Test-AssetValidity -Path $target -AssetKind $Kind -AssetMinBytes $MinBytes -AssetMaxBytes $MaxBytes) {
                $sizeMb = [math]::Round(((Get-Item $target).Length / 1MB), 1)
                Write-Host "==> Ready: $Name (${sizeMb} MB)"
                return
            }
            Write-Host "==> Downloaded file failed validation, trying next mirror..."
            if (Test-Path $target) { Remove-Item -Force $target }
        } catch {
            $lastError = $_
            Write-Host "==> Download failed from $url, trying next mirror..."
            if (Test-Path $target) { Remove-Item -Force $target }
        }
    }

    if (-not (Test-Path $target)) {
        if ($lastError) {
            throw $lastError
        }
        throw "All download URLs failed for $Name"
    }
}

$wslMsiUrls = @()
$rootfsUrls = @()

if ($env:CLAWWORK_WSL_MSI_URL) {
    $wslMsiUrls += $env:CLAWWORK_WSL_MSI_URL
}
if ($env:CLAWWORK_UBUNTU_ROOTFS_URL) {
    $rootfsUrls += $env:CLAWWORK_UBUNTU_ROOTFS_URL
}

if ($UseCnMirrors) {
    # Optional acceleration mirror for GitHub download.
    $wslMsiUrls += "https://gh.llkk.cc/https://github.com/microsoft/WSL/releases/download/2.6.3/$WslMsiName"
    # Smaller Ubuntu base rootfs (~28MB) for offline package size control.
    $rootfsUrls += "https://mirrors.ustc.edu.cn/ubuntu-cdimage/ubuntu-base/releases/24.04/release/ubuntu-base-24.04.4-base-amd64.tar.gz"
    $rootfsUrls += "https://mirror.sjtu.edu.cn/ubuntu-cdimage/ubuntu-base/releases/24.04/release/ubuntu-base-24.04.4-base-amd64.tar.gz"
}

# Official fallback URLs.
$wslMsiUrls += "https://github.com/microsoft/WSL/releases/download/2.6.3/$WslMsiName"
$rootfsUrls += "https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/ubuntu-base-24.04.4-base-amd64.tar.gz"

Ensure-DownloadedFile -Name $WslMsiName -Urls $wslMsiUrls -Kind "msi" -MinBytes 10485760
Ensure-DownloadedFile -Name $UbuntuRootfsName -Urls $rootfsUrls -Kind "tar_gz" -MinBytes 20971520 -MaxBytes 83886080

Write-Host "==> Offline WSL assets are ready in: $OfflineDir"
