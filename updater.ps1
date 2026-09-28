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
  $ExePath = Join-Path $ResolvedAppDir $ExeName

  # Tro ly doc chay la mot VoiNoi.exe rieng (--doc-reader) va khoa file trong _internal:
  # khong tat thi chep de that bai giua chung. Tat moi ban cua dung exe nay trong thu muc app.
  Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Id -ne $PID -and $_.Path -and ($_.Path -ieq $ExePath)
  } | ForEach-Object {
    Write-UpdateLog "stopping $($_.Id) before copy"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    Wait-Process -Id $_.Id -Timeout 10 -ErrorAction SilentlyContinue
  }
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

  Start-Process -FilePath $ExePath -WorkingDirectory $ResolvedAppDir
  Write-UpdateLog "app restarted | exe=$ExePath"
} catch {
  Write-UpdateLog ("update failed: " + $_.Exception.Message)
  # cap nhat hong thi van mo lai app (ban cu hoac ban da chep duoc), khong de nguoi dung mat app
  try {
    $Fallback = Join-Path $AppDir $ExeName
    if (Test-Path $Fallback) {
      Start-Process -FilePath $Fallback -WorkingDirectory $AppDir
      Write-UpdateLog "app restarted after failed update"
    }
  } catch {}
  throw
}
