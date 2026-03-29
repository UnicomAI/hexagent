!macro customInstall
  ; Force desktop shortcut to use bundled ClawWork icon, independent of EXE icon resource.
  Delete "$DESKTOP\ClawWork.lnk"
  CreateShortCut "$DESKTOP\ClawWork.lnk" "$INSTDIR\ClawWork.exe" "" "$INSTDIR\resources\app-icon.ico" 0
!macroend

!macro customUnInstall
  ; Unregister the WSL distribution to clean up registry and metadata
  nsExec::Exec "wsl.exe --unregister hexagent"
  ; Remove the persistent data directory in the user profile
  RMDir /r "$PROFILE\.hexagent"
!macroend
