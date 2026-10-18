#define MyAppName "FlyGPT"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "FlyGPT Project"
#define MyAppExeName "FlyGPT.exe"

[Setup]
AppId={{C94E1A5E-CE25-48C6-9C9C-7E2D1A9E8B31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\FlyGPT
DefaultGroupName=FlyGPT
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=FlyGPT-Setup-0.1.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\FlyGPT\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\FlyGPT"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\FlyGPT"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\SetupOllama.ps1"""; Description: "Set up Ollama and download FlyGPT's AI model"; Flags: postinstall waituntilterminated skipifsilent
Filename: "{app}\{#MyAppExeName}"; Description: "Launch FlyGPT"; Flags: postinstall nowait skipifsilent unchecked
