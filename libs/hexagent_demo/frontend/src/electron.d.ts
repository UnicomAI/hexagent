export {};

declare global {
  interface Window {
    electronAPI?: {
      backendPort?: number;
      isElectron?: boolean;
      platform?: string;
      checkWslPrerequisites?: () => Promise<{
        ok: boolean;
        code?: string;
        message?: string;
        virtualizationReady?: boolean;
        vmMonitorModeExtensions?: boolean;
        slat?: boolean;
        virtualizationFirmwareEnabled?: boolean;
        virtualMachinePlatformEnabled?: boolean;
        wslFeatureEnabled?: boolean;
        hypervisorLaunchAuto?: boolean;
        rebootPending?: boolean;
      }>;
      installWslRuntime?: () => Promise<{
        ok: boolean;
        code?: string;
        rebootRequired?: boolean;
        exitCode?: number;
        message?: string;
        stdout?: string;
        stderr?: string;
      }>;
      restartWindowsNow?: () => Promise<{
        ok: boolean;
        message?: string;
      }>;
    };
  }
}
