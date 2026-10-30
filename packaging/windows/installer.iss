#define AppVersion "1.0.0"
#ifndef BundleDir
  #define BundleDir "..\..\dist\BHLIAudit"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\installer"
#endif

[Setup]
AppId={{C9470975-3249-43C2-A410-80972C956B05}
AppName=BHLI Audit
AppVersion={#AppVersion}
AppPublisher=BHLI Audit project
DefaultDirName={localappdata}\Programs\BHLI Audit
DefaultGroupName=BHLI Audit
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=BHLI-Audit-Setup-{#AppVersion}-x64
SetupIconFile=..\..\desktop\assets\bhli.ico
UninstallDisplayIcon={app}\BHLIAudit.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dynamic
CloseApplications=no
RestartApplications=no
AppMutex=Local\BHLI.Audit.Desktop.Running
UninstallDisplayName=BHLI Audit
VersionInfoDescription=BHLI Audit client installer (test candidate)

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BHLI Audit"; Filename: "{app}\BHLIAudit.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\BHLI Audit"; Filename: "{app}\BHLIAudit.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\BHLIAudit.exe"; Description: "Launch BHLI Audit"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeUninstall(): Boolean;
begin
  Result := not CheckForMutexes('Local\BHLI.Audit.Desktop.Running');
  if not Result then
    SuppressibleMsgBox('Close BHLI Audit normally before uninstalling. Pending requests may still complete. Your settings and reports will be preserved.', mbError, MB_OK, IDOK);
end;
