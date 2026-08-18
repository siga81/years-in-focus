<#
Build the Windows installer from the existing portable release\YearsInFocus\ folder.

Prerequisites:
  - tools\build_windows.ps1 was run successfully
  - Inno Setup 7 is installed (ISCC.exe)
#>

[CmdletBinding()]
param(
    [string]$InnoCompiler = "C:\Program Files\Inno Setup 7\ISCC.exe"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$portable = Join-Path $root "release\YearsInFocus\YearsInFocus.exe"
$script = Join-Path $root "installer\YearsInFocus.iss"

if (-not (Test-Path -LiteralPath $portable)) {
    throw "Portable Ausgabe fehlt: $portable. Zuerst tools\build_windows.ps1 ausführen."
}
if (-not (Test-Path -LiteralPath $InnoCompiler)) {
    throw "Inno Setup Compiler nicht gefunden: $InnoCompiler"
}

& $InnoCompiler $script
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup konnte den Installer nicht erzeugen."
}

Write-Host "Installer fertig: $(Join-Path $root 'release\installer')"
