// main.js — Electron main process
const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const path = require("path");
const net = require("net");
const fs = require("fs");
const { spawn, execFileSync } = require("child_process");
const treeKill = require("tree-kill");

const IS_DEV = !!process.env.ELECTRON_DEV;

let backendProcess = null;
let backendPort = null;
let mainWindow = null;
let backendStderr = ""; // capture stderr for error reporting

// ── User data directory ─────────────────────────────────────────────────────
// Store config.json, .env, etc. in a persistent location:
//   macOS:   ~/Library/Application Support/HexAgent/
//   Windows: %APPDATA%/HexAgent/
//   Linux:   ~/.config/HexAgent/
const userDataDir = app.getPath("userData");

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

// ── Helpers ──────────────────────────────────────────────────────────────────

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

// ── Backend lifecycle ────────────────────────────────────────────────────────

async function spawnBackend() {
  const port = IS_DEV ? 8000 : await findFreePort();
  backendPort = port;

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
          // Ignore — attribute may not be present or dir may not exist
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

    backendProcess = spawn(binaryPath, [], {
      cwd: userDataDir,
      stdio: "pipe",
      env: {
        ...process.env,
        PATH: newPath,
        HOST: "127.0.0.1",
        PORT: String(port),
        HEXAGENT_DATA_DIR: userDataDir,
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

// ── IPC ──────────────────────────────────────────────────────────────────────

ipcMain.on("get-backend-port", (event) => {
  event.returnValue = backendPort;
});

// ── Window ───────────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
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

  // Open DevTools with Cmd+Shift+I (mac) or Ctrl+Shift+I (win/linux)
  mainWindow.webContents.on("before-input-event", (_event, input) => {
    if (input.type === "keyDown" && input.key === "I" && input.shift && (input.meta || input.control)) {
      mainWindow.webContents.toggleDevTools();
    }
  });
}

// ── App lifecycle ────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  ensureUserData();

  try {
    await spawnBackend();
  } catch (err) {
    console.error("Failed to start backend:", err);
    dialog.showErrorBox(
      "HexAgent - Failed to Start",
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
