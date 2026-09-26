$ErrorActionPreference = "Stop"
$Startup = [Environment]::GetFolderPath("Startup")
foreach ($Name in @("VoiNoi.lnk", "Vietnamese Voice Mic.lnk")) {
  $Link = Join-Path $Startup $Name
  if (Test-Path $Link) {
    Remove-Item $Link -Force
    Write-Host "Removed startup shortcut:" $Link
  }
}
