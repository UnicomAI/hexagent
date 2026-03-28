// preload.js — exposes backend connection info to the renderer
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  backendPort: ipcRenderer.sendSync("get-backend-port"),
  isElectron: true,
  platform: process.platform,
  checkWslPrerequisites: () => ipcRenderer.invoke("check-wsl-prerequisites"),
  installWslRuntime: () => ipcRenderer.invoke("install-wsl-runtime"),
  restartWindowsNow: () => ipcRenderer.invoke("restart-windows-now"),
});
