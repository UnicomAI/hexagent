param(
    [switch]$CurrentWindow
)

$ErrorActionPreference = "Stop"

function Test-CommandExists {
    param([Parameter(Mandatory = $true)][string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ScriptDir "backend"
$FrontendDir = Join-Path $ScriptDir "frontend"

if (-not (Test-Path $BackendDir)) {
    throw "Backend directory not found: $BackendDir"
}
if (-not (Test-Path $FrontendDir)) {
    throw "Frontend directory not found: $FrontendDir"
}

if (-not (Test-CommandExists -Name "uv")) {
    throw "Command 'uv' not found. Please install uv first."
}
if (-not (Test-CommandExists -Name "npm")) {
    throw "Command 'npm' not found. Please install Node.js/npm first."
}

$backendCmd = @"
Set-Location '$BackendDir'
if (-not (Test-Path '.venv')) {
    Write-Host '[backend] .venv not found, running uv sync...' -ForegroundColor Yellow
    uv sync
}
Write-Host '[backend] starting on http://127.0.0.1:8000' -ForegroundColor Cyan
uv run uvicorn openagent_api.main:app --host 127.0.0.1 --port 8000
"@

$frontendCmd = @"
Set-Location '$FrontendDir'
if (-not (Test-Path 'node_modules')) {
    Write-Host '[frontend] node_modules not found, running npm install...' -ForegroundColor Yellow
    npm install
}
Write-Host '[frontend] starting on http://localhost:3000' -ForegroundColor Cyan
npm run dev
"@

if ($CurrentWindow) {
    Write-Host "Starting backend in a background job (CurrentWindow mode)..." -ForegroundColor Green
    Start-Job -Name "openagent-backend" -ScriptBlock {
        param($cmd)
        powershell -NoProfile -NoExit -Command $cmd
    } -ArgumentList $backendCmd | Out-Null

    Write-Host "Starting frontend in current window..." -ForegroundColor Green
    Invoke-Expression $frontendCmd
    exit 0
}

Write-Host "Launching backend and frontend in new PowerShell windows..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCmd | Out-Null
Start-Process powershell -ArgumentList "-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCmd | Out-Null

Write-Host ""
Write-Host "OpenAgent dev services launched." -ForegroundColor Green
Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend : http://127.0.0.1:8000/health"
Write-Host ""
Write-Host "Tip: run with -CurrentWindow if you want frontend in the current shell."
