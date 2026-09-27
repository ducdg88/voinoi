# Dat lich Loop-VoiNoi: chay moi 3 gio, chay bu neu may tat dung gio.
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Script = Join-Path $Root "kaizen\voinoi_kaizen.py"
$action = New-ScheduledTaskAction -Execute $Python -Argument "-X utf8 `"$Script`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours(8) -RepetitionInterval (New-TimeSpan -Hours 3)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "DG Loop-VoiNoi Kaizen" -Action $action -Trigger $trigger -Settings $settings -Description "Vong lap tu cai tien VoiNoi (kaizen\voinoi_kaizen.py)" -Force | Out-Null
Get-ScheduledTask -TaskName "DG Loop-VoiNoi Kaizen" | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
