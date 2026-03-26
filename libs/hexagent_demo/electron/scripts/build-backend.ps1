$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ElectronDir = Resolve-Path "$ScriptDir\.."
$BackendDir = Resolve-Path "$ElectronDir\..\backend"

Write-Host "==> Installing PyInstaller..."
Set-Location $BackendDir
uv pip install pyinstaller

# Ensure the skills directory exists so --add-data doesn't fail
if (-not (Test-Path "$BackendDir\skills")) {
    New-Item -ItemType Directory -Path "$BackendDir\skills" | Out-Null
}

Write-Host "==> Building backend with PyInstaller..."
uv run pyinstaller `
    --name hexagent_api_server `
    --onedir `
    --noconfirm `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.loops.asyncio `
    --hidden-import uvicorn.protocols `
    --hidden-import uvicorn.protocols.http `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.protocols.http.h11_impl `
    --hidden-import uvicorn.protocols.http.httptools_impl `
    --hidden-import uvicorn.protocols.websockets `
    --hidden-import uvicorn.protocols.websockets.auto `
    --hidden-import uvicorn.protocols.websockets.wsproto_impl `
    --hidden-import uvicorn.protocols.websockets.websockets_impl `
    --hidden-import uvicorn.lifespan `
    --hidden-import uvicorn.lifespan.on `
    --hidden-import uvicorn.lifespan.off `
    --collect-submodules hexagent_api `
    --collect-submodules hexagent `
    --collect-data hexagent `
    --add-data "skills;skills" `
    hexagent_api/server.py

Write-Host "==> Copying dist to electron/backend_dist..."
if (Test-Path "$ElectronDir\backend_dist") {
    Remove-Item -Recurse -Force "$ElectronDir\backend_dist"
}
Copy-Item -Recurse "$BackendDir\dist\hexagent_api_server" "$ElectronDir\backend_dist"

Write-Host "==> Backend build complete."
