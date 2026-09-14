# Registers the CryptoForge paper engine as a daily Windows scheduled task.
# Run from an ordinary (non-admin) PowerShell:  powershell -ExecutionPolicy Bypass -File paper\setup_task.ps1
#
# Trigger time is LOCAL. India (IST, UTC+5:30, no DST) -> 05:36 IST == 00:06 UTC.

param(
    [string]$At = '05:36',
    [string]$TaskName = 'CryptoForge Paper Engine'
)

$ErrorActionPreference = 'Stop'

$paperDir = $PSScriptRoot
$root = Split-Path -Parent $paperDir
$bat = Join-Path $paperDir 'run_daily.bat'

if (-not (Test-Path $bat)) { throw "run_daily.bat not found at $bat" }

$action = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Force `
    -Description 'Daily rebalance of the CryptoForge paper-trading account. 05:36 IST = 00:06 UTC.' | Out-Null

Write-Output "Registered task '$TaskName'."
Write-Output "  runs at      : $At local (India)  ==  00:06 UTC"
Write-Output "  command      : $bat"
Write-Output "  working dir  : $root"
Write-Output ""
Write-Output "Next scheduled run:"
Get-ScheduledTaskInfo -TaskName $TaskName | Select-Object TaskName, NextRunTime, LastRunTime, LastTaskResult | Format-List
Write-Output "To run it immediately:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Output "To remove it        :  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
