$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$appExe = Join-Path $repoRoot "dist\attend\attend.exe"
if (-not (Test-Path $appExe)) {
    throw "App bundle not found. Build it first with scripts\build_windows.ps1."
}

$compiler = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $compiler)) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) {
        $compiler = $command.Source
    } else {
        throw "Inno Setup 6 is required to build the installer. Install it from https://jrsoftware.org/isinfo.php."
    }
}

& $compiler "/Qp" (Join-Path $PSScriptRoot "attend.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed."
}

$installer = Join-Path $repoRoot "dist\attend.exe"
Write-Host "Installer complete: $installer"
