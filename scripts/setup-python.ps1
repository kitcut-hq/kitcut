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

.PARAMETER Recreate
  Delete .venv and rebuild it from scratch. The answer when the venv exists
  but is on the wrong Python version, or is broken beyond pip check's repair.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/setup-python.ps1 -Recreate
#>
[CmdletBinding()]
param([switch]$Recreate)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
# Everything below deletes and writes relative to $root; prove it is the repo
# before touching anything (a stray copy of this script would otherwise aim
# Remove-Item at whatever directory happens to sit above it).
if (-not (Test-Path (Join-Path $root 'requirements.txt'))) {
    throw "no requirements.txt in $root -- this script must live in the repo's scripts/ directory"
}
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
    try { Remove-Item -Recurse -Force '.venv' -ErrorAction Stop }
    catch { throw ".venv is held open (an editor or python.exe?) -- close it and re-run: $_" }
    if (Test-Path '.venv') {
        # a half-deleted venv whose python.exe survived would be taken for
        # healthy by the "already present" branch below
        throw '.venv survived deletion -- something still holds part of it open'
    }
}
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'the "py" launcher is not installed -- install Python 3.13 from python.org (keep "py launcher" checked), then re-run'
    }
    & py -3.13 -E -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'could not create .venv on Python 3.13' }
    Write-Host '  created'
} else {
    Write-Host '  already present'
}
$py = Join-Path $root '.venv\Scripts\python.exe'
# An old .venv on another Python version passes the existence check but breaks
# every compiled extension; refuse it rather than installing into it.
& $py -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)"
if ($LASTEXITCODE -ne 0) { throw '.venv is not Python 3.13 -- re-run with -Recreate' }

Write-Host '== 3. dependencies ==' -ForegroundColor Cyan
& $py -m pip install --quiet --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw 'upgrading pip/setuptools/wheel failed' }
& $py -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'dependency install failed' }
# pip's resolver ignores pre-existing installs it did not make; this catches
# the gaps left behind if the venv was ever built with PYTHONPATH set.
# NOTE deliberately no 2>&1: in PowerShell 5.1 redirecting a native exe's
# stderr wraps each line in an ErrorRecord, and under
# $ErrorActionPreference='Stop' pip's routine upgrade chatter would abort the
# whole script. Exit code, not output text, decides whether check passed.
$broken = & $py -m pip check
if ($LASTEXITCODE -ne 0) {
    Write-Host '  pip check reports:' -ForegroundColor Yellow
    $broken | ForEach-Object { Write-Host "    $_" }
    # both message forms: "requires X, which is not installed" and
    # "has requirement X>=1, but you have X 0.9"
    $names = $broken | Select-String -Pattern 'require(?:s|ment) ([A-Za-z0-9_.\-]+)' -AllMatches |
        ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } |
        Sort-Object -Unique
    if ($names) {
        Write-Host "  repairing: $($names -join ', ')" -ForegroundColor Yellow
        # -c requirements.txt: a repair must respect the pins -- an unpinned
        # install here once risked stomping numpy, which av/ctranslate2 are
        # ABI-sensitive to
        & $py -m pip install --quiet -c requirements.txt @($names)
    }
    & $py -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw 'pip check still fails -- re-run with -Recreate for a clean rebuild'
    }
}

Write-Host '== 4. verify ==' -ForegroundColor Cyan
& $py -X utf8 (Join-Path $PSScriptRoot 'check-env.py')
exit $LASTEXITCODE
