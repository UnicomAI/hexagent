!include "LogicLib.nsh"

!macro EnsureVirtualizationFirmwareEnabled
  DetailPrint "Checking BIOS/UEFI virtualization status..."
  ; Some Windows builds may report VirtualizationFirmwareEnabled incorrectly.
  ; Treat either CPU firmware flag OR HypervisorPresent as sufficient.
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "$$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1; $$cs = Get-CimInstance Win32_ComputerSystem; if (($$cpu -and $$cpu.VirtualizationFirmwareEnabled) -or ($$cs -and $$cs.HypervisorPresent)) { exit 0 } else { exit 10 }"'
  Pop $0

  ${If} $0 != "0"
    ; Do not hard-block installation on uncertain detection.
    MessageBox MB_ICONEXCLAMATION|MB_YESNO "The installer could not confirm BIOS/UEFI virtualization from system APIs.$\r$\n$\r$\nIf virtualization is already enabled, choose Yes to continue installing WSL.$\r$\nIf it is disabled, choose No and enable Intel VT-x / AMD-V (or SVM) first.$\r$\n$\r$\nContinue installation?" IDYES +2
    Abort
  ${EndIf}
!macroend

!macro EnableWindowsFeature FeatureName
  DetailPrint "Enabling Windows feature: ${FeatureName}"
  nsExec::ExecToLog '"$SYSDIR\dism.exe" /online /enable-feature /featurename:${FeatureName} /all /norestart'
  Pop $0

  ${If} $0 == "3010"
    StrCpy $9 "1"
  ${ElseIf} $0 != "0"
    MessageBox MB_ICONSTOP|MB_OK "Failed to enable Windows feature ${FeatureName}. Exit code: $0.$\r$\n$\r$\nPlease make sure this is Windows 10/11 x64 and run the installer as administrator."
    Abort
  ${EndIf}
!macroend

!macro InstallOfflineWslRuntime
  DetailPrint "Checking whether WSL runtime is already installed..."
  nsExec::ExecToLog '"$SYSDIR\wsl.exe" --version'
  Pop $0

  ${If} $0 == "0"
    DetailPrint "WSL runtime already available, skipping offline MSI install."
    Return
  ${EndIf}

  ${IfNot} ${FileExists} "$INSTDIR\wsl.2.6.3.0.x64.msi"
    MessageBox MB_ICONSTOP|MB_OK "Offline WSL installer was not found: $INSTDIR\wsl.2.6.3.0.x64.msi"
    Abort
  ${EndIf}

  DetailPrint "Installing offline WSL runtime..."
  nsExec::ExecToLog 'msiexec.exe /i "$INSTDIR\wsl.2.6.3.0.x64.msi" /passive /norestart'
  Pop $0

  ${If} $0 == "3010"
    StrCpy $9 "1"
  ${ElseIf} $0 != "0"
    MessageBox MB_ICONSTOP|MB_OK "Offline WSL runtime installation failed. Exit code: $0.$\r$\n$\r$\nPlease check the Windows logs, or run the MSI manually and try again."
    Abort
  ${EndIf}
!macroend

!macro ConfigureWslDefaults
  ${If} $9 != "1"
    DetailPrint "Configuring WSL default version..."
    nsExec::ExecToLog '"$SYSDIR\wsl.exe" --set-default-version 2'
    Pop $0

    ${If} $0 != "0"
      DetailPrint "Skipping WSL default version setup because wsl.exe returned exit code $0"
    ${EndIf}
  ${EndIf}
!macroend

!macro customInstall
  StrCpy $9 "0"

  ; Force desktop shortcut to use bundled UniClaw-Work icon, independent of EXE icon resource.
  Delete "$DESKTOP\UniClaw-Work.lnk"
  CreateShortCut "$DESKTOP\UniClaw-Work.lnk" "$INSTDIR\UniClaw-Work.exe" "" "$INSTDIR\resources\app-icon.ico" 0

  ; Split package mode: copy VM prebuilt archive when distributed next to installer.
  IfFileExists "$EXEDIR\hexagent-prebuilt.tar" 0 +2
  CopyFiles /SILENT "$EXEDIR\hexagent-prebuilt.tar" "$INSTDIR\hexagent-prebuilt.tar"

  ; Copy offline WSL runtime assets for app-level offline install.
  IfFileExists "$EXEDIR\wsl.*.x64.msi" 0 +2
  CopyFiles /SILENT "$EXEDIR\wsl.*.x64.msi" "$INSTDIR"
  IfFileExists "$EXEDIR\ubuntu-base-24.04-amd64.tar.gz" 0 +2
  CopyFiles /SILENT "$EXEDIR\ubuntu-base-24.04-amd64.tar.gz" "$INSTDIR\ubuntu-base-24.04-amd64.tar.gz"

  ; Prepare the Windows runtime environment before the user launches the app.
  !insertmacro EnsureVirtualizationFirmwareEnabled
  !insertmacro EnableWindowsFeature "Microsoft-Windows-Subsystem-Linux"
  !insertmacro EnableWindowsFeature "VirtualMachinePlatform"
  !insertmacro InstallOfflineWslRuntime
  !insertmacro ConfigureWslDefaults

  ${If} $9 == "1"
    SetRebootFlag true
    MessageBox MB_ICONINFORMATION|MB_OK "WSL components were installed, but Windows must restart before they are fully available.$\r$\n$\r$\nUniClaw-Work has been installed. Please restart the computer before launching it."
  ${EndIf}
!macroend

!macro customUnInstall
  Delete "$INSTDIR\hexagent-prebuilt.tar"
  Delete "$INSTDIR\wsl.*.x64.msi"
  Delete "$INSTDIR\ubuntu-base-24.04-amd64.tar.gz"
  ; Unregister the WSL distribution to clean up registry and metadata
  nsExec::Exec "wsl.exe --unregister hexagent"
  ; Remove persistent data directories
  RMDir /r "$APPDATA\hexagent"
  RMDir /r "$PROFILE\.hexagent"
!macroend
