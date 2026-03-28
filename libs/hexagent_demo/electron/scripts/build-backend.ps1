$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ElectronDir = Resolve-Path "$ScriptDir\.."
$BackendDir = Resolve-Path "$ElectronDir\..\backend"

Write-Host "==> Installing PyInstaller..."
Set-Location $BackendDir
$pyinstallerArgs = @(
    "--name", "clawwork_api_server",
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
    "--collect-all", "clawwork_api",
    "--collect-all", "clawwork",
    "--paths", "../../clawwork",
    "--paths", ".",
    "--add-data", "../../clawwork/sandbox/vm;sandbox/vm",
    "--add-data", "skills;skills",
    "clawwork_api/server.py"
)

# Ensure the skills directory exists so --add-data doesn't fail
if (-not (Test-Path "$BackendDir\skills")) {
    New-Item -ItemType Directory -Path "$BackendDir\skills" | Out-Null
}

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
Copy-Item -Recurse "$BackendDir\dist\clawwork_api_server" "$ElectronDir\backend_dist"

Write-Host "==> Backend build complete."
