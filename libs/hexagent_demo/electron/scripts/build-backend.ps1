$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ElectronDir = Resolve-Path "$ScriptDir\.."
$BackendDir = Resolve-Path "$ElectronDir\..\backend"
$ConfigSource = Join-Path $BackendDir "config.json"
$TempConfigCreated = $false

if (-not (Test-Path $ConfigSource)) {
    # Keep packaging resilient in CI/local envs where config.json is not present.
    # Electron will still seed userData/config.json from this bundled default.
    $ConfigSource = Join-Path $BackendDir ".packaged-default-config.json"
    Set-Content -Path $ConfigSource -Value "{}" -Encoding UTF8
    $TempConfigCreated = $true
}

Write-Host "==> Installing PyInstaller..."
Set-Location $BackendDir
$pyinstallerArgs = @(
    "--name", "hexagent_api_server",
    "--onedir",
    "--noconfirm",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.loops.asyncio",
    "--hidden-import", "uvicorn.protocols",
    "--hidden-import", "uvicorn.protocols.http",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.http.h11_impl",
    "--hidden-import", "uvicorn.protocols.http.httptools_impl",
    "--hidden-import", "uvicorn.protocols.websockets",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.protocols.websockets.wsproto_impl",
    "--hidden-import", "uvicorn.protocols.websockets.websockets_impl",
    "--hidden-import", "uvicorn.lifespan",
    "--hidden-import", "uvicorn.lifespan.on",
    "--hidden-import", "uvicorn.lifespan.off",
    "--collect-submodules", "hexagent_api",
    "--collect-submodules", "hexagent",
    "--collect-data", "hexagent",
    "--add-data", "../../hexagent/sandbox/vm/setup;sandbox/vm/setup",
    "--add-data", "../../hexagent/sandbox/vm/setup_lite;sandbox/vm/setup_lite",
    "--add-data", "../../hexagent/sandbox/vm/lima;sandbox/vm/lima",
    "--add-data", "skills;skills",
    "--add-data", "$ConfigSource;.",
    "hexagent_api/server.py"
)

# Ensure the skills directory exists so --add-data doesn't fail
if (-not (Test-Path "$BackendDir\skills")) {
    New-Item -ItemType Directory -Path "$BackendDir\skills" | Out-Null
}

try {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv pip install pyinstaller
        Write-Host "==> Building backend with PyInstaller (uv)..."
        uv run pyinstaller @pyinstallerArgs
    } else {
        $venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            throw "uv not found and backend venv python missing: $venvPython"
        }
        Write-Host "==> uv not found, using backend venv python fallback..."
        & $venvPython -m PyInstaller @pyinstallerArgs
    }

    Write-Host "==> Copying dist to electron/backend_dist..."
    if (Test-Path "$ElectronDir\backend_dist") {
        Remove-Item -Recurse -Force "$ElectronDir\backend_dist"
    }
    Copy-Item -Recurse "$BackendDir\dist\hexagent_api_server" "$ElectronDir\backend_dist"

    # Safety net: never ship huge prebuilt tar inside main installer payload.
    Get-ChildItem -Path "$ElectronDir\backend_dist" -Recurse -File -Filter "hexagent-prebuilt.tar" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "==> Backend build complete."
}
finally {
    if ($TempConfigCreated -and (Test-Path $ConfigSource)) {
        Remove-Item -Force $ConfigSource
    }
}
