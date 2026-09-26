$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
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

$Shell = New-Object -ComObject WScript.Shell
$Places = @(
  [Environment]::GetFolderPath("Desktop"),
  (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs")
)
foreach ($Place in $Places) {
  $Link = Join-Path $Place "VoiNoi.lnk"
  $Shortcut = $Shell.CreateShortcut($Link)
  $Shortcut.TargetPath = $Target
  $Shortcut.WorkingDirectory = $Root
  $Shortcut.WindowStyle = 7
  if (Test-Path $Icon) {
    $Shortcut.IconLocation = "$Icon,0"
  }
  $Shortcut.Description = "VoiNoi: noi tieng Viet thanh chu"
  $Shortcut.Save()
  Write-Host "Shortcut:" $Link
}
