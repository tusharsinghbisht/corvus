param([Parameter(Mandatory=$true)][string]$Campaign)
# Only the three pinned, reviewed Atomic tests below. No prerequisite installation.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$c = Get-Content -LiteralPath $Campaign -Raw | ConvertFrom-Json
if ($c.run_id -notmatch '^CORVUS-ART-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}$') { throw 'Invalid run ID' }
if ($env:COMPUTERNAME -ne $c.expected_computer_name) { throw 'Wrong endpoint' }
$base = Join-Path 'C:\ProgramData\CorvusLab' $c.run_id
if (Test-Path -LiteralPath $base) { throw 'Refusing to overwrite an existing campaign' }
New-Item -ItemType Directory -Path $base | Out-Null
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $base /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Private artifact ACL setup failed' }
$allowed = @{
 '66703791-c902-4560-8770-42b8a91f7667' = "systeminfo`nreg query HKLM\SYSTEM\CurrentControlSet\Services\Disk\Enum"
 'aab580c7-cc30-4a7c-b5a9-46a29066b022' = 'whoami /all'
 'a538de64-1c74-46ed-aa60-b995ed302598' = 'powershell.exe -e  JgAgACgAZwBjAG0AIAAoACcAaQBlAHsAMAB9ACcAIAAtAGYAIAAnAHgAJwApACkAIAAoACIAVwByACIAKwAiAGkAdAAiACsAIgBlAC0ASAAiACsAIgBvAHMAdAAgACcASAAiACsAIgBlAGwAIgArACIAbABvACwAIABmAHIAIgArACIAbwBtACAAUAAiACsAIgBvAHcAIgArACIAZQByAFMAIgArACIAaAAiACsAIgBlAGwAbAAhACcAIgApAA=='
}
if ($c.tests.Count -ne 3 -or $c.rounds -lt 1 -or $c.rounds -gt 3) { throw 'Unsupported campaign scope' }
foreach ($test in $c.tests) {
 if (-not $allowed.ContainsKey($test.guid) -or $test.command.Replace("`r",'').Trim() -cne $allowed[$test.guid]) { throw 'Unreviewed command refused' }
}
$channels = @('Microsoft-Windows-Sysmon/Operational','Microsoft-Windows-PowerShell/Operational','Security','System','Application')
$before = @(Get-Service Sysmon64,WazuhSvc | Select-Object Name,Status)
if (@($before | Where-Object { $_.Status -ne 'Running' }).Count) { throw 'Required security telemetry is not running' }
$start = [DateTime]::UtcNow
$records = New-Object System.Collections.ArrayList
function Save-Manifest {
 $m = @{schema_version='0.1';run_id=$c.run_id;computer_name=$env:COMPUTERNAME;runner_pid=$PID;start_utc=$start.ToString('o');updated_utc=[DateTime]::UtcNow.ToString('o');framework='Atomic Red Team';upstream_commit=$c.upstream_commit;services_before=$before;records=@($records);simulation_authorized=$true;response_executed=$false;limitations=@('Authorized harmless technique emulation, not evidence of compromise.','SSH/controller processes and collection activity are present in raw telemetry.','Each reviewed command line runs separately to preserve its own exit status. No prerequisite download or security-policy change.')}
 $m | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $base 'execution.json') -Encoding UTF8
}
Save-Manifest
try {
 for ($round=1;$round -le $c.rounds;$round++) {
  $control = "powershell.exe -NoProfile -NonInteractive -Command `"Write-Output '$($c.run_id)-CONTROL-$round'; Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version`""
  $steps = @(@{guid='control';technique='administrative-control';name='Read-only inventory control';command=$control}) + @($c.tests)
  foreach ($test in $steps) {
   $lineNumber=0
   foreach ($line in $test.command.Replace("`r",'').Trim().Split("`n")) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $lineNumber++
    $key = "r$round-$($test.guid)-$lineNumber"
    $started = [DateTime]::UtcNow
    $out = Join-Path $base ($key+'.stdout.txt')
    $err = Join-Path $base ($key+'.stderr.txt')
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = "$env:SystemRoot\System32\cmd.exe"
    $info.Arguments = '/d /s /c "'+$line+'"'
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $info
    if (-not $p.Start()) { throw 'Reviewed process did not start' }
    $stdoutTask = $p.StandardOutput.ReadToEndAsync()
    $stderrTask = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit(90000)) { throw 'Reviewed command timed out; stop and inspect this process manually' }
    $stdoutTask.Result | Set-Content -LiteralPath $out -Encoding UTF8
    $stderrTask.Result | Set-Content -LiteralPath $err -Encoding UTF8
    $record = @{id=$key;round=$round;guid=$test.guid;technique=$test.technique;name=$test.name;command=$line;cmd_pid=$p.Id;start_utc=$started.ToString('o');end_utc=[DateTime]::UtcNow.ToString('o');exit_code=$p.ExitCode;stdout=[IO.Path]::GetFileName($out);stderr=[IO.Path]::GetFileName($err);role=$(if ($test.guid -eq 'control') {'control'} else {'technique_emulation'})}
    [void]$records.Add($record)
    Save-Manifest
    if ($p.ExitCode -ne 0) { throw 'Reviewed command failed; campaign stopped' }
    if (@(Get-Service Sysmon64,WazuhSvc | Where-Object Status -ne 'Running').Count) { throw 'Security telemetry health changed; campaign stopped' }
    Start-Sleep -Seconds 3
   }
  }
 }
} finally { Save-Manifest }
$end = [DateTime]::UtcNow
$filterStart = $start.AddMinutes(-2).ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ')
$filterEnd = $end.AddSeconds(5).ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ')
Start-Sleep -Seconds 6
$exports = @()
foreach ($channel in $channels) {
 $name = $channel.Replace('/','_')+'.evtx'
 $destination = Join-Path $base $name
 & wevtutil.exe epl $channel $destination "/q:*[System[TimeCreated[@SystemTime>='$filterStart' and @SystemTime<='$filterEnd']]]" /ow:false
 if ($LASTEXITCODE -ne 0) { throw 'Native event export failed; do not retire endpoint yet' }
 $eventCount = [System.Diagnostics.Eventing.Reader.EventLogSession]::GlobalSession.GetLogInformation($destination,[System.Diagnostics.Eventing.Reader.PathType]::FilePath).RecordCount
 $exports += @{channel=$channel;file=$name;records=$eventCount;bytes=(Get-Item -LiteralPath $destination).Length;sha256=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLower()}
}
# Preserve retained native history before endpoint retirement, not just indexed archives.
$history = @()
foreach ($channel in $channels) {
 $destination = Join-Path $base ('historical-'+$channel.Replace('/','_')+'.evtx')
 & wevtutil.exe epl $channel $destination /ow:false
 if ($LASTEXITCODE -ne 0) { throw 'Historical native export failed; do not retire endpoint yet' }
 if ((Get-Item -LiteralPath $destination).Length -gt 268435456) { throw 'Native file exceeds reviewed export bound; inspect before retirement' }
 $count = [System.Diagnostics.Eventing.Reader.EventLogSession]::GlobalSession.GetLogInformation($destination,[System.Diagnostics.Eventing.Reader.PathType]::FilePath).RecordCount
 $history += @{channel=$channel;file=[IO.Path]::GetFileName($destination);records=$count;bytes=(Get-Item -LiteralPath $destination).Length;sha256=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLower()}
}
$history | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $base 'retained-native-history.json') -Encoding UTF8
$rulesHash = $null
try { $rules=(Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Services\SysmonDrv\Parameters' -Name Rules).Rules; if ($rules -is [byte[]]) { $rulesHash=([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($rules))).Replace('-','').ToLower() } } catch { }
@{end_utc=$end.ToString('o');native_window_start=$filterStart;native_window_end=$filterEnd;exports=$exports;services_after=@(Get-Service Sysmon64,WazuhSvc | Select-Object Name,Status);sysmon_registry_rules_sha256=$rulesHash;sysmon_hash_note='Hash of registry Rules bytes if readable; no configuration changes.'} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $base 'native-export.json') -Encoding UTF8
$files = @(Get-ChildItem -LiteralPath $base -File | ForEach-Object { @{file=$_.Name;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()} })
$files | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $base 'SHA256SUMS.json') -Encoding UTF8
Write-Output ('CAMPAIGN_CAPTURED '+$c.run_id+' records='+$records.Count+' native_exports='+$exports.Count)
