[Setup]
AppName=GP Bridge
AppVersion=0.1.0
AppPublisher=WTdusk
DefaultDirName={localappdata}\Programs\GP Bridge
PrivilegesRequired=lowest
DefaultGroupName=GP Bridge
OutputDir=dist\installer
OutputBaseFilename=GPBridge-Setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\GPBridge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\GPBridgeMCP.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "AGENT_KONTAKT_PROFILE_WORKFLOW.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\gpbridge.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\GP Bridge"; Filename: "{app}\GPBridge.exe"
Name: "{commondesktop}\GP Bridge"; Filename: "{app}\GPBridge.exe"

[Dirs]
Name: "{app}\GPBridgeData\Profiles\kontakt"
Name: "{app}\GPBridgeData\MIDI"
