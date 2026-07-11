!macro NSIS_HOOK_POSTUNINSTALL
  SetShellVarContext current
  RMDir /r "$LOCALAPPDATA\com.craftag.studio"
!macroend
