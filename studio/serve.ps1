<#
Sketch Studio on this machine, reachable from outside through a Cloudflare quick tunnel.

    powershell -ExecutionPolicy Bypass -File studio\serve.ps1               start (or restart) both
    powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -ServerOnly   restart the server only;
                                                                            the tunnel and its URL stay
    powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -Stop         stop both

Starts studio/server.py on 127.0.0.1 and `cloudflared tunnel --url` in front of it, both as
hidden background processes, then prints the public https://<random>.trycloudflare.com URL
and writes it to temp\studio-url.txt and to MongoDB (kitcut.studio_hosts), where the public site
(kitcut-hq/sketch-studio on Vercel) looks it up. A quick tunnel gets a NEW random URL every time
it starts, and has no uptime guarantee; the site follows it through the database, so nothing
needs redeploying. -Stop marks the studio offline there.
Logs: temp\studio-server.log / .err and temp\studio-tunnel.log.
#>
param([switch]$Stop, [switch]$ServerOnly, [int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$temp = Join-Path $root 'temp'

function Stop-Studio([switch]$KeepTunnel) {
    Get-CimInstance Win32_Process | Where-Object {
        ((-not $KeepTunnel) -and $_.Name -eq 'cloudflared.exe' -and $_.CommandLine -like "*127.0.0.1:$Port*") -or
        ($_.Name -like 'python*.exe' -and $_.CommandLine -like '*studio*server.py*')
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
# the public site finds the tunnel through MongoDB (kitcut.studio_hosts); say when it goes away
function Announce([string]$what) {
    & $py -X utf8 "$root\studio\agent.py" --announce $what
    if ($LASTEXITCODE) { Write-Warning 'could not tell the public site (MongoDB); it will say the studio is offline' }
}

Stop-Studio -KeepTunnel:$ServerOnly
if ($Stop) { Announce 'off'; 'Sketch Studio stopped.'; return }

Start-Process -FilePath $py -ArgumentList '-X', 'utf8', "`"$root\studio\server.py`"", '--port', $Port `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput "$temp\studio-server.log" -RedirectStandardError "$temp\studio-server.err"
$up = $false
for ($i = 0; $i -lt 60 -and -not $up; $i++) {
    Start-Sleep -Milliseconds 500
    try { $up = (Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2).ok } catch { }
}
if (-not $up) { throw "the server did not start; see $temp\studio-server.err" }
if ($ServerOnly) {
    "Sketch Studio server restarted; tunnel unchanged: $(Get-Content "$temp\studio-url.txt" -ErrorAction SilentlyContinue)"
    return
}

$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) { $cf = 'C:\Program Files (x86)\cloudflared\cloudflared.exe' }
if (-not (Test-Path $cf)) { throw 'cloudflared not found: winget install --id Cloudflare.cloudflared' }
Remove-Item "$temp\studio-tunnel.log" -ErrorAction SilentlyContinue
Start-Process -FilePath $cf -ArgumentList 'tunnel', '--no-autoupdate', '--url', "http://127.0.0.1:$Port" `
    -WindowStyle Hidden -RedirectStandardError "$temp\studio-tunnel.log" -RedirectStandardOutput "$temp\studio-tunnel.out"
$url = $null
for ($i = 0; $i -lt 90 -and -not $url; $i++) {
    Start-Sleep -Milliseconds 500
    $m = Select-String -Path "$temp\studio-tunnel.log" -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($m) { $url = $m.Matches[0].Value }
}
if (-not $url) { throw "no tunnel URL after 45 s; see $temp\studio-tunnel.log" }
Set-Content -Path "$temp\studio-url.txt" -Value $url -Encoding ascii
Announce $url
"Sketch Studio: $url"
"  local:  http://127.0.0.1:$Port"
"  token:  STUDIO_TOKEN in $root\.env"
