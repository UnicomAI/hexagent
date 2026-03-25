export {};

declare global {
  interface Window {
    electronAPI?: {
      backendPort?: number;
      isElectron?: boolean;
      platform?: string;
      installWslRuntime?: () => Promise<{
        ok: boolean;
        rebootRequired?: boolean;
        exitCode?: number;
        message?: string;
        stdout?: string;
        stderr?: string;
      }>;
    };
  }
}
