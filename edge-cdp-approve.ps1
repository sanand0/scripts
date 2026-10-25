# CDP auto-approval for the logged-in user's existing Edge profile.
# Run as a limited interactive task. Keep debugging bound to loopback.
$ErrorActionPreference = 'Stop'
$log = Join-Path (Split-Path -Parent $PSCommandPath) 'edge-cdp-approve.log'
$edge = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft\Edge\Application\msedge.exe'
if (!(Test-Path $edge)) { $edge = Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe' }
function Log($text) { Add-Content $log "$(Get-Date -Format o) $text" -Encoding UTF8 }
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$root = [Windows.Automation.AutomationElement]::RootElement
$children = [Windows.Automation.TreeScope]::Children
$desc = [Windows.Automation.TreeScope]::Descendants
$trueCondition = [Windows.Automation.Condition]::TrueCondition
$name = [Windows.Automation.AutomationElement]::NameProperty
$type = [Windows.Automation.AutomationElement]::ControlTypeProperty
$dialog = [Windows.Automation.PropertyCondition]::new($name,'Allow remote debugging?')
$allow = [Windows.Automation.AndCondition]::new(
    [Windows.Automation.PropertyCondition]::new($name,'Allow'),
    [Windows.Automation.PropertyCondition]::new($type,[Windows.Automation.ControlType]::Button))
$nextCheck = Get-Date
$lastLaunch = [datetime]::MinValue
$lastError = ''
Log "Started session $([Diagnostics.Process]::GetCurrentProcess().SessionId)"
while ($true) {
    try {
        $windows = $root.FindAll($children,$trueCondition)
        $count = 0
        foreach ($w in $windows) {
            if ($w.Current.ClassName -ne 'Chrome_WidgetWin_1') { continue }
            $proc = Get-Process -Id $w.Current.ProcessId -ErrorAction SilentlyContinue
            if (!$proc -or $proc.ProcessName -ne 'msedge') { continue }
            $count++
            $prompt = $w.FindFirst($desc,$dialog)
            if (!$prompt) { continue }
            $button = $prompt.FindFirst($desc,$allow)
            if (!$button) { $button = $w.FindFirst($desc,$allow) }
            if ($button) {
                $button.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
                Log 'Approved Edge remote debugging'
            }
        }
        if ((Get-Date) -ge $nextCheck) {
            $nextCheck = (Get-Date).AddSeconds(20)
            if (!$count -and (Test-Path $edge) -and (Get-Date) -ge $lastLaunch.AddSeconds(60)) {
                $lastLaunch = Get-Date
                Start-Process $edge -ArgumentList @('--new-window','about:blank')
                Log 'Opened neutral Edge window'
            }
        }
        $lastError = ''
    } catch {
        $msg = $_.Exception.GetType().Name + ': ' + $_.Exception.Message
        if ($msg -ne $lastError) { Log "Warning: $msg"; $lastError = $msg }
    }
    Start-Sleep -Seconds 2
}
