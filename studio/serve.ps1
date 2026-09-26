<#
Sketch Studio on this machine, reachable from outside through a Cloudflare quick tunnel.

    powershell -ExecutionPolicy Bypass -File studio\serve.ps1              start (or restart) both
    powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -Restart     restart the server only
                                                                           (the tunnel and its URL stay)
    powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -Release     ship: snapshot tag studio-stable
                                                                           (studio\release.py), then -Restart
    powershell -ExecutionPolicy Bypass -File studio\serve.ps1 -Stop        stop both
    add -Dev to run the working tree itself instead of the current release

The server runs from the current release (STUDIO_HOME\releases\<sha>, see release.py), so edits
in this working tree never reach a film being made; -Dev (or no release built yet) runs the
working tree. Its films, logs and Claude sessions live in STUDIO_HOME (default: kitcut-studio
next to this checkout); its keys stay in this checkout's .env.

A restart is gentle: the old server is asked to drain -- it takes no new films and finishes the
ones being made (up to -DrainMinutes, default 20) -- and films still waiting in its queue are made
by the new one. Then it starts studio/server.py on 127.0.0.1 and, unless restarting, `cloudflared
tunnel --url` in front of it, both hidden, and records the public https://<random>.trycloudflare.com
URL in STUDIO_HOME\url.txt and in MongoDB (kitcut.studio_hosts), where the public site
(kitcut-hq/sketch-studio on Vercel) looks it up. A quick tunnel gets a NEW random URL every time it
starts; the site follows it through the database, so nothing needs redeploying. -Stop marks the
studio offline there. Logs: STUDIO_HOME\server.log / .err and tunnel.log.
#>
param([switch]$Stop, [switch]$Restart, [switch]$ServerOnly, [switch]$Release, [switch]$Dev,
      [string]$Ref = 'studio-stable', [int]$Port = 8765, [int]$DrainMinutes = 20)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$studioHome = if ($env:STUDIO_HOME) { $env:STUDIO_HOME } else { Join-Path (Split-Path $repo -Parent) 'kitcut-studio' }
New-Item -ItemType Directory -Force $studioHome | Out-Null
$Restart = $Restart -or $ServerOnly -or $Release
$py = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
# what the server and everything it starts reads: where films live, the keys, the working tree
$env:STUDIO_HOME = $studioHome
$env:STUDIO_REPO = $repo
$env:STUDIO_ENV_FILE = Join-Path $repo '.env'

function Get-Token {
    $line = Get-Content $env:STUDIO_ENV_FILE -ErrorAction SilentlyContinue | Where-Object { $_ -match '^\s*STUDIO_TOKEN\s*=' } | Select-Object -Last 1
    if ($line) { return ($line -split '=', 2)[1].Trim().Trim('"').Trim("'") }
    return ''
}

function Drain {
    # ask a running server to finish what it is making, then let it go
    try { $h = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 3 } catch { return }
    if (-not $h.running) { return }
    try {
        Invoke-RestMethod -Method Post "http://127.0.0.1:$Port/api/admin/drain" -TimeoutSec 5 `
            -Headers @{ Authorization = "Bearer $(Get-Token)" } | Out-Null
    } catch { Write-Warning "could not ask the server to drain: $_"; return }
    $until = (Get-Date).AddMinutes($DrainMinutes)
    while ((Get-Date) -lt $until) {
        try { $h = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 3 } catch { return }
        if (-not $h.running) { return }
        "  draining: $($h.running) film(s) still being made..."
        Start-Sleep -Seconds 10
    }
    Write-Warning "films still running after $DrainMinutes min; stopping anyway (they will be marked interrupted)"
}

function Stop-Studio([switch]$KeepTunnel) {
    Get-CimInstance Win32_Process | Where-Object {
        ((-not $KeepTunnel) -and $_.Name -eq 'cloudflared.exe' -and $_.CommandLine -like "*127.0.0.1:$Port*") -or
        ($_.Name -like 'python*.exe' -and $_.CommandLine -like '*studio*server.py*')
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

# the public site finds the tunnel through MongoDB (kitcut.studio_hosts); say when it goes away
function Announce([string]$what) {
    & $py -X utf8 "$repo\studio\agent.py" --announce $what
    if ($LASTEXITCODE) { Write-Warning 'could not tell the public site (MongoDB); it will say the studio is offline' }
}

if ($Release) {
    & $py -X utf8 "$repo\studio\release.py" --ref $Ref
    if ($LASTEXITCODE) { throw 'the release was not made current; the running server is untouched' }
}

# which code to run: the current release, or (-Dev, or none built yet) this working tree
$code = $repo
$cur = Join-Path $studioHome 'releases\current'
if (-not $Dev -and (Test-Path $cur)) {
    $code = Join-Path $studioHome ('releases\' + (Get-Content $cur -TotalCount 1).Trim())
    if (-not (Test-Path "$code\studio\server.py")) { throw "the current release is missing: $code" }
}

if (-not $Stop) { Drain }
Stop-Studio -KeepTunnel:$Restart
if ($Stop) { Announce 'off'; 'Sketch Studio stopped.'; return }

Start-Process -FilePath $py -ArgumentList '-X', 'utf8', "`"$code\studio\server.py`"", '--port', $Port `
    -WorkingDirectory $code -WindowStyle Hidden `
    -RedirectStandardOutput "$studioHome\server.log" -RedirectStandardError "$studioHome\server.err"
$up = $false
for ($i = 0; $i -lt 60 -and -not $up; $i++) {
    Start-Sleep -Milliseconds 500
    try { $up = (Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2).ok } catch { }
}
if (-not $up) { throw "the server did not start; see $studioHome\server.err" }
$ver = (Invoke-RestMethod "http://127.0.0.1:$Port/api/health").release
if ($Restart) {
    "Sketch Studio server restarted (code $ver); tunnel unchanged: $(Get-Content "$studioHome\url.txt" -ErrorAction SilentlyContinue)"
    return
}

$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) { $cf = 'C:\Program Files (x86)\cloudflared\cloudflared.exe' }
if (-not (Test-Path $cf)) { throw 'cloudflared not found: winget install --id Cloudflare.cloudflared' }
Remove-Item "$studioHome\tunnel.log" -ErrorAction SilentlyContinue
Start-Process -FilePath $cf -ArgumentList 'tunnel', '--no-autoupdate', '--url', "http://127.0.0.1:$Port" `
    -WindowStyle Hidden -RedirectStandardError "$studioHome\tunnel.log" -RedirectStandardOutput "$studioHome\tunnel.out"
$url = $null
for ($i = 0; $i -lt 90 -and -not $url; $i++) {
    Start-Sleep -Milliseconds 500
    $m = Select-String -Path "$studioHome\tunnel.log" -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($m) { $url = $m.Matches[0].Value }
}
if (-not $url) { throw "no tunnel URL after 45 s; see $studioHome\tunnel.log" }
Set-Content -Path "$studioHome\url.txt" -Value $url -Encoding ascii
Announce $url
"Sketch Studio: $url  (code $ver)"
"  local:  http://127.0.0.1:$Port"
"  films:  $studioHome\projects"
"  token:  STUDIO_TOKEN in $repo\.env"
