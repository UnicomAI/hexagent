!macro customInstall
  ; Force desktop shortcut to use bundled ClawWork icon, independent of EXE icon resource.
  Delete "$DESKTOP\ClawWork.lnk"
  CreateShortCut "$DESKTOP\ClawWork.lnk" "$INSTDIR\ClawWork.exe" "" "$INSTDIR\resources\app-icon.ico" 0
!macroend

!macro customUnInstall
  RMDir /r "$PROFILE\.clawwork"
!macroend
