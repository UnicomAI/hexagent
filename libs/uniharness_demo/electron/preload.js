// preload.js — exposes backend connection info to the renderer
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  backendPort: ipcRenderer.sendSync("get-backend-port"),
  isElectron: true,
  platform: process.platform,
});
