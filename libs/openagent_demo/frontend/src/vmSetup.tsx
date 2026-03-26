/**
 * VMSetupContext — app-level provider for VM installation state.
 *
 * All phase states, SSE connections, and action functions live here so they
 * survive Settings-modal open/close cycles.  Closing the modal no longer
 * aborts in-flight installations.
 */

import {
  createContext,
  useContext,
  useRef,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  getVMStatus,
  installVMBackend,
  getVMBuildStatus,
  buildVM,
  getVMProvisionStatus,
  provisionVM,
  cancelProvision,
  getProvisionLog,
} from "./api";
import type { VMStatus, ProvisionStepDef } from "./api";
import { useAppContext } from "./store";

const WSL_MANUAL_INSTALL_CMD = "wsl --install --no-distribution";
const IS_WINDOWS = navigator.platform.toUpperCase().includes("WIN");
const RESTART_REQUIRED_PATTERN = /restart windows|restart your computer|reboot|重启|重新启动/i;

function buildWslInstallRecoveryMessage(detail?: string): string {
  const base =
    `Automatic runtime installation failed. Run this in an Administrator PowerShell: ${WSL_MANUAL_INSTALL_CMD}. ` +
    "Then restart Windows and click Retry. You can skip Local VM for now and use E2B Sandbox (chat mode).";
  const trimmed = (detail || "").trim();
  if (!trimmed) return base;
  return `${base} Details: ${trimmed}`;
}

function isRestartRequiredMessage(detail?: string | null): boolean {
  return RESTART_REQUIRED_PATTERN.test((detail || "").trim());
}

// ── Types ──

export type PhaseStatus = "checking" | "pending" | "running" | "done" | "error";

export interface VMSetupContextValue {
  vmStatus: VMStatus | null;

  phase1: PhaseStatus;
  phase1Msg: string;
  phase1Error: string;

  phase2: PhaseStatus;
  phase2Msg: string;
  phase2Error: string;

  phase3: PhaseStatus;
  phase3Error: string;
  provSteps: ProvisionStepDef[];
  provStepStatus: Record<string, PhaseStatus>;
  provStepMsg: Record<string, string>;
  provLog: string | null;

  installLima: () => void;
  recheckVmEngine: () => void;
  buildVMInstance: () => void;
  startProvision: (force?: boolean) => void;
  stopProvision: () => void;
  viewLog: () => void;
}

// ── Context ──

const VMSetupContext = createContext<VMSetupContextValue | null>(null);

export function useVMSetup(): VMSetupContextValue {
  const ctx = useContext(VMSetupContext);
  if (!ctx) throw new Error("useVMSetup must be used within VMSetupProvider");
  return ctx;
}

// ── Provider ──

export function VMSetupProvider({ children }: { children: ReactNode }) {
  const { dispatch } = useAppContext();

  // Phase 1: Lima engine
  const [vmStatus, setVmStatus] = useState<VMStatus | null>(null);
  const [phase1, setPhase1] = useState<PhaseStatus>("checking");
  const [phase1Msg, setPhase1Msg] = useState("");
  const [phase1Error, setPhase1Error] = useState("");

  // Phase 2: VM instance
  const [phase2, setPhase2] = useState<PhaseStatus>("pending");
  const [phase2Msg, setPhase2Msg] = useState("");
  const [phase2Error, setPhase2Error] = useState("");

  // Phase 3: Provisioning
  const [phase3, setPhase3] = useState<PhaseStatus>("pending");
  const [phase3Error, setPhase3Error] = useState("");
  const [provSteps, setProvSteps] = useState<ProvisionStepDef[]>([]);
  const [provStepStatus, setProvStepStatus] = useState<Record<string, PhaseStatus>>({});
  const [provStepMsg, setProvStepMsg] = useState<Record<string, string>>({});
  const [provLog, setProvLog] = useState<string | null>(null);
  const autoBootstrapTriggeredRef = useRef(false);

  // SSE abort controllers (kept alive across renders, never aborted on unmount)
  const installCtrl = useRef<AbortController | null>(null);
  const buildCtrl = useRef<AbortController | null>(null);
  const provCtrl = useRef<AbortController | null>(null);

  // ── Helpers ──

  const refreshAppVmStatus = () => {
    getVMStatus()
      .then((vs) => dispatch({ type: "SET_VM_STATUS", payload: vs }))
      .catch(() => {});
  };

  const notify = (message: string, type: "error" | "info" | "success") => {
    dispatch({ type: "SHOW_NOTIFICATION", payload: { message, type } });
  };

  const showRestartRequiredModal = (message: string) => {
    dispatch({ type: "SHOW_RESTART_REQUIRED_MODAL", payload: { message } });
  };

  const hideRestartRequiredModal = () => {
    dispatch({ type: "HIDE_RESTART_REQUIRED_MODAL" });
  };

  const doRecheckVmEngine = async () => {
    hideRestartRequiredModal();
    setPhase1("checking");
    setPhase1Msg("Re-checking runtime status...");
    setPhase1Error("");
    try {
      const vs = await getVMStatus();
      setVmStatus(vs);
      dispatch({ type: "SET_VM_STATUS", payload: vs });
      if (!vs.supported) {
        setPhase1("error");
        setPhase1Msg("");
        setPhase1Error("Not supported on this platform");
        return;
      }
      if (vs.installed) {
        hideRestartRequiredModal();
        setPhase1("done");
        setPhase1Msg("");
        setPhase1Error("");
        setPhase2("pending");
        attachBuild();
      } else if (vs.reason) {
        setPhase1("error");
        setPhase1Msg("");
        setPhase1Error(vs.reason);
        if (isRestartRequiredMessage(vs.reason)) showRestartRequiredModal(vs.reason);
      } else {
        setPhase1("pending");
        setPhase1Msg("");
        setPhase1Error("");
      }
    } catch {
      setPhase1("error");
      setPhase1Msg("");
      setPhase1Error("Could not check VM status");
    }
  };

  // ── Phase 3: Provision ──

  const attachProvision = (force = false) => {
    setPhase3("running");
    setPhase3Error("");
    setProvLog(null);
    provCtrl.current?.abort();
    provCtrl.current = provisionVM(
      {
        onStepStart(step, message) {
          setProvStepStatus((prev) => ({ ...prev, [step]: "running" }));
          setProvStepMsg((prev) => ({ ...prev, [step]: message }));
        },
        onStepProgress(step, message) {
          setProvStepMsg((prev) => ({ ...prev, [step]: message }));
        },
        onStepDone(step, message) {
          setProvStepStatus((prev) => ({ ...prev, [step]: "done" }));
          setProvStepMsg((prev) => ({ ...prev, [step]: message }));
        },
        onStepSkip(step) {
          setProvStepStatus((prev) => ({ ...prev, [step]: "done" }));
        },
        onStepError(step, message) {
          setProvStepStatus((prev) => ({ ...prev, [step]: "error" }));
          setProvStepMsg((prev) => ({ ...prev, [step]: message }));
        },
        onDone() {
          setPhase3("done");
          notify("VM fully set up — all dependencies installed", "success");
        },
        onError(message) {
          setPhase3("error");
          setPhase3Error(message);
          notify(`VM dependency installation failed: ${message}`, "error");
        },
      },
      { force },
    );
  };

  const doStartProvision = (force = false) => {
    getVMProvisionStatus()
      .then((ps) => {
        setProvSteps(ps.steps);
        const statuses: Record<string, PhaseStatus> = {};
        for (const s of ps.steps) statuses[s.id] = "pending";
        setProvStepStatus(statuses);
        attachProvision(force);
      })
      .catch(() => attachProvision(force));
  };

  // ── Phase 2: Build VM ──

  const attachBuild = () => {
    setPhase2("running");
    setPhase2Error("");
    buildCtrl.current?.abort();
    buildCtrl.current = buildVM(
      (_step, message) => setPhase2Msg(message),
      () => {
        setPhase2("done");
        setPhase2Msg("");
        refreshAppVmStatus();
        notify("VM instance is ready — cowork mode available", "success");
      },
      (message) => {
        setPhase2("error");
        setPhase2Error(message);
        notify(`VM instance setup failed: ${message}`, "error");
      },
    );
  };

  // ── Phase 1: Install Lima ──

  const doInstallLima = async () => {
    hideRestartRequiredModal();
    const inferredBackend = navigator.platform.toUpperCase().includes("WIN") ? "wsl" : "lima";
    const currentBackend = vmStatus?.backend ?? inferredBackend;
    const canAssistWslInstall =
      currentBackend === "wsl" &&
      typeof window !== "undefined" &&
      typeof window.electronAPI?.installWslRuntime === "function";

    if (canAssistWslInstall) {
      setPhase1("checking");
      setPhase1Error("");
      setPhase1Msg("Checking Windows virtualization prerequisites...");

      try {
        if (typeof window.electronAPI?.checkWslPrerequisites === "function") {
          const pre = await window.electronAPI.checkWslPrerequisites();
          const autoFixable =
            pre?.code === "WINDOWS_FEATURES_DISABLED" ||
            pre?.code === "HYPERVISOR_DISABLED";
          if (!pre.ok && !autoFixable) {
            setPhase1("error");
            setPhase1Msg("");
            setPhase1Error(pre.message || "WSL prerequisites are not ready.");
            notify(pre.message || "WSL prerequisites are not ready.", "error");
            return;
          }
          if (!pre.ok && autoFixable) {
            notify("Windows features are not enabled yet. OpenAgent will try to enable them with admin permission.", "info");
          }
          if (pre.rebootPending) {
            const msg = "Windows restart is pending. Please restart first, then continue VM setup.";
            setPhase1("error");
            setPhase1Msg("");
            setPhase1Error(msg);
            notify(msg, "info");
            showRestartRequiredModal(msg);
            return;
          }
        }

        setPhase1("running");
        setPhase1Error("");
        setPhase1Msg("Installing required Windows runtime (admin permission needed)...");

        const res = await window.electronAPI!.installWslRuntime!();
        if (!res.ok) {
          const raw = res.message || "Runtime installation failed.";
          const msg = buildWslInstallRecoveryMessage(raw);
          setPhase1("error");
          setPhase1Error(msg);
          notify("Automatic runtime installation failed. See VM Engine details for manual steps.", "error");
          return;
        }

        if (res.rebootRequired) {
          const msg = res.message || "Runtime installed. Please restart Windows before continuing VM setup.";
          setPhase1("error");
          setPhase1Msg("");
          setPhase1Error(msg);
          notify(msg, "info");
          showRestartRequiredModal(msg);
          return;
        }

        const vs = await getVMStatus();
        setVmStatus(vs);
        dispatch({ type: "SET_VM_STATUS", payload: vs });

        if (vs.installed) {
          hideRestartRequiredModal();
          setPhase1("done");
          setPhase1Msg("");
          notify("Runtime installed", "success");
          setPhase2("pending");
          attachBuild();
        } else {
          setPhase1("pending");
          setPhase1Msg("Runtime install command completed. Click Retry if needed.");
          notify("Runtime install command completed", "info");
        }
      } catch (err: unknown) {
        const raw = err instanceof Error ? err.message : String(err);
        const msg = buildWslInstallRecoveryMessage(raw);
        setPhase1("error");
        setPhase1Error(msg);
        notify("Automatic runtime installation failed. See VM Engine details for manual steps.", "error");
      }
      return;
    }

    setPhase1("running");
    setPhase1Error("");
    setPhase1Msg("Starting installation...");
    installCtrl.current?.abort();
    installCtrl.current = installVMBackend(
      (_step, message) => setPhase1Msg(message),
      () => {
        setPhase1("done");
        setPhase1Msg("");
        refreshAppVmStatus();
        notify("VM engine installed", "success");
        // Auto-chain: advance to phase 2
        setPhase2("pending");
        attachBuild();
      },
      (message) => {
        setPhase1("error");
        setPhase1Error(message);
        notify(`VM engine installation failed: ${message}`, "error");
      },
    );
  };

  // ── Phase 3 actions ──

  const doStopProvision = async () => {
    try { await cancelProvision(); } catch { /* ignore */ }
    provCtrl.current?.abort();
    setPhase3("error");
    setPhase3Error("Stopped by user");
  };

  const doViewLog = async () => {
    try {
      const log = await getProvisionLog();
      setProvLog(log);
    } catch {
      setProvLog("(Could not fetch log)");
    }
  };

  // ── Initial status check (runs once on app start) ──

  useEffect(() => {
    let cancelled = false;

    (async () => {
      // Load provision step definitions (best-effort)
      try {
        const ps = await getVMProvisionStatus();
        if (cancelled) return;
        setProvSteps(ps.steps);
        if (ps.markers?.provisioned) {
          const statuses: Record<string, PhaseStatus> = {};
          for (const s of ps.steps) statuses[s.id] = "done";
          setProvStepStatus(statuses);
        } else if (ps.markers && ps.markers.steps_done.length > 0) {
          const statuses: Record<string, PhaseStatus> = {};
          for (const s of ps.steps) {
            statuses[s.id] = ps.markers.steps_done.includes(s.id) ? "done" : "pending";
          }
          setProvStepStatus(statuses);
        }
      } catch { /* best effort */ }

      // Phase 1: VM engine (Lima / WSL)
      let limaInstalled = false;
      let vmStatusSnapshot: Awaited<ReturnType<typeof getVMStatus>> | null = null;
      try {
        const vs = await getVMStatus();
        vmStatusSnapshot = vs;
        if (cancelled) return;
        setVmStatus(vs);
        dispatch({ type: "SET_VM_STATUS", payload: vs });
      if (!vs.supported) {
        hideRestartRequiredModal();
        setPhase1("error");
        setPhase1Error("Not supported on this platform");
        return;
      }
      if (vs.installed) {
        hideRestartRequiredModal();
        setPhase1("done");
        limaInstalled = true;
      } else if (vs.reason) {
        setPhase1("error");
        setPhase1Error(vs.reason);
        if (isRestartRequiredMessage(vs.reason)) showRestartRequiredModal(vs.reason);
      } else {
        hideRestartRequiredModal();
        setPhase1("pending");
      }
      } catch {
        if (cancelled) return;
        setPhase1("error");
        setPhase1Error("Could not check VM status");
        return;
      }

      if (!limaInstalled) return;

      // Phase 2: VM instance (Lima must be Running; WSL is on-demand — Stopped is OK)
      const runningLabels = ["Running", "正在运行"];
      const wslStoppedLabels = ["Stopped", "已停止"];
      let vmReady = vmStatusSnapshot?.vm_ready === true;
      if (vmReady) {
        setPhase2("done");
      } else if (vmStatusSnapshot?.instance_error) {
        setPhase2("error");
        setPhase2Error(vmStatusSnapshot.instance_error);
      } else {
        try {
          const bs = await getVMBuildStatus();
          if (cancelled) return;
          if (bs.status === "running") {
            // Re-attach to an in-progress build
            attachBuild();
          } else if (bs.vm_state && runningLabels.includes(bs.vm_state)) {
            setPhase2("done");
            vmReady = true;
          } else if (
            vmStatusSnapshot?.backend === "wsl" &&
            bs.vm_state &&
            wslStoppedLabels.includes(bs.vm_state)
          ) {
            setPhase2("done");
            vmReady = true;
          } else if (bs.vm_state === "Stopped") {
            setPhase2("pending");
            setPhase2Msg("VM exists but is stopped");
          } else {
            setPhase2("pending");
          }
        } catch {
          if (cancelled) return;
          setPhase2("pending");
        }
      }

      if (!vmReady) return;

      // Phase 3: check provisioning
      try {
        const ps = await getVMProvisionStatus();
        if (cancelled) return;
        setProvSteps(ps.steps);
        if (ps.status === "running") {
          attachProvision();
        } else if (ps.markers?.provisioned) {
          setPhase3("done");
          const statuses: Record<string, PhaseStatus> = {};
          for (const s of ps.steps) statuses[s.id] = "done";
          setProvStepStatus(statuses);
        } else if (ps.markers && ps.markers.steps_done.length > 0) {
          setPhase3("pending");
          const statuses: Record<string, PhaseStatus> = {};
          for (const s of ps.steps) {
            statuses[s.id] = ps.markers.steps_done.includes(s.id) ? "done" : "pending";
          }
          setProvStepStatus(statuses);
        } else {
          setPhase3("pending");
        }
      } catch {
        if (cancelled) return;
        setPhase3("pending");
      }
    })();

    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Context value ──

  // Windows-only auto setup:
  // automatically trigger VM Engine + VM Instance on startup so users
  // don't need to click "Install" manually after app installation.
  useEffect(() => {
    if (!IS_WINDOWS) return;
    if (autoBootstrapTriggeredRef.current) return;
    if (!vmStatus?.supported) return;
    if (phase1 === "checking") return;
    if (phase1 === "running" || phase2 === "running") return;

    if (phase1 === "pending") {
      autoBootstrapTriggeredRef.current = true;
      notify("Detected first-time Windows setup. Starting VM runtime install automatically...", "info");
      void doInstallLima();
      return;
    }

    if (phase1 === "done" && phase2 === "pending") {
      autoBootstrapTriggeredRef.current = true;
      notify("Runtime is ready. Starting VM instance setup automatically...", "info");
      attachBuild();
    }
  }, [vmStatus, phase1, phase2]); // eslint-disable-line react-hooks/exhaustive-deps

  const value: VMSetupContextValue = {
    vmStatus,
    phase1, phase1Msg, phase1Error,
    phase2, phase2Msg, phase2Error,
    phase3, phase3Error,
    provSteps, provStepStatus, provStepMsg, provLog,
    installLima: doInstallLima,
    recheckVmEngine: doRecheckVmEngine,
    buildVMInstance: attachBuild,
    startProvision: doStartProvision,
    stopProvision: doStopProvision,
    viewLog: doViewLog,
  };

  return (
    <VMSetupContext.Provider value={value}>
      {children}
    </VMSetupContext.Provider>
  );
}
