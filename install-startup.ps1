$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Startup = [Environment]::GetFolderPath("Startup")
$Link = Join-Path $Startup "VoiNoi.lnk"

$Exe = Join-Path $Root "VoiNoi.exe"
$Cmd = Join-Path $Root "Start VoiNoi.cmd"
$Icon = Join-Path $Root "assets\voinoi.ico"

if (Test-Path $Exe) {
  $Target = $Exe
} elseif (Test-Path $Cmd) {
  $Target = $Cmd
} else {
  throw "Cannot find VoiNoi.exe or Start VoiNoi.cmd in $Root"
}

# ban cu (Vietnamese Voice Mic) co the con shortcut khoi dong: bo di de khong chay hai ban
$OldLink = Join-Path $Startup "Vietnamese Voice Mic.lnk"
if (Test-Path $OldLink) {
  Remove-Item $OldLink -Force
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($Link)
$Shortcut.TargetPath = $Target
$Shortcut.WorkingDirectory = $Root
$Shortcut.WindowStyle = 7
if (Test-Path $Icon) {
  $Shortcut.IconLocation = "$Icon,0"
}
$Shortcut.Description = "Start VoiNoi in background"
$Shortcut.Save()

Write-Host "Installed startup shortcut:"
Write-Host $Link
