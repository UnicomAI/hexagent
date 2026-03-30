!macro customInstall
  ; Force desktop shortcut to use bundled UniClaw-Work icon, independent of EXE icon resource.
  Delete "$DESKTOP\UniClaw-Work.lnk"
  CreateShortCut "$DESKTOP\UniClaw-Work.lnk" "$INSTDIR\UniClaw-Work.exe" "" "$INSTDIR\resources\app-icon.ico" 0

  ; Split package mode: if prebuilt tar is distributed next to installer exe,
  ; copy it into install dir for runtime discovery/import.
  IfFileExists "$EXEDIR\hexagent-prebuilt.tar" 0 +2
  CopyFiles /SILENT "$EXEDIR\hexagent-prebuilt.tar" "$INSTDIR\hexagent-prebuilt.tar"
!macroend

!macro customUnInstall
  Delete "$INSTDIR\hexagent-prebuilt.tar"
  ; Unregister the WSL distribution to clean up registry and metadata
  nsExec::Exec "wsl.exe --unregister hexagent"
  ; Remove the persistent data directory in the user profile
  RMDir /r "$PROFILE\.hexagent"
!macroend
