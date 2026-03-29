!macro customInstall
  ; Force desktop shortcut to use bundled ClawWork icon, independent of EXE icon resource.
  Delete "$DESKTOP\ClawWork.lnk"
  CreateShortCut "$DESKTOP\ClawWork.lnk" "$INSTDIR\ClawWork.exe" "" "$INSTDIR\resources\app-icon.ico" 0

  ; Split package mode: if prebuilt tar is distributed next to installer exe,
  ; copy it into install dir for runtime discovery/import.
  IfFileExists "$EXEDIR\hexagent-prebuilt.tar" 0 +2
  CopyFiles /SILENT "$EXEDIR\hexagent-prebuilt.tar" "$INSTDIR\hexagent-prebuilt.tar"
!macroend

!macro customUnInstall
  Delete "$INSTDIR\hexagent-prebuilt.tar"
  RMDir /r "$PROFILE\.hexagent"
!macroend
