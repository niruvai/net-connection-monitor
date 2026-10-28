; Inno Setup script - compile with:  iscc packaging\windows_installer.iss
; Requires the PyInstaller output in dist\NetWatcher (see build_windows.ps1).
#define AppName "Net Watcher"
#ifndef AppVersion
  #define AppVersion "1.0.0"  ; normally passed by build_windows.ps1: iscc /DAppVersion=x.y.z
#endif
#define AppExe "NetWatcher.exe"

[Setup]
AppId={{6F1B7C0E-3C9A-4C58-9B74-2B7F5E0C1D42}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Net Watcher
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=NetWatcher-Setup-{#AppVersion}
SetupIconFile=..\assets\icons\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startup"; Description: "Start Net Watcher when I sign in to Windows"; GroupDescription: "Startup:"

[Files]
Source: "..\dist\NetWatcher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same value the in-app "Start with Windows" setting writes, so both stay in sync.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "NetWatcher"; \
    ValueData: """{app}\{#AppExe}"" --minimized"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
; In-app updates run this installer with /SILENT /NWUPDATE=1: reopen the app when it finishes.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: IsAppUpdate

[Code]
function IsAppUpdate: Boolean;
begin
  Result := ExpandConstant('{param:NWUPDATE|0}') = '1';
end;
