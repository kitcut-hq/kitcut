<#
.SYNOPSIS
Import recent videos from an iPhone (or any MTP device) into the repo's sources/.

.DESCRIPTION
An iPhone connects as an MTP / Windows Portable Device, not a drive letter, so
Copy-Item and Get-ChildItem cannot see it. Everything here goes through the
Shell.Application COM namespace, which is the only supported way to read MTP
storage from PowerShell.

The device enumerates as a folder with ZERO items when the phone is locked or
has not granted "Trust This Computer". That is not an error you can retry past
in software -- the phone must be unlocked and trusted first. -WhatIf reports
this state plainly instead of copying nothing and claiming success.

A copy is finished when the destination's byte count STOPS MOVING, not when the
file appears. The shell creates the destination immediately and fills it over
the following minutes, so a Test-Path check passes on a partial copy -- and a
truncated video still probes cleanly, it just reports a shorter duration. The
final size is compared against the device's, and a mismatch is reported rather
than passed or failed silently, because iOS transcodes HEVC during transfer
when the phone's setting is "Automatic".

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts/import-iphone.ps1 -Days 1 -List
powershell -ExecutionPolicy Bypass -File scripts/import-iphone.ps1 -Days 1
powershell -ExecutionPolicy Bypass -File scripts/import-iphone.ps1 -DeviceName 'Pixel 5' -Days 60
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    # Only import items modified within this many days. 1 = today and yesterday.
    [int]$Days = 1,

    # Where to put them. Defaults to the repo's gitignored sources/ dir.
    # Resolved in the body: $PSScriptRoot is not populated in a param default
    # under Windows PowerShell 5.1.
    [string]$Destination,

    # Device name as shown under This PC.
    [string]$DeviceName = 'Apple iPhone',

    # Extensions to import.
    [string[]]$Extension = @('.mov', '.mp4', '.m4v'),

    # List what is on the device without copying.
    [switch]$List,

    # Give up on a file whose byte count has not moved for this many seconds.
    # This is a stall detector, not a size budget: a 1.5 GB take over MTP runs
    # for minutes, and any fixed overall deadline is wrong for some file.
    [double]$StallTimeout = 180,

    # How long the byte count must hold steady before the copy counts as done.
    [double]$StableSeconds = 4
)

$ErrorActionPreference = 'Stop'
$SHELL_THIS_PC = 17

if (-not $Destination) {
    $Destination = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) '..\sources'
}

function Get-MtpDevice {
    param([string]$Name)
    $shell = New-Object -ComObject Shell.Application
    $device = $shell.NameSpace($SHELL_THIS_PC).Items() |
        Where-Object { $_.Name -eq $Name }
    if (-not $device) {
        $seen = ($shell.NameSpace($SHELL_THIS_PC).Items() | ForEach-Object { $_.Name }) -join ', '
        throw "Device '$Name' not found under This PC. Saw: $seen"
    }
    return $device
}

# MTP folders must be walked; there is no recursive glob. Depth is bounded
# because DCIM is only ever device > storage > DCIM > 1xxAPPLE > files.
function Get-MtpFilesRecursive {
    param($Folder, [int]$Depth = 0)
    if ($Depth -gt 5) { return }
    foreach ($item in $Folder.Items()) {
        if ($item.IsFolder) {
            Get-MtpFilesRecursive -Folder $item.GetFolder -Depth ($Depth + 1)
        }
        else {
            $item
        }
    }
}

# MTP items do not expose LastWriteTime. ExtendedProperty is the reliable
# accessor; GetDetailsOf column indexes shift between Windows builds.
function Get-MtpDate {
    param($Item)
    foreach ($prop in 'System.DateModified', 'System.ItemDate', 'System.DateCreated') {
        try {
            $value = $Item.ExtendedProperty($prop)
            if ($value -is [datetime]) { return $value }
        }
        catch { }
    }
    return $null
}

$device = Get-MtpDevice -Name $DeviceName
$storages = @($device.GetFolder.Items())

if ($storages.Count -eq 0) {
    throw "'$DeviceName' exposes no storage at all. Reconnect the cable."
}

$totalItems = 0
foreach ($storage in $storages) { $totalItems += $storage.GetFolder.Items().Count }

if ($totalItems -eq 0) {
    Write-Host ''
    Write-Host "'$DeviceName' is mounted but exposes 0 items." -ForegroundColor Yellow
    Write-Host 'That means the phone is locked, or has not trusted this PC.' -ForegroundColor Yellow
    Write-Host ''
    Write-Host '  1. Unlock the phone (Face ID / passcode).'
    Write-Host '  2. If a "Trust This Computer?" prompt appears, tap Trust and'
    Write-Host '     re-enter the passcode.'
    Write-Host '  3. Keep it unlocked and re-run this script.'
    Write-Host ''
    Write-Host 'The driver is fine -- this is a consent state, not a fault.'
    exit 2
}

Write-Host "Scanning $DeviceName ..." -ForegroundColor Cyan
$all = foreach ($storage in $storages) { Get-MtpFilesRecursive -Folder $storage.GetFolder }

$cutoff = (Get-Date).Date.AddDays(-$Days)
$matches = @()
foreach ($item in $all) {
    $ext = [System.IO.Path]::GetExtension($item.Name)
    if ($Extension -notcontains $ext.ToLower()) { continue }
    $date = Get-MtpDate -Item $item
    if ($null -ne $date -and $date -lt $cutoff) { continue }
    $size = $null
    try { $size = $item.ExtendedProperty('System.Size') } catch { }
    $matches += [pscustomobject]@{
        Item = $item; Name = $item.Name; Date = $date; Size = $size
    }
}

if ($matches.Count -eq 0) {
    Write-Host "No videos newer than $($cutoff.ToString('yyyy-MM-dd')) found on the device." -ForegroundColor Yellow
    Write-Host "Scanned $($all.Count) files total."
    exit 0
}

Write-Host ''
Write-Host "Found $($matches.Count) video(s) modified since $($cutoff.ToString('yyyy-MM-dd')):"
foreach ($m in $matches) {
    $when = if ($m.Date) { $m.Date.ToString('yyyy-MM-dd HH:mm') } else { 'unknown date' }
    $mb = if ($m.Size) { '{0,8:N1} MB' -f ($m.Size / 1MB) } else { '   ? MB' }
    Write-Host ("  {0,-28} {1}  {2}" -f $m.Name, $when, $mb)
}
Write-Host ''

if ($List) { exit 0 }

$Destination = (New-Item -ItemType Directory -Force -Path $Destination).FullName
$shell = New-Object -ComObject Shell.Application
$destNs = $shell.NameSpace($Destination)
$failed = @()
$suspect = @()

foreach ($m in $matches) {
    $target = Join-Path $Destination $m.Name
    if (Test-Path $target) {
        Write-Host "  skip (exists): $($m.Name)" -ForegroundColor DarkGray
        continue
    }
    if (-not $PSCmdlet.ShouldProcess($m.Name, 'copy from device')) { continue }

    $expect = $m.Size
    $expectText = if ($expect) { '{0:N1} MB' -f ($expect / 1MB) } else { 'unknown size' }
    Write-Host "  copying $($m.Name) ($expectText) ..."
    # 16 = yes to all, 4 = no progress dialog. MTP honours these inconsistently,
    # so completion is confirmed by watching the file rather than trusting it.
    $destNs.CopyHere($m.Item, 16 -bor 4)

    # The shell CREATES the destination file immediately and fills it over the
    # following minutes, so Test-Path is true almost at once -- polling on it
    # reports success on a partial copy. A 1.5 GB take truncated this way looks
    # fine to ffprobe (it just reports a shorter duration) and silently corrupts
    # everything downstream. Wait for the byte count to stop moving instead.
    $lastSize = -1
    $stableFor = 0.0
    $elapsed = 0.0
    $done = $false
    while ($elapsed -lt $StallTimeout) {
        Start-Sleep -Milliseconds 500
        $elapsed += 0.5
        $size = if (Test-Path $target) { (Get-Item $target).Length } else { 0 }

        if ($size -ne $lastSize) {
            $stableFor = 0.0
            $lastSize = $size
            if ($size -gt 0) {
                $pct = if ($expect) { ' ({0,5:N1}%)' -f (100.0 * $size / $expect) } else { '' }
                Write-Host ("`r    {0,8:N1} MB{1}   " -f ($size / 1MB), $pct) -NoNewline
            }
            continue
        }

        # Size held steady. Zero bytes means the transfer has not begun; give it
        # the same grace, since MTP can take a while to spin up on a big file.
        $stableFor += 0.5
        if ($size -gt 0 -and $stableFor -ge $StableSeconds) { $done = $true; break }
        if ($stableFor -ge $StallTimeout) { break }
    }

    Write-Host ''
    $final = if (Test-Path $target) { (Get-Item $target).Length } else { 0 }

    if (-not $done -or $final -eq 0) {
        Write-Host "    STALLED after $elapsed s at $final bytes" -ForegroundColor Red
        $failed += $m.Name
        continue
    }

    if ($expect -and $final -ne $expect) {
        # iOS transcodes HEVC on the fly when the phone's transfer setting is
        # "Automatic", so a mismatch is not automatically a truncation. Say what
        # was seen and let the caller judge, rather than passing or failing it
        # silently.
        $delta = 100.0 * $final / $expect
        Write-Host ("    done, but {0:N1} MB != {1:N1} MB on device ({2:N1}%)" -f `
                    ($final / 1MB), ($expect / 1MB), $delta) -ForegroundColor Yellow
        Write-Host '    Either the device transcoded it, or the copy is short. Check the duration.' -ForegroundColor Yellow
        $suspect += $m.Name
    }
    else {
        Write-Host ("    done ({0:N1} MB)" -f ($final / 1MB)) -ForegroundColor Green
    }
}

Write-Host ''
Write-Host "Imported into: $Destination" -ForegroundColor Cyan

if ($suspect.Count -gt 0) {
    Write-Host ''
    Write-Host "Size mismatch, verify before using: $($suspect -join ', ')" -ForegroundColor Yellow
}
if ($failed.Count -gt 0) {
    Write-Host ''
    Write-Host "FAILED: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
