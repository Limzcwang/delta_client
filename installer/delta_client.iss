; Delta Client Inno Setup 安装脚本（P2）
; 版本/源目录/输出目录由 scripts/build_win.ps1 通过 /D 注入；也可直接 ISCC 编译：
;   ISCC /DAppVersion=0.1.0 /DAppVersionInfo=0.1.0.0 installer\delta_client.iss

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef AppVersionInfo
  #define AppVersionInfo "0.1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\dist\DeltaClient"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif
#ifndef RepoDir
  #define RepoDir ".."
#endif

#define AppName "Delta Client"
#define AppExeName "DeltaClient.exe"

[Setup]
AppId={{8D5F3C1E-7A4B-4E2A-9C1D-2B6E5A9F0C31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Delta
DefaultDirName={localappdata}\Programs\DeltaClient
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=DeltaClient-Setup-{#AppVersion}
SetupIconFile={#RepoDir}\assets\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
VersionInfoVersion={#AppVersionInfo}
VersionInfoCompany=Delta
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} 安装程序

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\DeltaClient');
    if DirExists(DataDir) then
    begin
      if MsgBox('是否同时删除用户数据（配置、会话、日志、历史账号）？' + #13#10 +
                '选择“否”将保留数据，下次安装仍可使用。',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
