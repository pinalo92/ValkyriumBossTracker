; Inno Setup 6 — Valkyrium Boss Tracker
; Compilar: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\Valkyrium.iss

#define MyAppName "Valkyrium Boss Tracker"
#define MyAppVersion "0.2.2"
#define MyAppPublisher "Pinalo"
#define MyAppURL "https://github.com/pinalo92/ValkyriumBossTracker"
#define MyAppExeName "ValkyriumBossTracker.exe"

[Setup]
AppId={{A8F3C2E1-9B4D-4E7A-8C11-7F2E91B0D4A3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\ValkyriumBossTracker
DefaultGroupName=Valkyrium
DisableProgramGroupPage=yes
LicenseFile=
OutputDir=..\dist
OutputBaseFilename=ValkyriumSetup_v{#MyAppVersion}
SetupIconFile=..\pinalo_boss_tracker\data\app_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Accesos directos:"; Flags: checkedonce

[Files]
; Requiere build_onefile.bat previo
Source: "..\dist\Valkyrium_OneFile\ValkyriumBossTracker.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Valkyrium"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
