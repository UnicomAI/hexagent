import { AlertTriangle, Loader2, Settings } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppContext } from "../store";

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
  const { t } = useTranslation("misc");
  const { dispatch } = useAppContext();
  const [restarting, setRestarting] = useState(false);

  const handleRestartNow = async () => {
    if (restarting) return;
    const confirmed = window.confirm(t("restartRequired.confirmRestartNow"));
    if (!confirmed) return;

    setRestarting(true);
    try {
      const api = window.electronAPI?.restartWindowsNow;
      if (!api) {
        throw new Error(t("restartRequired.restartNotSupported"));
      }
      const res = await api();
      if (!res?.ok) {
        throw new Error(res?.message || t("restartRequired.restartFailed"));
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t("restartRequired.restartFailed");
      dispatch({ type: "SHOW_NOTIFICATION", payload: { message: msg, type: "error" } });
      setRestarting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="restart-required-overlay" role="dialog" aria-modal="true" aria-labelledby="restart-required-title">
      <div className="restart-required-modal">
        <div className="restart-required-header">
          <AlertTriangle size={18} className="restart-required-icon" />
          <h2 id="restart-required-title" className="restart-required-title">
            {t("restartRequired.title")}
          </h2>
        </div>
        <p className="restart-required-text">
          {t("restartRequired.wslComplete")}
        </p>
        <p className="restart-required-text restart-required-text--strong">
          {t("restartRequired.pleaseRestart")}
        </p>
        {message ? <p className="restart-required-detail">{message}</p> : null}
        <div className="restart-required-actions">
          <button className="restart-required-btn restart-required-btn--ghost" type="button" onClick={onOpenSettings}>
            <Settings size={14} />
            <span>{t("restartRequired.openSandboxSettings")}</span>
          </button>
          <button className="restart-required-btn restart-required-btn--primary" type="button" onClick={handleRestartNow} disabled={restarting}>
            {restarting ? <Loader2 size={14} className="model-save-spinner" /> : null}
            <span>{restarting ? t("restartRequired.restarting") : t("restartRequired.restartNow")}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
