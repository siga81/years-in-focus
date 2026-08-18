; Years in Focus - Windows installer
; Build after tools\build_windows.ps1 has produced release\YearsInFocus\.

#define AppName "Years in Focus"
#define AppVersion "0.1.4"
#define AppPublisher "Years in Focus"
#define AppExeName "YearsInFocus.exe"

[Setup]
AppId={{ABA275CE-C4F1-4CFD-B932-958E1A0CDF96}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
LicenseFile=..\LICENSE
SetupIconFile=..\assets\YiF-Icon.ico
; Classic system-wide Windows installation. Inno Setup asks for elevation itself;
; users do not need to start the installer manually as administrator.
DefaultDirName={autopf}\Years in Focus
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\release\installer
OutputBaseFilename=YearsInFocus-Setup-{#AppVersion}-x64-system
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\release\YearsInFocus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
