param([switch]$SkipZip)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$python = Join-Path $repoRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Create and populate venv first: python -m venv venv; venv\Scripts\python -m pip install -r requirements.txt -r requirements-build.txt"
}

& $python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is missing. Install it with: venv\Scripts\python -m pip install -r requirements-build.txt"
}

$qmlPath = Join-Path $repoRoot "app\ui\qml"
$iconPath = Join-Path $repoRoot "logos\logo.ico"
$versionInfoPath = Join-Path $repoRoot "scripts\version_info.txt"
if (-not (Test-Path $iconPath)) { throw "Windows icon not found: $iconPath" }
$arguments = @(
    "--noconfirm",
    "--additional-hooks-dir", "scripts/pyinstaller_hooks",
    "--specpath", "build",
    "--add-data", "$qmlPath;app/ui/qml",
    "--icon", $iconPath,
    "--version-file", $versionInfoPath,
    "--windowed",
    "--onedir",
    "--name", "attend",
    "--collect-submodules", "PySide6.QtQuick",
    "--collect-submodules", "PySide6.QtQuickWidgets",
    "--collect-submodules", "PySide6.QtSvg",
    "--collect-data", "insightface",
    "--collect-submodules", "insightface.app",
    "--collect-submodules", "insightface.model_zoo",
    "--exclude-module", "PySide6.QtWebEngineCore",
    "--exclude-module", "PySide6.QtWebEngineWidgets",
    "--exclude-module", "PySide6.QtWebEngineQuick",
    "--collect-binaries", "onnxruntime",
    "--collect-binaries", "faiss",
    "app/main.py"
)

& $python -m PyInstaller @arguments
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

Copy-Item README.md (Join-Path $repoRoot "dist\attend\README.txt") -Force
if ($SkipZip) {
    Write-Host "App bundle complete; ZIP creation skipped."
    exit 0
}
$archive = Join-Path $repoRoot "dist\attend-windows-x64.zip"
if (Test-Path $archive) {
    Remove-Item $archive -Force
}
Compress-Archive -Path (Join-Path $repoRoot "dist\attend") -DestinationPath $archive -CompressionLevel Optimal
Write-Host "Build complete: $archive"
Write-Host "Extract the ZIP and run attend\attend.exe. First launch downloads the InsightFace model."
