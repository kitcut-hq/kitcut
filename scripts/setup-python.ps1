<#
.SYNOPSIS
  Build (or repair) the project's Python environment. Idempotent -- safe to
  re-run any time something looks wrong.

.DESCRIPTION
  Three things, in this order, because the order matters:

  1. Clear PYTHONPATH -- from this process AND from the user's persisted
     environment. A machine-wide PYTHONPATH aimed at another Python's
     site-packages makes 3.13 load 3.11's compiled extensions, which shows up
     as "DLL load failed" or "numpy.core.multiarray failed to import". A venv
     does not shield you from it.
  2. Create .venv on Python 3.13.
  3. Install requirements.txt *with PYTHONPATH already gone*. This step is the
     one people get wrong: if pip can still see the foreign site-packages it
     marks transitive dependencies as already satisfied and skips them, and
     you get a venv that is quietly missing yaml and idna.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1
#>
[CmdletBinding()]
param([switch]$Recreate)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host '== 1. PYTHONPATH ==' -ForegroundColor Cyan
$persisted = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'User')
if ($persisted) {
    Write-Host "  removing persisted User PYTHONPATH: $persisted" -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path temp | Out-Null
    Set-Content -Path 'temp\pythonpath.removed.txt' -Value $persisted -Encoding utf8
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $null, 'User')
} else {
    Write-Host '  persisted User PYTHONPATH: already clear'
}
# Also clear it here, or step 3 inherits it and pip skips dependencies.
$env:PYTHONPATH = $null
Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue

Write-Host '== 2. .venv ==' -ForegroundColor Cyan
if ($Recreate -and (Test-Path '.venv')) {
    Write-Host '  -Recreate: deleting the existing .venv'
    Remove-Item -Recurse -Force '.venv'
}
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & py -3.13 -E -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'could not create .venv on Python 3.13' }
    Write-Host '  created'
} else {
    Write-Host '  already present'
}
$py = Join-Path $root '.venv\Scripts\python.exe'

Write-Host '== 3. dependencies ==' -ForegroundColor Cyan
& $py -m pip install --quiet --upgrade pip setuptools wheel
& $py -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'dependency install failed' }
# pip's resolver ignores pre-existing installs it did not make; this catches
# the gaps left behind if the venv was ever built with PYTHONPATH set.
$broken = & $py -m pip check 2>&1
if ($broken -notmatch 'No broken requirements') {
    Write-Host "  repairing: $broken" -ForegroundColor Yellow
    $broken | Select-String -Pattern 'requires ([a-zA-Z0-9_.\-]+),' -AllMatches |
        ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } |
        Sort-Object -Unique | ForEach-Object { & $py -m pip install --quiet $_ }
    & $py -m pip check
}

Write-Host '== 4. verify ==' -ForegroundColor Cyan
& $py -X utf8 (Join-Path $PSScriptRoot 'check-env.py')
exit $LASTEXITCODE
