function computeApiBase(): string {
  if (typeof window !== "undefined" && window.electronAPI?.backendPort) {
    return `http://localhost:${window.electronAPI.backendPort}`;
  }
  return "";
}

export function getApiBase(): string {
  return computeApiBase();
}

export function withApiBase(path: string): string {
  if (!path.startsWith("/")) return path;
  return `${computeApiBase()}${path}`;
}
