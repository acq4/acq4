#define AppName "ACQ4"
#define AppVersion "0.9.2"
#define AppURL "http://www.acq4.org/"
#define AppExeName "MyProg.exe"
#define BitDepth "64"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{006B563B-FB8A-41C6-A3DA-AED0FBC6D37A}
AppName={#AppName}
AppVersion={#AppVersion}
;AppVerName={#AppName} {#AppVersion}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={pf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=C:\Users\Luke\acq4
OutputBaseFilename=acq4-setup-{#AppVersion}-{#BitDepth}
Compression=lzma
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
DestDir: "{app}\Python27"; Source: "C:\Python27-{#BitDepth}\*"; Excludes: "*.pyc,*.pyo"; Flags: recursesubdirs
DestDir: "{app}\acq4"; Source: "C:\Users\Luke\acq4\acq4\*"; Excludes: "*.pyc,*.pyo"; Flags: recursesubdirs
DestDir: "{app}\config"; Source: "C:\Users\Luke\acq4\config\*"; Flags: recursesubdirs
DestDir: "{app}"; Source: "C:\Users\Luke\acq4\tools\acq4.bat"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\acq4.bat"; IconFilename: "{app}\acq4\icons\acq4.ico"; Flags: dontcloseonexit
Name: "{group}\Documentation"; Filename: "http://acq4.org/documentation"
Name: "{group}\configuration"; Filename: "{app}\config"; Flags: foldershortcut

[Run]
Filename: "{app}\acq4.bat"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

