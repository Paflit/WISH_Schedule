param(
    [switch]$Clean = $true
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ProjectRoot '.venv'
$PythonExe = Join-Path $VenvPath 'Scripts\python.exe'
$PipExe = Join-Path $VenvPath 'Scripts\pip.exe'

Write-Host '==> Project root:' $ProjectRoot

if (-not (Test-Path $VenvPath)) {
    Write-Host '==> Creating virtual environment...'
    python -m venv "$VenvPath"
}

Write-Host '==> Upgrading pip...'
& "$PythonExe" -m pip install --upgrade pip

Write-Host '==> Installing requirements...'
& "$PipExe" install -r (Join-Path $ProjectRoot 'requirements.txt')

if ($Clean) {
    Write-Host '==> Cleaning previous build artifacts...'
    $BuildDir = Join-Path $ProjectRoot 'build'
    $DistDir = Join-Path $ProjectRoot 'dist'
    if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
    if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
}

Write-Host '==> Building release exe with PyInstaller...'
& "$PythonExe" -m PyInstaller --noconfirm (Join-Path $ProjectRoot 'WISH_Schedule.spec')

$ReleaseDir = Join-Path $ProjectRoot 'dist\WISH_Schedule'
$ExePath = Join-Path $ReleaseDir 'WISH_Schedule.exe'

if (-not (Test-Path $ExePath)) {
    throw "Build failed: exe not found at $ExePath"
}

foreach ($DirName in @('data', 'exports', 'imports', 'logs')) {
    $TargetDir = Join-Path $ReleaseDir $DirName
    if (-not (Test-Path $TargetDir)) {
        New-Item -ItemType Directory -Path $TargetDir | Out-Null
    }
}

$SourceDb = Join-Path $ProjectRoot 'data\schedule.db'
$TargetDb = Join-Path $ReleaseDir 'data\schedule.db'
if ((Test-Path $SourceDb) -and -not (Test-Path $TargetDb)) {
    Write-Host '==> Copying current database into release package...'
    Copy-Item $SourceDb $TargetDb
}

Write-Host ''
Write-Host 'Build complete.'
Write-Host 'Exe:' $ExePath
