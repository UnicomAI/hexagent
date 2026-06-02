export {};

declare global {
  interface Window {
    electronAPI?: {
      backendPort?: number;
    };
  }
}
