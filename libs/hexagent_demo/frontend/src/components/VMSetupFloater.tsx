/**
 * Floating progress indicator for background VM setup.
 *
 * Visible when any VM phase is running and the settings modal is closed.
 * Click to open settings → sandbox tab for full details.
 */

import { useTranslation } from "react-i18next";
import { Loader2, ChevronRight } from "lucide-react";
import { useVMSetup } from "../vmSetup";

interface VMSetupFloaterProps {
  settingsOpen: boolean;
  onOpenSettings: () => void;
}

export default function VMSetupFloater({ settingsOpen, onOpenSettings }: VMSetupFloaterProps) {
  const { t } = useTranslation("misc");
  const vm = useVMSetup();

  const anyRunning =
    vm.phase1 === "running" || vm.phase2 === "running" || vm.phase3 === "running";

  if (!anyRunning || settingsOpen) return null;

  // Determine current phase info for display
  let title = t("vmSetup.settingUp");
  let msg = "";
  if (vm.phase1 === "running") {
    title = t("vmSetup.installingEngine");
    msg = vm.phase1Msg;
  } else if (vm.phase2 === "running") {
    title = t("vmSetup.buildingInstance");
    msg = vm.phase2Msg;
  } else if (vm.phase3 === "running") {
    title = t("vmSetup.installingDeps");
    const runningStep = vm.provSteps.find((s) => vm.provStepStatus[s.id] === "running");
    msg = runningStep ? vm.provStepMsg[runningStep.id] || runningStep.label : "";
  }

  return (
    <div className="vm-floater" onClick={onOpenSettings} title={t("vmSetup.clickToView")}>
      <Loader2 size={16} className="vm-floater-icon spin" />
      <div className="vm-floater-text">
        <span className="vm-floater-title">{title}</span>
        {msg && <span className="vm-floater-msg">{msg}</span>}
      </div>
      <ChevronRight size={14} className="vm-floater-arrow" />
    </div>
  );
}
