param([Parameter(Mandatory=$true)][string]$RunId)
# Read-only capture recovery: NEVER executes or reruns a test.
$ErrorActionPreference='Stop'
if ($RunId -notmatch '^CORVUS-ART-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}$') { throw 'Invalid run ID' }
$base=Join-Path 'C:\ProgramData\CorvusLab' $RunId
$m=Get-Content -LiteralPath (Join-Path $base 'execution.json') -Raw | ConvertFrom-Json
if ($m.run_id -ne $RunId -or $m.records.Count -ne 15 -or @($m.records | Where-Object {$null -eq $_.exit_code -or $_.exit_code -ne 0}).Count) { throw 'Incomplete reviewed executions; do not declare this dataset complete' }
if (Get-Process -Id $m.runner_pid -ErrorAction SilentlyContinue) { throw 'Original controller still running; inspect before finalizing' }
$channels=@('Microsoft-Windows-Sysmon/Operational','Microsoft-Windows-PowerShell/Operational','Security','System','Application')
$exports=@();$history=@()
foreach ($channel in $channels) {
 $name=$channel.Replace('/','_')+'.evtx'
 foreach ($historical in @($false,$true)) {
  $file=$(if ($historical) {'historical-'+$name} else {$name})
  $destination=Join-Path $base $file
  if (-not (Test-Path -LiteralPath $destination)) {
   if (-not $historical) { throw 'Missing campaign EVTX; inspect before recreating its time window' }
   & wevtutil.exe epl $channel $destination /ow:false
   if ($LASTEXITCODE -ne 0) { throw 'Historical export failed' }
  }
  if ((Get-Item -LiteralPath $destination).Length -gt 268435456) { throw 'Native file exceeds bound' }
  $info=[System.Diagnostics.Eventing.Reader.EventLogSession]::GlobalSession.GetLogInformation($destination,[System.Diagnostics.Eventing.Reader.PathType]::FilePath)
  $entry=@{channel=$channel;file=$file;records=$info.RecordCount;bytes=(Get-Item -LiteralPath $destination).Length;sha256=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLower()}
  if ($historical) {$history+=$entry} else {$exports+=$entry}
 }
}
$start=[DateTime]::Parse($m.start_utc).ToUniversalTime().AddMinutes(-2)
$end=[DateTime]::Parse($m.records[-1].end_utc).ToUniversalTime()
$rulesHash=$null
try { $rules=(Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Services\SysmonDrv\Parameters' -Name Rules).Rules; if ($rules -is [byte[]]) {$rulesHash=([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($rules))).Replace('-','').ToLower()} } catch {}
$after=@(Get-Service Sysmon64,WazuhSvc | Select-Object Name,Status)
if (@($after | Where-Object {$_.Status -ne 'Running'}).Count) {throw 'Security telemetry not healthy'}
$history | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $base 'retained-native-history.json') -Encoding UTF8
@{end_utc=$end.ToString('o');native_window_start=$start.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ');native_window_end=$null;native_window_note='Start matches the original query; its exact end was not persisted before controller interruption. EVTX records retain their own timestamps. end_utc is the last command end, not the native query end.';exports=$exports;services_after=$after;sysmon_registry_rules_sha256=$rulesHash;sysmon_hash_note='Registry Rules bytes if readable; no configuration change.';capture_recovery='Original SSH controller exceeded its wait while enumerating retained logs after all 15 commands completed successfully. Only that verified controller was stopped; this finalizer reads log metadata without rerunning tests.'} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $base 'native-export.json') -Encoding UTF8
$files=@(Get-ChildItem -LiteralPath $base -File | Where-Object {$_.Name -ne 'SHA256SUMS.json'} | ForEach-Object {@{file=$_.Name;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()}})
$files | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $base 'SHA256SUMS.json') -Encoding UTF8
Write-Output ('CAPTURE_FINALIZED '+$RunId+' files='+$files.Count)
