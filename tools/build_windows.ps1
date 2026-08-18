<#
Build the portable Windows distribution of Years in Focus.

Prerequisites:
  - a virtual environment at .build-venv with the project dependencies and PyInstaller
  - models\mediapipe\face_landmarker.task
  - models\yunet\face_detection_yunet_2023mar.onnx

The result is release\YearsInFocus\. Keep that folder intact: YearsInFocus.exe
starts the GUI, YearsInFocusCLI.exe is its private import/export worker.
#>

[CmdletBinding()]
param(
    [string]$Python = ".build-venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $root $Python
$modelsPath = Join-Path $root "models"
$iconPath = Join-Path $root "assets\YiF-Icon.ico"
$iconImagePath = Join-Path $root "assets\YiF-Icon.png"
$ffmpegBinPath = Join-Path $root "third_party\ffmpeg\bin"
$ffmpegLicensePath = Join-Path $root "third_party\ffmpeg\LICENSE-FFmpeg-LGPLv3.txt"
$ffmpegNoticePath = Join-Path $root "third_party\ffmpeg\FFMPEG-NOTICE.txt"
$thirdPartyNoticesPath = Join-Path $root "THIRD_PARTY_NOTICES.md"
$projectLicensePath = Join-Path $root "LICENSE"
$privacyNoticePath = Join-Path $root "PRIVACY.md"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Build-Python nicht gefunden: $pythonPath"
}
foreach ($requiredModel in @(
    (Join-Path $modelsPath "mediapipe\face_landmarker.task"),
    (Join-Path $modelsPath "yunet\face_detection_yunet_2023mar.onnx"),
    $iconPath,
    $iconImagePath,
    (Join-Path $ffmpegBinPath "ffmpeg.exe"),
    (Join-Path $ffmpegBinPath "ffprobe.exe"),
    $ffmpegLicensePath,
    $ffmpegNoticePath,
    $thirdPartyNoticesPath,
    $projectLicensePath,
    $privacyNoticePath
)) {
    if (-not (Test-Path -LiteralPath $requiredModel)) {
        throw "Benötigtes Modell fehlt: $requiredModel"
    }
}

$distPath = Join-Path $root "release"
$workPath = Join-Path $root ".pyinstaller-work"
$specPath = Join-Path $root ".pyinstaller-spec"
$env:PYTHONUSERBASE = Join-Path $root ".pyinstaller-userbase"

Push-Location $root
try {
    # Prevent a developer's private Python package folder from becoming an implicit
    # PyInstaller search path. It may be inaccessible and is never part of YiF.
    & $pythonPath -s -m PyInstaller --noconfirm --clean --onedir --windowed `
        --name YearsInFocus --icon $iconPath --paths "src" --add-data "$modelsPath;models" `
        --add-data "$iconImagePath;assets" `
        --collect-all mediapipe --collect-all cv2 --hidden-import pymysql `
        --distpath $distPath --workpath (Join-Path $workPath "gui") `
        --specpath $specPath "run_storyboard.pyw"
    if ($LASTEXITCODE -ne 0) {
        throw "Der portable GUI-Build ist fehlgeschlagen."
    }

    & $pythonPath -s -m PyInstaller --noconfirm --clean --onefile `
        --name YearsInFocusCLI --paths "src" --collect-all mediapipe --collect-all cv2 --hidden-import pymysql `
        --distpath (Join-Path $distPath "YearsInFocus") --workpath (Join-Path $workPath "cli") `
        --specpath $specPath "run_cli.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Der portable CLI-Build ist fehlgeschlagen."
    }

    # A single, shared LGPL FFmpeg copy sits next to both executables. This lets
    # the GUI and its private one-file CLI worker use the exact same tools.
    $releaseAppPath = Join-Path $distPath "YearsInFocus"
    Copy-Item -LiteralPath (Join-Path $ffmpegBinPath "ffmpeg.exe") -Destination $releaseAppPath -Force
    Copy-Item -LiteralPath (Join-Path $ffmpegBinPath "ffprobe.exe") -Destination $releaseAppPath -Force
    $licenseDestination = Join-Path $releaseAppPath "licenses"
    New-Item -ItemType Directory -Force -Path $licenseDestination | Out-Null
    Copy-Item -LiteralPath $ffmpegLicensePath -Destination $licenseDestination -Force
    Copy-Item -LiteralPath $ffmpegNoticePath -Destination $licenseDestination -Force
    Copy-Item -LiteralPath $thirdPartyNoticesPath -Destination $licenseDestination -Force
    Copy-Item -LiteralPath $projectLicensePath -Destination $licenseDestination -Force
    Copy-Item -LiteralPath $privacyNoticePath -Destination $licenseDestination -Force
}
finally {
    Pop-Location
}

Write-Host "Portable Ausgabe fertig: $(Join-Path $distPath 'YearsInFocus')"
