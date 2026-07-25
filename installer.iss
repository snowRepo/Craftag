[Setup]
; Main Installer Settings
AppName=Craftag
AppVersion=1.0.6
AppPublisher=DevApps
AppPublisherURL=https://devapps-online.vercel.app/
DefaultDirName={autopf}\Craftag
DisableProgramGroupPage=yes
PrivilegesRequired=lowest

; Installer Output and Compression
OutputBaseFilename=Craftag-Windows-Installer
OutputDir=dist
Compression=lzma2/ultra64
SolidCompression=yes

; Visuals
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\Craftag.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copy all files from PyInstaller's --onedir output
Source: "dist\Craftag\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Craftag"; Filename: "{app}\Craftag.exe"
Name: "{autodesktop}\Craftag"; Filename: "{app}\Craftag.exe"; Tasks: desktopicon
