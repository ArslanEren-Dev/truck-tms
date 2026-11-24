; Inno Setup script for the Truck TMS installer (dist\TruckTMS-Setup.exe).
; Build it with packaging\build_installer.ps1 after packaging\build_exe.ps1, or let the release
; workflow do both. The version comes from the command line: ISCC /DAppVersion=0.7.0 TruckTMS.iss
;
; Installs for the current user by default (no administrator rights needed), adds a Start menu
; shortcut and, if chosen, a desktop shortcut. Uninstalling removes the program only: the data
; file in the user's folder (~/.truck_tms) and its backups are never touched.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3A2C61-6B7D-4E1F-9C2A-5D4B3E7F1A90}
AppName=Truck TMS
AppVersion={#AppVersion}
AppVerName=Truck TMS {#AppVersion}
AppPublisher=Arslan Eren
AppPublisherURL=https://arslaneren-dev.github.io/truck-tms/
AppSupportURL=https://github.com/ArslanEren-Dev/truck-tms/issues
AppUpdatesURL=https://github.com/ArslanEren-Dev/truck-tms/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\Truck TMS
DefaultGroupName=Truck TMS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=TruckTMS-Setup
SetupIconFile=..\truck_tms\assets\truck_tms.ico
UninstallDisplayIcon={app}\TruckTMS.exe
UninstallDisplayName=Truck TMS
LicenseFile=..\LICENSE
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\TruckTMS.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Truck TMS"; Filename: "{app}\TruckTMS.exe"
Name: "{autodesktop}\Truck TMS"; Filename: "{app}\TruckTMS.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TruckTMS.exe"; Description: "{cm:LaunchProgram,Truck TMS}"; Flags: nowait postinstall skipifsilent
