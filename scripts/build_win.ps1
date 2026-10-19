<#
.SYNOPSIS
  一键构建 Windows 便携包 + Inno Setup 安装包 + SHA256SUMS。

.DESCRIPTION
  干净 venv -> requirements-build -> 单测 -> PyInstaller one-folder -> 便携 ZIP
  -> ISCC 安装包 -> SHA256SUMS。默认输出 release/。

.PARAMETER Python
  创建 venv 使用的 Python 命令（默认 python）。

.PARAMETER SkipTests
  跳过单元测试（仅排障用，正式发布不要跳过）。

.PARAMETER Clean
  删除 build/venv 后重新创建。
#>
param(
    [string]$Python = "python",
    [switch]$SkipTests,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildDir = Join-Path $Root "build"
$VenvDir = Join-Path $BuildDir "venv"
$DistDir = Join-Path $BuildDir "dist"
$ReleaseDir = Join-Path $Root "release"
$SpecFile = Join-Path $Root "delta_client.spec"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-Iscc {
    if ($env:ISCC -and (Test-Path $env:ISCC)) { return (Resolve-Path $env:ISCC).Path }
    $known = "C:\Users\1\Documents\deepseek-harness\default-workspace\.tmp\build\InnoSetup\ISCC.exe"
    if (Test-Path $known) { return $known }
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw "找不到 Inno Setup ISCC.exe：请设置环境变量 ISCC，或安装 Inno Setup。"
}

Push-Location $Root
try {
    Write-Step "读取版本号"
    $Version = (& $Python -c "from config import APP_VERSION; print(APP_VERSION)").Trim()
    if (-not $Version) { throw "无法从 config.APP_VERSION 读取版本号" }
    $VersionInfo = (& $Python -c "from config import APP_VERSION; from scripts.write_version_info import version_tuple; print('.'.join(map(str, version_tuple(APP_VERSION))))").Trim()
    Write-Host "APP_VERSION=$Version ($VersionInfo)"

    if ($Clean -and (Test-Path $VenvDir)) {
        Write-Step "清理旧 venv"
        Remove-Item -Recurse -Force $VenvDir
    }
    if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
        Write-Step "创建干净 venv"
        New-Item -ItemType Directory -Force $BuildDir | Out-Null
        & $Python -m venv $VenvDir
    }
    $VenvPython = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) { throw "venv Python 创建失败：$VenvPython" }

    # 避免继承本机 PYTHONPATH 污染打包环境
    $SavedPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = $null
    try {
        Write-Step "安装打包依赖（requirements-build.txt）"
        & $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $Root "requirements-build.txt")
        if ($LASTEXITCODE -ne 0) { throw "pip install 失败（exit $LASTEXITCODE）" }
        $E3Requirements = Join-Path $Root "requirements-e3.txt"
        if (Test-Path $E3Requirements) {
            Write-Step "安装 E3b 采集/OCR 依赖（requirements-e3.txt）"
            & $VenvPython -m pip install --disable-pip-version-check -r $E3Requirements
            if ($LASTEXITCODE -ne 0) { throw "E3 依赖安装失败（exit $LASTEXITCODE）" }
        }

        if (-not $SkipTests) {
            Write-Step "运行单元测试"
            & $VenvPython -m unittest discover -s tests
            if ($LASTEXITCODE -ne 0) { throw "单元测试失败（exit $LASTEXITCODE）" }
        }

        Write-Step "生成 Windows 版本资源"
        & $VenvPython scripts/write_version_info.py
        if ($LASTEXITCODE -ne 0) { throw "生成 version_info 失败" }

        if (-not (Test-Path (Join-Path $Root "assets\app.ico"))) {
            Write-Step "生成应用图标"
            & $VenvPython scripts/make_icon.py
            if ($LASTEXITCODE -ne 0) { throw "生成 app.ico 失败" }
        }

        Write-Step "PyInstaller one-folder 构建（--noupx）"
        if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
        & $VenvPython -m PyInstaller --clean --noconfirm `
            --distpath $DistDir --workpath (Join-Path $BuildDir "pyinstaller") $SpecFile
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败（exit $LASTEXITCODE）" }
        $AppDir = Join-Path $DistDir "DeltaClient"
        $AppExe = Join-Path $AppDir "DeltaClient.exe"
        if (-not (Test-Path $AppExe)) { throw "未找到构建产物：$AppExe" }

        Write-Step "验证便携包版本资源"
        $fileVersion = (Get-Item $AppExe).VersionInfo.FileVersion
        if ($fileVersion -notmatch [regex]::Escape($Version)) {
            throw "便携包 FileVersion 不正确：$fileVersion（期望 $Version）"
        }
        Write-Host "portable FileVersion: $fileVersion"

        New-Item -ItemType Directory -Force $ReleaseDir | Out-Null
        $PortableZip = Join-Path $ReleaseDir "DeltaClient-$Version-portable.zip"
        if (Test-Path $PortableZip) { Remove-Item -Force $PortableZip }
        Write-Step "生成便携 ZIP"
        Compress-Archive -Path (Join-Path $AppDir "*") -DestinationPath $PortableZip -CompressionLevel Optimal
        if (-not (Test-Path $PortableZip)) { throw "便携 ZIP 生成失败" }

        Write-Step "Inno Setup 安装包"
        $Iscc = Resolve-Iscc
        $SetupExe = Join-Path $ReleaseDir "DeltaClient-Setup-$Version.exe"
        if (Test-Path $SetupExe) { Remove-Item -Force $SetupExe }
        & $Iscc "/DAppVersion=$Version" "/DAppVersionInfo=$VersionInfo" `
            "/DSourceDir=$AppDir" "/DOutputDir=$ReleaseDir" "/DRepoDir=$Root" `
            (Join-Path $Root "installer\delta_client.iss")
        if ($LASTEXITCODE -ne 0) { throw "ISCC 编译失败（exit $LASTEXITCODE）" }
        if (-not (Test-Path $SetupExe)) { throw "未找到安装包：$SetupExe" }

        Write-Step "生成 SHA256SUMS"
        $Sums = Join-Path $ReleaseDir "SHA256SUMS.txt"
        $lines = @()
        foreach ($file in @($SetupExe, $PortableZip)) {
            $hash = (Get-FileHash -Algorithm SHA256 $file).Hash.ToLowerInvariant()
            $lines += "$hash  $(Split-Path -Leaf $file)"
        }
        $lines | Set-Content -Encoding ASCII $Sums

        Write-Step "完成"
        Write-Host "Setup:   $SetupExe"
        Write-Host "Portable:$PortableZip"
        Write-Host "SHA256:  $Sums"
    }
    finally {
        $env:PYTHONPATH = $SavedPythonPath
    }
}
finally {
    Pop-Location
}

