<#
  Builds the Windows executable (and the installer, when Inno Setup is installed).

  Usage (PowerShell, from anywhere):  .\packaging\build_windows.ps1 [-SkipInstaller]
  Output:  dist\NetWatcher\NetWatcher.exe   and   dist\installer\NetWatcher-Setup-<version>.exe  (publish with: platform key windows-x64)
#>
param([switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

& .\.venv\Scripts\python.exe -m PyInstaller packaging\net_watcher.spec --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "Built dist\NetWatcher\NetWatcher.exe"

$proc = Start-Process -FilePath "dist\NetWatcher\NetWatcher.exe" -ArgumentList "--self-test" -Wait -PassThru
if ($proc.ExitCode -ne 0) { throw "Packaged app failed its self-test (see %APPDATA%\NetWatcher\logs)" }
Write-Host "Self-test passed"

$Version = (& .\.venv\Scripts\python.exe -c "from core.version import __version__; print(__version__)").Trim()
$Feed = (& .\.venv\Scripts\python.exe -c "from core.update import config; print(bool(config.FEED_URL and config.PUBLIC_KEYS))").Trim()
if ($Feed -ne "True") { Write-Warning "core/update/config.py has no FEED_URL / PUBLIC_KEYS: this build will not check for updates." }

if ($SkipInstaller) { return }
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    $candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $candidate) { $iscc = $candidate }
}
if ($iscc) {
    & $iscc "/DAppVersion=$Version" packaging\windows_installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "Installer written to dist\installer\"
} else {
    Write-Warning "Inno Setup 6 not found - skipped installer. Install it from https://jrsoftware.org/isinfo.php and re-run."
}
