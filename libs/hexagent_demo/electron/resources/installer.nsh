!macro customInstall
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
!macroend

!macro customUnInstall
  Delete "$INSTDIR\hexagent-prebuilt.tar"
  Delete "$INSTDIR\wsl.*.x64.msi"
  Delete "$INSTDIR\ubuntu-base-24.04-amd64.tar.gz"
  ; Unregister the WSL distribution to clean up registry and metadata
  nsExec::Exec "wsl.exe --unregister hexagent"
  ; Remove the persistent data directory in the user profile
  RMDir /r "$PROFILE\.hexagent"
!macroend
