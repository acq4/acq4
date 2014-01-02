#define AppName "ACQ4"
#define MyAppVersion "0.9.0"
#define MyAppURL "http://www.acq4.org/"
#define MyAppExeName "MyProg.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{006B563B-FB8A-41C6-A3DA-AED0FBC6D37A}
AppName={#AppName}
AppVersion={#MyAppVersion}
;AppVerName={#AppName} {#MyAppVersion}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={pf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=C:\Users\Luke\acq4
OutputBaseFilename=acq4-setup
Compression=lzma
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
DestDir: "{app}"; Source: "C:\Python27\*"; Excludes: "*.pyc,*.pyo"; Flags: recursesubdirs
DestDir: "{app}"; Source: "C:\Luke\acq4\acq4"; Excludes: "*.pyc,*.pyo"; Flags: recursesubdirs
DestDir: "{app}"; Source: "C:\Luke\acq4\config"
DestDir: "{app}"; Source: "C:\Luke\acq4\tools\acq4.bat"

;[Icons]
;Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\acq4.bat"; Description: "{cm:LaunchProgram,{AppName}}"; Flags: nowait postinstall skipifsilent

