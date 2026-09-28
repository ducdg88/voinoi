$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$Version = "2.0.2"
$AppName = "VoiNoi"
$ReleaseBaseUrl = "https://github.com/ducdg88/voinoi/releases/latest/download"

Set-Location $Root

if (-not (Test-Path $Venv)) {
  python -m venv $Venv
}

& "$Venv\Scripts\python.exe" -m pip install --upgrade pip
& "$Venv\Scripts\python.exe" -m pip install -r requirements.txt

# Ban .exe gon nhe: Whisper (du phong ngoai tuyen, vai tram MB) khong dong goi.
# Muon dung Whisper thi chay ban nguon voi requirements-whisper.txt.
& "$Venv\Scripts\python.exe" -m PyInstaller `
  --noconfirm `
  --clean `
  --noconsole `
  --onedir `
  --name $AppName `
  --icon "assets\voinoi.ico" `
  --add-data "voice-mic-settings.json;." `
  --add-data "voice-context.json;." `
  --add-data "assets\voinoi.ico;assets" `
  --add-data "reader\static;reader\static" `
  --add-data "reader\huong-dan.md;reader" `
  --hidden-import doc_reader `
  --additional-hooks-dir "pyinstaller-hooks" `
  --exclude-module faster_whisper `
  --exclude-module whisper `
  --exclude-module torch `
  --exclude-module ctranslate2 `
  --exclude-module onnxruntime `
  --exclude-module av `
  --exclude-module tokenizers `
  --exclude-module huggingface_hub `
  --exclude-module numba `
  --exclude-module scipy `
  voice_mic_icon.py
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$Out = Join-Path $Root "dist\$AppName"
foreach ($file in @("README.md", "install-startup.ps1", "uninstall-startup.ps1", "install-shortcut.ps1", "updater.ps1", "voice-mic-settings.json", "voice-context.json")) {
  Copy-Item (Join-Path $Root $file) $Out -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $Out "assets") | Out-Null
Copy-Item (Join-Path $Root "assets\voinoi.ico") (Join-Path $Out "assets") -Force

$ReleaseDir = Join-Path $Root "releases"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$ZipName = "$AppName-windows.zip"
$Zip = Join-Path $ReleaseDir $ZipName
if (Test-Path $Zip) {
  Remove-Item $Zip -Force
}
Compress-Archive -Path (Join-Path $Out "*") -DestinationPath $Zip -Force
$Hash = (Get-FileHash -Algorithm SHA256 -Path $Zip).Hash.ToLowerInvariant()
$Manifest = [ordered]@{
  version = $Version
  zip_url = $ZipName
  sha256 = $Hash
  notes = "$AppName $Version"
  release_url = "$ReleaseBaseUrl/$ZipName"
}
# Khong dung Set-Content -Encoding UTF8: PowerShell 5 them BOM, ban app cu doc manifest bi loi JSON
[IO.File]::WriteAllText((Join-Path $ReleaseDir "version.json"), ($Manifest | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding $false))

Write-Host ""
Write-Host "Build complete:" $Out
Write-Host "Run:" (Join-Path $Out "$AppName.exe")
Write-Host "Zip:" $Zip
Write-Host "Manifest:" (Join-Path $ReleaseDir "version.json")
