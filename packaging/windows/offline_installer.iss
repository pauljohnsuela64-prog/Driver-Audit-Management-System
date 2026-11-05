#ifndef BundleDir
  #define BundleDir "..\..\dist\BHLIAuditOffline"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\offline-installer"
#endif

[Setup]
AppId={{6C429C06-F81C-4C60-A5BC-C8A0E0987F5D}
AppName=BHLI Audit Offline
AppVersion=1.0.0-offline-dev
VersionInfoVersion=1.0.0.0
AppPublisher=BHLI Audit project
DefaultDirName={localappdata}\Programs\BHLI Audit Offline
DefaultGroupName=BHLI Audit Offline
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=BHLI-Audit-Offline-Setup-1.0.0-dev-x64
SetupIconFile=..\..\desktop\assets\bhli.ico
UninstallDisplayIcon={app}\BHLIAuditOffline.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dynamic
CloseApplications=no
RestartApplications=no
AppMutex=Local\BHLI.Audit.Offline.Desktop.Running
UninstallDisplayName=BHLI Audit Offline
VersionInfoDescription=BHLI Audit Offline installer — fictional development testing only

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BHLI Audit Offline"; Filename: "{app}\BHLIAuditOffline.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\BHLI Audit Offline"; Filename: "{app}\BHLIAuditOffline.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\BHLIAuditOffline.exe"; Description: "Launch BHLI Audit Offline"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeUninstall(): Boolean;
begin
  Result := not CheckForMutexes('Local\BHLI.Audit.Offline.Desktop.Running');
  if not Result then
    SuppressibleMsgBox('Close BHLI Audit Offline normally before uninstalling. Local writes must finish. Local records will be preserved, but no backup exists yet.', mbError, MB_OK, IDOK);
end;
