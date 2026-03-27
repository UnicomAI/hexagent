import { AlertTriangle, RefreshCw, Settings } from "lucide-react";
import { useVMSetup } from "../vmSetup";

interface RestartRequiredModalProps {
  open: boolean;
  message: string;
  onOpenSettings: () => void;
}

export default function RestartRequiredModal({
  open,
  message,
  onOpenSettings,
}: RestartRequiredModalProps) {
  const vm = useVMSetup();

  if (!open) return null;

  return (
    <div className="restart-required-overlay" role="dialog" aria-modal="true" aria-labelledby="restart-required-title">
      <div className="restart-required-modal">
        <div className="restart-required-header">
          <AlertTriangle size={18} className="restart-required-icon" />
          <h2 id="restart-required-title" className="restart-required-title">
            Restart Required
          </h2>
        </div>
        <p className="restart-required-text">
          WSL runtime installation is complete, but Windows must restart before OpenAgent can continue.
        </p>
        <p className="restart-required-text restart-required-text--strong">
          Please restart your computer now, otherwise VM/Cowork features will not work.
        </p>
        {message ? <p className="restart-required-detail">{message}</p> : null}
        <div className="restart-required-actions">
          <button className="restart-required-btn restart-required-btn--ghost" type="button" onClick={onOpenSettings}>
            <Settings size={14} />
            <span>Open Sandbox Settings</span>
          </button>
          <button className="restart-required-btn restart-required-btn--primary" type="button" onClick={vm.recheckVmEngine}>
            <RefreshCw size={14} />
            <span>I have restarted, Re-check</span>
          </button>
        </div>
      </div>
    </div>
  );
}
