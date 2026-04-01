// main.js 鈥?Electron main process
const { app, BrowserWindow, Menu, dialog, ipcMain } = require("electron");
const path = require("path");
const net = require("net");
const fs = require("fs");
const { spawn, execFileSync, execSync } = require("child_process");
const treeKill = require("tree-kill");

const IS_DEV = !!process.env.ELECTRON_DEV;

// Read build-time flags written by build-all.sh into build_flags.json.
// In dev mode fall back to sensible defaults (clear data = false).
function readBuildFlags() {
  try {
    const flagsPath = IS_DEV
      ? path.join(__dirname, "build_flags.json")
      : path.join(process.resourcesPath, "build_flags.json");
    if (fs.existsSync(flagsPath)) {
      return JSON.parse(fs.readFileSync(flagsPath, "utf8"));
    }
  } catch (_) {}
  return {};
}
const BUILD_FLAGS = readBuildFlags();

let backendProcess = null;
let backendPort = null;
let mainWindow = null;
let backendStderr = ""; // capture stderr for error reporting

// 鈹€鈹€ User data directory 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
// Store config.json, .env, etc. in a persistent location:
//   macOS:   ~/Library/Application Support/HexAgent/
//   Windows: %APPDATA%/HexAgent/
//   Linux:   ~/.config/HexAgent/
const userDataDir = app.getPath("userData");

function wslLog(message) {
  const logDir = path.join(userDataDir, "logs");
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }
  const logFile = path.join(logDir, "wsl.log");
  const timestamp = new Date().toISOString().replace("T", " ").split(".")[0];
  const logEntry = `${timestamp} INFO electron: ${message}\n`;
  fs.appendFileSync(logFile, logEntry);
}

function ensureUserData() {
  // Create user data directory if it doesn't exist
  if (!fs.existsSync(userDataDir)) {
    fs.mkdirSync(userDataDir, { recursive: true });
  }

  // Seed default config.json if missing
  const configDst = path.join(userDataDir, "config.json");
  if (!fs.existsSync(configDst)) {
    // Try to copy from bundled resources, otherwise create empty
    if (!IS_DEV) {
      const bundledConfig = path.join(
        process.resourcesPath,
        "backend",
        "_internal",
        "config.json"
      );
      if (fs.existsSync(bundledConfig)) {
        fs.copyFileSync(bundledConfig, configDst);
      } else {
        fs.writeFileSync(configDst, JSON.stringify({}, null, 2));
      }
    }
  }

  // Create private skills directory if missing.
  // Public and example skills are bundled with the application and
  // read directly from the backend's _internal/skills/ directory.
  const privateSkillsDir = path.join(userDataDir, "skills", "private");
  if (!fs.existsSync(privateSkillsDir)) {
    fs.mkdirSync(privateSkillsDir, { recursive: true });
  }

  // Create uploads directory if missing
  const uploadsDir = path.join(userDataDir, "uploads");
  if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir, { recursive: true });
  }
}

// 鈹€鈹€ Helpers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on("error", reject);
  });
}

function waitForHealth(port, retries = 30, interval = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      const http = require("http");
      const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
        if (res.statusCode === 200) return resolve();
        retry();
      });
      req.on("error", retry);
      req.setTimeout(1000, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      attempts++;
      if (attempts >= retries)
        return reject(
          new Error(
            `Backend failed to start after ${retries} attempts.\n\nBackend output:\n${backendStderr.slice(-2000)}`
          )
        );
      setTimeout(check, interval);
    };
    check();
  });
}

function killPort(port) {
  try {
    if (process.platform === "win32") {
      // Find PID on port using netstat
      const output = execSync(`netstat -ano | findstr :${port}`).toString();
      const lines = output.split("\n");
      for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 5 && parts[1].includes(`:${port}`)) {
          const pid = parts[parts.length - 1];
          if (pid && pid !== "0") {
            console.log(`Killing process ${pid} on port ${port}`);
            execSync(`taskkill /F /PID ${pid}`);
          }
        }
      }
    } else {
      // For macOS/Linux
      execSync(`lsof -t -i:${port} | xargs kill -9 2>/dev/null || true`);
    }
  } catch (err) {
    // Ignore errors if port is not in use
  }
}

// 鈹€鈹€ Backend lifecycle 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

async function spawnBackend() {
  if (IS_DEV) {
    killPort(8000);
  }
  const port = IS_DEV ? 8000 : await findFreePort();
  backendPort = port;
  const appDir = IS_DEV ? __dirname : path.dirname(process.execPath);
  const wslOfflineDir = IS_DEV
    ? path.join(__dirname, "resources", "wsl")
    : path.join(process.resourcesPath, "wsl");

  if (IS_DEV) {
    const backendDir = path.join(__dirname, "..", "backend");
    backendProcess = spawn(
      "uv",
      [
        "run",
        "uvicorn",
        "hexagent_api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        String(port),
      ],
      { cwd: backendDir, stdio: "pipe" }
    );
  } else {
    let binaryName = "hexagent_api_server";
    if (process.platform === "win32") binaryName += ".exe";
    const binaryPath = path.join(
      process.resourcesPath,
      "backend",
      binaryName
    );

    // Verify binary exists
    if (!fs.existsSync(binaryPath)) {
      throw new Error(`Backend binary not found: ${binaryPath}`);
    }

    // Remove macOS quarantine flags from backend and Lima resources so
    // Gatekeeper does not block unsigned binaries (error -86) on first launch.
    if (process.platform === "darwin") {
      for (const subdir of ["backend", "lima"]) {
        const dir = path.join(process.resourcesPath, subdir);
        try {
          execFileSync("xattr", ["-dr", "com.apple.quarantine", dir]);
        } catch (_) {
          // Ignore 鈥?attribute may not be present or dir may not exist
        }
      }
    }

    // Build PATH with bundled Lima so limactl is discoverable
    const limaDir = path.join(process.resourcesPath, "lima");
    const limaBin = path.join(limaDir, "bin");
    const envPath = process.env.PATH || "";
    const newPath = fs.existsSync(limaBin)
      ? `${limaBin}${path.delimiter}${envPath}`
      : envPath;
    wslLog(
      `Backend env dirs: appDir=${appDir}, wslOfflineDir=${wslOfflineDir}`
    );

    backendProcess = spawn(binaryPath, [], {
      cwd: userDataDir,
      stdio: "pipe",
      env: {
        ...process.env,
        PATH: newPath,
        HOST: "127.0.0.1",
        PORT: String(port),
        HEXAGENT_DATA_DIR: userDataDir,
        HEXAGENT_APP_DIR: appDir,
        HEXAGENT_WSL_OFFLINE_DIR: wslOfflineDir,
        HEXAGENT_CLEAR_USER_DATA_ON_START: BUILD_FLAGS.clear_user_data_on_start ? "1" : "0",
      },
    });
  }

  backendProcess.stdout.on("data", (d) => process.stdout.write(`[backend] ${d}`));
  backendProcess.stderr.on("data", (d) => {
    const text = d.toString();
    backendStderr += text;
    // Keep last 10KB of stderr
    if (backendStderr.length > 10000) {
      backendStderr = backendStderr.slice(-10000);
    }
    process.stderr.write(`[backend] ${text}`);
  });
  backendProcess.on("exit", (code) => {
    console.log(`Backend exited with code ${code}`);
    backendProcess = null;
  });

  await waitForHealth(port);
  console.log(`Backend healthy on port ${port}`);
}

function killBackend() {
  if (backendProcess && backendProcess.pid) {
    treeKill(backendProcess.pid, "SIGTERM");
    backendProcess = null;
  }
}

function runCommand(cmd, args) {
  return new Promise((resolve) => {
    const p = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    p.stdout?.on("data", (d) => { stdout += d.toString(); });
    p.stderr?.on("data", (d) => { stderr += d.toString(); });
    p.on("error", (err) => {
      resolve({ code: 1, stdout, stderr: `${stderr}\n${err.message}`.trim() });
    });
    p.on("close", (code) => {
      resolve({ code: code ?? 1, stdout, stderr });
    });
  });
}

function tryParseJsonObject(text) {
  const raw = (text || "").trim();
  if (!raw) return null;
  const first = raw.indexOf("{");
  const last = raw.lastIndexOf("}");
  if (first < 0 || last <= first) return null;
  try {
    return JSON.parse(raw.slice(first, last + 1));
  } catch {
    return null;
  }
}

async function checkWslPrerequisitesInternal() {
  wslLog("Checking WSL prerequisites...");
  if (process.platform !== "win32") {
    wslLog("WSL prerequisites check: Unsupported platform.");
    return {
      ok: false,
      code: "UNSUPPORTED_PLATFORM",
      message: "This check is only available on Windows.",
    };
  }

  const psScript = `
$ErrorActionPreference = 'SilentlyContinue'
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1 VMMonitorModeExtensions,SecondLevelAddressTranslationExtensions,VirtualizationFirmwareEnabled
$cs = Get-CimInstance Win32_ComputerSystem | Select-Object -First 1 HypervisorPresent
$vmp = (Get-WindowsOptionalFeature -Online -FeatureName 'VirtualMachinePlatform').State
$wsl = (Get-WindowsOptionalFeature -Online -FeatureName 'Microsoft-Windows-Subsystem-Linux').State
$hypervisorAuto = $false
try {
  $line = (bcdedit /enum '{current}' | Select-String -Pattern 'hypervisorlaunchtype' -SimpleMatch | Select-Object -First 1).ToString()
  if ($line -match 'Auto') { $hypervisorAuto = $true }
} catch {}
$rebootPending = (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending') -or (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired')
$vmMonitorRaw = $cpu.VMMonitorModeExtensions
$slatRaw = $cpu.SecondLevelAddressTranslationExtensions
$virtFirmwareRaw = $cpu.VirtualizationFirmwareEnabled
$vmMonitorKnown = $null -ne $vmMonitorRaw
$slatKnown = $null -ne $slatRaw
$virtFirmwareKnown = $null -ne $virtFirmwareRaw
$vmMonitor = [bool]$vmMonitorRaw
$slat = [bool]$slatRaw
$virtFirmware = [bool]$virtFirmwareRaw
$hypervisorPresent = [bool]$cs.HypervisorPresent
# Hypervisor already running => virtualization requirements are effectively met.
$virtualizationReady = $hypervisorPresent -or ($vmMonitor -and $slat -and $virtFirmware)
$vmpEnabled = ($vmp -eq 'Enabled')
$wslFeatureEnabled = ($wsl -eq 'Enabled')
$ok = $virtualizationReady -and $vmpEnabled -and $wslFeatureEnabled -and $hypervisorAuto
$code = 'OK'
$message = 'WSL prerequisites are ready.'
if ((-not $hypervisorPresent) -and (($vmMonitorKnown -and -not $vmMonitor) -or ($slatKnown -and -not $slat))) {
  $ok = $false
  $code = 'CPU_NOT_SUPPORTED'
  $message = 'Your CPU does not meet WSL2 virtualization requirements (VM monitor mode + SLAT).'
} elseif (-not $vmpEnabled -or -not $wslFeatureEnabled) {
  $ok = $false
  $code = 'WINDOWS_FEATURES_DISABLED'
  $message = 'Required Windows features are not enabled yet. Click Retry install to enable them automatically (admin permission), then restart Windows.'
} elseif ((-not $hypervisorPresent) -and $virtFirmwareKnown -and -not $virtFirmware) {
  $ok = $false
  $code = 'BIOS_VIRT_DISABLED'
  $message = "Hardware virtualization is disabled in BIOS. Please enable Intel VT-x/AMD-V (SVM), save BIOS, then reboot Windows."
} elseif (-not $hypervisorAuto) {
  $ok = $false
  $code = 'HYPERVISOR_DISABLED'
  $message = "Hypervisor launch is disabled. Click Retry install to fix it automatically, then restart Windows."
}
[pscustomobject]@{
  ok = $ok
  code = $code
  message = $message
  virtualizationReady = $virtualizationReady
  vmMonitorModeExtensions = $vmMonitor
  slat = $slat
  virtualizationFirmwareEnabled = $virtFirmware
  hypervisorPresent = $hypervisorPresent
  virtualMachinePlatformEnabled = $vmpEnabled
  wslFeatureEnabled = $wslFeatureEnabled
  hypervisorLaunchAuto = $hypervisorAuto
  rebootPending = $rebootPending
} | ConvertTo-Json -Compress
`.trim();

  const res = await runCommand("powershell.exe", [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    psScript,
  ]);

  const parsed = tryParseJsonObject(`${res.stdout || ""}\n${res.stderr || ""}`);
  if (parsed && typeof parsed === "object") {
    wslLog(`WSL prerequisites result: ${JSON.stringify(parsed)}`);
    return parsed;
  }
  wslLog(`WSL prerequisites check FAILED: ${res.stderr || res.stdout || "unknown error"}`);
  return {
    ok: false,
    code: "CHECK_FAILED",
    message: "Failed to check WSL prerequisites.",
  };
}

// 鈹€鈹€ IPC 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

ipcMain.on("get-backend-port", (event) => {
  event.returnValue = backendPort;
});

ipcMain.handle("check-wsl-prerequisites", async () => {
  return checkWslPrerequisitesInternal();
});

ipcMain.handle("install-wsl-runtime", async () => {
  wslLog("Starting WSL runtime installation...");
  if (process.platform !== "win32") {
    wslLog("WSL runtime installation: Unsupported platform.");
    return { ok: false, message: "This action is only available on Windows." };
  }

  const precheck = await checkWslPrerequisitesInternal();
  if (precheck?.code === "BIOS_VIRT_DISABLED" || precheck?.code === "CPU_NOT_SUPPORTED") {
    wslLog(`WSL runtime installation BLOCKED by hardware/BIOS: ${precheck.code}`);
    return {
      ok: false,
      code: precheck.code,
      message: precheck.message,
      precheck,
    };
  }

  const exeDir = IS_DEV ? __dirname : path.dirname(process.execPath);
  const offlineMsiCandidates = [
    path.join(exeDir, "wsl.2.6.3.0.x64.msi"),
    path.join(exeDir, "wsl.x64.msi"),
    path.join(process.resourcesPath, "wsl", "wsl.2.6.3.0.x64.msi"),
    path.join(process.resourcesPath, "wsl", "wsl.x64.msi"),
  ];
  const offlineMsiPath = offlineMsiCandidates.find((x) => fs.existsSync(x)) || "";
  wslLog(offlineMsiPath ? `Offline WSL MSI found: ${offlineMsiPath}` : "Offline WSL MSI not found, use online install");

  const psScript = `
$ErrorActionPreference = 'Stop'
$offlineMsi = "${offlineMsiPath}"
$wslPath = Join-Path $env:SystemRoot "System32\\wsl.exe"
if (-not (Test-Path $wslPath)) {
  $wslPath = Join-Path $env:SystemRoot "Sysnative\\wsl.exe"
}
if (-not (Test-Path $wslPath)) {
  throw "wsl.exe not found under %SystemRoot%."
}
try {
  $code = 0
  if (-not [string]::IsNullOrWhiteSpace($offlineMsi) -and (Test-Path $offlineMsi)) {
    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList @("/i",$offlineMsi,"/qn","/norestart") -Verb RunAs -Wait -PassThru
    if ($null -eq $proc) { throw "Start-Process returned null process." }
    $code = $proc.ExitCode
    if ($code -ne 0 -and $code -ne 3010) {
      $proc = Start-Process -FilePath $wslPath -ArgumentList @("--install","--no-distribution") -Verb RunAs -Wait -PassThru
      if ($null -eq $proc) { throw "Start-Process returned null process." }
      $code = $proc.ExitCode
    }
  } else {
    $proc = Start-Process -FilePath $wslPath -ArgumentList @("--install","--no-distribution") -Verb RunAs -Wait -PassThru
    if ($null -eq $proc) { throw "Start-Process returned null process." }
    $code = $proc.ExitCode
  }
  exit $code
} catch {
  $msg = $_.Exception.Message
  if ([string]::IsNullOrWhiteSpace($msg)) { $msg = "Unknown Start-Process failure." }
  Write-Output ("INSTALL_ERR:" + $msg)
  exit 1
}
`.trim();

  const res = await runCommand("powershell.exe", [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    psScript,
  ]);

  wslLog(`WSL runtime installation finished with exit code ${res.code}`);

  const success = res.code === 0 || res.code === 3010;
  let rebootRequired = res.code === 3010;
  if (success) {
    const rebootProbe = await runCommand("powershell.exe", [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-Command",
      "if ((Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending') -or (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired')) { Write-Output '1' } else { Write-Output '0' }",
    ]);
    rebootRequired = rebootRequired || (rebootProbe.stdout || "").trim() === "1";

    wslLog(`WSL runtime installation SUCCESS (rebootRequired=${rebootRequired})`);
    return {
      ok: true,
      rebootRequired,
      exitCode: res.code,
      message: rebootRequired
        ? "Runtime installation completed. Please restart Windows before continuing VM setup."
        : "Runtime installation completed.",
      stdout: res.stdout,
      stderr: res.stderr,
    };
  }

  const combined = `${res.stderr || ""}\n${res.stdout || ""}`.trim();
  const installErr = (combined.match(/INSTALL_ERR:(.*)/) || [null, ""])[1]?.trim();
  const cancelled = /canceled|cancelled|拒绝|已取消|denied/i.test(combined);
  if (cancelled) {
    wslLog("WSL runtime installation CANCELLED by user");
    return { ok: false, exitCode: res.code, message: "Installation was cancelled." };
  }

  if (precheck?.code === "WINDOWS_FEATURES_DISABLED" || precheck?.code === "HYPERVISOR_DISABLED") {
    wslLog(`WSL runtime installation: Features still disabled (exit ${res.code})`);
    return {
      ok: false,
      code: precheck.code,
      exitCode: res.code,
      message:
        "WSL prerequisites are not fully enabled yet. Please allow the admin prompt, restart Windows, and retry VM setup.",
      precheck,
    };
  }

  wslLog(`WSL runtime installation FAILED: ${installErr || combined}`);
  return {
    ok: false,
    exitCode: res.code,
    message: installErr || combined || `Runtime installation failed (exit ${res.code}).`,
  };
});

ipcMain.handle("restart-windows-now", async () => {
  if (process.platform !== "win32") {
    return { ok: false, message: "This action is only available on Windows." };
  }

  // First try a normal restart request.
  let res = await runCommand("shutdown.exe", ["/r", "/t", "0"]);
  if (res.code === 0) {
    return { ok: true, message: "Windows restart has been triggered." };
  }

  // Fallback with elevation prompt when policy/permissions block direct call.
  const psScript = `
$ErrorActionPreference = 'Stop'
try {
  Start-Process -FilePath shutdown.exe -ArgumentList @('/r','/t','0') -Verb RunAs
  exit 0
} catch {
  $msg = $_.Exception.Message
  if ([string]::IsNullOrWhiteSpace($msg)) { $msg = "Unknown restart failure." }
  Write-Output ("RESTART_ERR:" + $msg)
  exit 1
}
`.trim();

  res = await runCommand("powershell.exe", [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    psScript,
  ]);

  if (res.code === 0) {
    return { ok: true, message: "Windows restart has been triggered." };
  }

  const combined = `${res.stderr || ""}\n${res.stdout || ""}`.trim();
  const restartErr = (combined.match(/RESTART_ERR:(.*)/) || [null, ""])[1]?.trim();
  const cancelled = /canceled|cancelled|鎷掔粷|宸插彇娑坾denied/i.test(combined);
  if (cancelled) {
    return { ok: false, message: "Restart was cancelled." };
  }
  return {
    ok: false,
    message: restartErr || combined || `Failed to trigger restart (exit ${res.code}).`,
  };
});

// 鈹€鈹€ Window 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

function createWindow() {
  const winIconPath = IS_DEV
    ? path.join(__dirname, "resources", "icon.ico")
    : path.join(process.resourcesPath, "app-icon.ico");

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    autoHideMenuBar: true,
    icon: fs.existsSync(winIconPath) ? winIconPath : undefined,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (IS_DEV) {
    mainWindow.loadURL("http://localhost:3000");
  } else {
    const indexPath = path.join(
      process.resourcesPath,
      "frontend",
      "index.html"
    );
    mainWindow.loadFile(indexPath);
  }

  // Hide native menu bar in desktop app window.
  mainWindow.setMenuBarVisibility(false);

  // Open DevTools with Cmd+Shift+I (mac) or Ctrl+Shift+I (win/linux)
  mainWindow.webContents.on("before-input-event", (_event, input) => {
    if (input.type === "keyDown" && input.key === "I" && input.shift && (input.meta || input.control)) {
      mainWindow.webContents.toggleDevTools();
    }
  });
}

// 鈹€鈹€ App lifecycle 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

app.whenReady().then(async () => {
  ensureUserData();

  // On Windows/Linux, remove default application menu (File/Edit/View...).
  if (process.platform !== "darwin") {
    Menu.setApplicationMenu(null);
  }

  try {
    await spawnBackend();
  } catch (err) {
    console.error("Failed to start backend:", err);
    dialog.showErrorBox(
      "UniClaw-Work - Failed to Start",
      `The backend server could not be started.\n\n${err.message}`
    );
    app.quit();
    return;
  }
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  killBackend();
});

// Explicitly handle Ctrl+C (SIGINT) on terminal
process.on("SIGINT", () => {
  console.log("Caught interrupt signal (SIGINT), killing backend...");
  killBackend();
  app.quit();
});

process.on("SIGTERM", () => {
  console.log("Caught termination signal (SIGTERM), killing backend...");
  killBackend();
  app.quit();
});




