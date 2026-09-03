<#
.SYNOPSIS
  SessionStart probe: tell Claude when this folder is not set up yet.

.DESCRIPTION
  Wired as a SessionStart hook in .claude/settings.json (the tester copy
  ships it): whatever this prints lands in Claude's context at the start of
  every session, so a brand-new user opens the folder and Claude offers to
  set it up -- they never have to know a setup skill exists.

  Discipline (same as the statusline reader): prints NOTHING when the
  environment is healthy -- silence is the healthy path -- never throws,
  never blocks, needs nothing but PowerShell itself. It must work on the
  machine where nothing else does, because that machine is the whole point.
#>
$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot

$missing = @()
if (-not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) {
    $missing += 'the Python environment (.venv)'
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    $missing += 'ffmpeg'
}
if (-not (Get-Command py -ErrorAction SilentlyContinue) -and
    -not (Get-Command python -ErrorAction SilentlyContinue)) {
    $missing += 'Python'
}

if ($missing.Count -gt 0) {
    Write-Output ("KitCut setup probe: this folder is NOT set up yet (missing: " +
        ($missing -join ', ') + "). Before doing anything else, use the " +
        "'setup' skill and offer to set the machine up -- the user only " +
        "approves; never hand them a command to type. If they asked for " +
        "something else first, explain that nothing renders until setup " +
        "runs, and do setup first.")
}
exit 0
