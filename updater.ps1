param(
  [Parameter(Mandatory = $true)][int]$AppPid,
  [Parameter(Mandatory = $true)][string]$ZipPath,
  [Parameter(Mandatory = $true)][string]$AppDir,
  [Parameter(Mandatory = $true)][string]$ExeName
)

$ErrorActionPreference = "Stop"

function Write-UpdateLog {
  param([string]$Message)
  $LogPath = Join-Path $AppDir "voice-update.log"
  $Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $LogPath -Encoding UTF8 -Value "$Stamp $Message"
}

try {
  Write-UpdateLog "update started | pid=$AppPid | zip=$ZipPath"

  try {
    Wait-Process -Id $AppPid -Timeout 30
  } catch {
    Write-UpdateLog "wait timed out; continuing"
  }

  $ResolvedAppDir = (Resolve-Path $AppDir).Path
  $ResolvedZip = (Resolve-Path $ZipPath).Path
  $TempDir = Join-Path ([IO.Path]::GetTempPath()) ("VoiNoi-extract-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
  Expand-Archive -Path $ResolvedZip -DestinationPath $TempDir -Force

  $SourceDir = $TempDir
  $NestedExe = Get-ChildItem -Path $TempDir -Recurse -Filter $ExeName | Select-Object -First 1
  if ($NestedExe) {
    $SourceDir = $NestedExe.Directory.FullName
  }

  $Preserve = @(
    "voice-mic-settings.json",
    "voice-mic-settings.local.json",
    "voice-context.json",
    "voice-context.local.json",
    "voice-mic.log",
    "voice-update.log",
    "voice-targets.json",
    "mic-position.json"
  )

  Get-ChildItem -Path $SourceDir -Force | ForEach-Object {
    if ($Preserve -contains $_.Name) {
      if (-not (Test-Path (Join-Path $ResolvedAppDir $_.Name))) {
        Copy-Item -LiteralPath $_.FullName -Destination $ResolvedAppDir -Recurse -Force
      }
      return
    }
    Copy-Item -LiteralPath $_.FullName -Destination $ResolvedAppDir -Recurse -Force
  }

  Remove-Item -LiteralPath $TempDir -Recurse -Force -ErrorAction SilentlyContinue
  Write-UpdateLog "update copied files"

  $ExePath = Join-Path $ResolvedAppDir $ExeName
  Start-Process -FilePath $ExePath -WorkingDirectory $ResolvedAppDir
  Write-UpdateLog "app restarted | exe=$ExePath"
} catch {
  Write-UpdateLog ("update failed: " + $_.Exception.Message)
  throw
}
