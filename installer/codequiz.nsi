; Code Quiz installer for Windows. Build it with: python installer/build.py
;
; Installs for the current user only (no administrator rights needed) into
; %LOCALAPPDATA%\Programs\Code Quiz, with its own copy of Python. Modules the
; user adds and their settings live in %APPDATA%\CodeQuiz, so updates and
; reinstalls keep them.

Target amd64-unicode
ManifestDPIAware true
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32

!ifndef VERSION
  !error "Define VERSION (installer/build.py does this)"
!endif
!ifndef STAGE
  !error "Define STAGE, the folder build.py fills"
!endif
!ifndef OUTFILE
  !define OUTFILE "CodeQuiz-Setup-${VERSION}.exe"
!endif

!define APP "Code Quiz"
!define APPKEY "Software\CodeQuiz"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\CodeQuiz"
!define UNINSTALLER "Uninstall Code Quiz.exe"
!define PYTHONW '"$INSTDIR\python\pythonw.exe" -I "$INSTDIR\quiz.py"'

Name "${APP}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\Code Quiz"
InstallDirRegKey HKCU "${APPKEY}" "InstallDir"
BrandingText "${APP} ${VERSION}"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!define MUI_ICON "${STAGE}\icon.ico"
!define MUI_UNICON "${STAGE}\icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${__FILEDIR__}\wizard.bmp"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "Code Quiz runs on this computer and opens in its own window. It comes with the built-in subjects; add more from .quiz module files or from your GitHub library on the Modules page.$\r$\n$\r$\nNo administrator rights are needed, and Code Quiz brings its own copy of Python, so a Python you may already have is left alone.$\r$\n$\r$\nClick Next to continue."
!define MUI_DIRECTORYPAGE_TEXT_TOP "Choose a new or empty folder, or the folder of an earlier Code Quiz to update it. Your added modules and settings are kept in $APPDATA\CodeQuiz either way."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Open Code Quiz now"
!define MUI_FINISHPAGE_RUN_FUNCTION OpenApp

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

VIProductVersion "${VERSION}.0"
VIFileVersion "${VERSION}.0"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductName" "${APP}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileDescription" "${APP} setup"
!pragma warning disable 9100 ; no LegalCopyright key

; A running Code Quiz keeps its files open; ask it to stop first.
!macro StopApp
  ${If} ${FileExists} "$INSTDIR\python\python.exe"
  ${AndIf} ${FileExists} "$INSTDIR\quiz.py"
    nsExec::Exec '"$INSTDIR\python\python.exe" -I "$INSTDIR\quiz.py" quit'
    Pop $0
    Sleep 500
  ${EndIf}
!macroend

; Sets $R0 to 1 when $INSTDIR is new, empty or an earlier Code Quiz, so the
; installer never mixes its files into (or later deletes) another folder.
Function CheckInstDir
  StrCpy $R0 1
  ${If} ${FileExists} "$INSTDIR\*.*"
  ${AndIfNot} ${FileExists} "$INSTDIR\${UNINSTALLER}"
    FindFirst $R1 $R2 "$INSTDIR\*.*"
    ${DoWhile} $R2 != ""
      ${If} $R2 != "."
      ${AndIf} $R2 != ".."
        StrCpy $R0 0
        ${ExitDo}
      ${EndIf}
      FindNext $R1 $R2
    ${Loop}
    FindClose $R1
  ${EndIf}
FunctionEnd

Function .onVerifyInstDir
  Call CheckInstDir
  ${If} $R0 == 0
    Abort
  ${EndIf}
FunctionEnd

Function OpenApp
  Exec '${PYTHONW} app'
FunctionEnd

Section "Code Quiz" SecApp
  SectionIn RO
  Call CheckInstDir
  ${If} $R0 == 0
    Abort "$INSTDIR already holds other files. Choose a new or empty folder."
  ${EndIf}
  !insertmacro StopApp

  ; Replace the program files of an earlier version.
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\quizzes"
  Delete "$DESKTOP\${APP}.lnk"

  SetOutPath "$INSTDIR"
  File "${STAGE}\quiz.py"
  File "${STAGE}\icon.ico"
  File /r "${STAGE}\python"
  File /r "${STAGE}\app"
  File /r "${STAGE}\quizzes"
  WriteUninstaller "$INSTDIR\${UNINSTALLER}"

  CreateShortcut "$SMPROGRAMS\${APP}.lnk" "$INSTDIR\python\pythonw.exe" '-I "$INSTDIR\quiz.py" app' \
    "$INSTDIR\icon.ico" 0 SW_SHOWNORMAL "" "Multiple-choice drills for coding and data subjects"

  WriteRegStr HKCU "${APPKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\icon.ico"
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\${UNINSTALLER}"'
  WriteRegStr HKCU "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\${UNINSTALLER}" /S'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINSTKEY}" "EstimatedSize" "$0"
SectionEnd

Section "Desktop shortcut" SecDesktop
  CreateShortcut "$DESKTOP\${APP}.lnk" "$INSTDIR\python\pythonw.exe" '-I "$INSTDIR\quiz.py" app' \
    "$INSTDIR\icon.ico" 0 SW_SHOWNORMAL "" "Multiple-choice drills for coding and data subjects"
SectionEnd

Section "Open .quiz files" SecFiles
  WriteRegStr HKCU "Software\Classes\.quiz" "" "CodeQuiz.Module"
  WriteRegStr HKCU "Software\Classes\.quiz\OpenWithProgids" "CodeQuiz.Module" ""
  WriteRegStr HKCU "Software\Classes\CodeQuiz.Module" "" "Code Quiz module"
  WriteRegStr HKCU "Software\Classes\CodeQuiz.Module\DefaultIcon" "" "$INSTDIR\icon.ico"
  WriteRegStr HKCU "Software\Classes\CodeQuiz.Module\shell\open\command" "" '${PYTHONW} app --import "%1"'
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp} "The app, the built-in subjects and the copy of Python it runs on."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "A Code Quiz shortcut on the desktop. The Start menu always gets one."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecFiles} "Open .quiz module files with Code Quiz: double-click one to add that subject."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  !insertmacro StopApp
  Delete "$SMPROGRAMS\${APP}.lnk"
  Delete "$DESKTOP\${APP}.lnk"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\quizzes"
  Delete "$INSTDIR\quiz.py"
  Delete "$INSTDIR\icon.ico"
  Delete "$INSTDIR\${UNINSTALLER}"
  RMDir "$INSTDIR"

  ; Undo the .quiz file type, leaving any other program's claim on it alone.
  ReadRegStr $0 HKCU "Software\Classes\.quiz" ""
  ${If} $0 == "CodeQuiz.Module"
    DeleteRegValue HKCU "Software\Classes\.quiz" ""
  ${EndIf}
  DeleteRegValue HKCU "Software\Classes\.quiz\OpenWithProgids" "CodeQuiz.Module"
  DeleteRegKey /ifempty HKCU "Software\Classes\.quiz\OpenWithProgids"
  DeleteRegKey /ifempty HKCU "Software\Classes\.quiz"
  DeleteRegKey HKCU "Software\Classes\CodeQuiz.Module"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'

  DeleteRegKey HKCU "${UNINSTKEY}"
  DeleteRegKey HKCU "${APPKEY}"

  ; Added modules and settings stay unless the user asks to delete them
  ; (a silent uninstall keeps them).
  ${If} ${FileExists} "$APPDATA\CodeQuiz\*.*"
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 \
      "Also delete the modules you added and your settings, including a saved GitHub token?$\r$\n$\r$\n$APPDATA\CodeQuiz" \
      /SD IDNO IDNO keep_data
    RMDir /r "$APPDATA\CodeQuiz"
    keep_data:
  ${EndIf}
SectionEnd
