$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $Python)) {
  $Python = Join-Path $Root ".venv\Scripts\python.exe"
}
if (-not (Test-Path $Python)) {
  $message = "Missing Python virtual environment. Run: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
  Set-Content -Path (Join-Path $Root "voice-mic-crash.log") -Value $message -Encoding UTF8
  throw $message
}

# WMI (Get-CimInstance) doi khi tra loi "Call cancelled": thu lai vai lan, khong duoc thi dung cach du phong.
function Get-ProcessList {
  for ($attempt = 1; $attempt -le 3; $attempt++) {
    try {
      return @(Get-CimInstance Win32_Process -ErrorAction Stop)
    } catch {
      Start-Sleep -Milliseconds 400
    }
  }
  return $null
}

$processes = Get-ProcessList
$stopIds = @()
if ($null -ne $processes) {
  # Ban mic cu chay bang trinh duyet, va moi ban VoiNoi / Vietnamese Voice Mic dang chay: tat de chi con mot ban.
  $stopIds = $processes |
    Where-Object {
      (
        $_.Name -match '^(python|chrome|msedge)\.exe$' -and (
          $_.CommandLine -like '*voice_drop_server*' -or
          $_.CommandLine -like '*127.0.0.1:8877*' -or
          $_.CommandLine -like '*VI Mic Drop*' -or
          $_.CommandLine -like '*VietnameseVoiceMic*chrome-profile*'
        )
      ) -or (
        $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like '*voice_mic_icon.py*'
      ) -or (
        $_.Name -eq 'VietnameseVoiceMic.exe' -or $_.Name -eq 'VoiNoi.exe'
      )
    } |
    ForEach-Object { $_.ProcessId }
} else {
  # Du phong khi WMI loi: PID ban dang chay nam trong voice-mic.lock, cong them ban .exe theo ten.
  $lockFile = Join-Path $Root "voice-mic.lock"
  if (Test-Path $lockFile) {
    $lockPid = 0
    if ([int]::TryParse((Get-Content $lockFile -Raw -ErrorAction SilentlyContinue), [ref]$lockPid) -and $lockPid -gt 0) {
      $stopIds += $lockPid
    }
  }
  $stopIds += @(Get-Process -Name VoiNoi, VietnameseVoiceMic -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
}
$stopIds | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
$stopIds | ForEach-Object { Wait-Process -Id $_ -Timeout 5 -ErrorAction SilentlyContinue }

$stdoutLog = Join-Path $Root "voice-mic-start.log"
$stderrLog = Join-Path $Root "voice-mic-crash.log"
foreach ($logPath in @($stdoutLog, $stderrLog)) {
  $cleared = $false
  for ($attempt = 1; $attempt -le 10; $attempt++) {
    try {
      Set-Content -Path $logPath -Value "" -Encoding UTF8
      $cleared = $true
      break
    } catch [System.IO.IOException] {
      Start-Sleep -Milliseconds 250
    }
  }
  if (-not $cleared) {
    throw "Could not prepare log file after waiting: $logPath"
  }
}
$env:PYTHONWARNINGS = "ignore"
$pythonArgs = @(
  "-X", "utf8",
  "-W", "ignore",
  ".\voice_mic_icon.py"
)

Start-Process -FilePath $Python `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -ArgumentList $pythonArgs `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog
