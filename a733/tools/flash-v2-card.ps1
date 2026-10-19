# One-off guarded writer for the removable card inventoried on this PC.
# Must run elevated. It never cleans a disk or formats a volume.
param([ValidateSet('v2', 'v3')][string]$Version = 'v2')
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$imagePath = Join-Path $projectPath "build\ios-a733-stage0-auto-$Version-sd.img"
$statusPath = Join-Path $projectPath "build\flash-$Version-status.json"
$expectedHash = @{
    v2 = 'B1F3A318F062FAFDA161C4A27E41D7FD73DFDBBA11425B60E4FB14AF0DE47C83'
    v3 = '6B461666E2BF37B976F641CFF09D08229AB6A0DD032F3C25CC76167FE901ACB3'
}[$Version]
$diskNumber = 1
$expectedSerial = '000000000819'
$expectedSize = 61891149824
$volumeHandles = @()
$deviceStream = $null
$backupPath = $null
$writeStarted = $false

function Assert-TargetCard {
    $disk = Get-Disk -Number $diskNumber
    if ($disk.IsBoot -or $disk.IsSystem -or $disk.IsReadOnly -or
        $disk.BusType -ne 'USB' -or $disk.Size -ne $expectedSize -or
        $disk.SerialNumber.Trim() -ne $expectedSerial -or
        $disk.FriendlyName.Trim() -ne 'Generic STORAGE DEVICE') {
        throw 'Disk identity/safety check failed. No write permitted.'
    }
    $partitions = @(Get-Partition -DiskNumber $diskNumber)
    if ($partitions.Count -ne 1 -or $partitions[0].Size -ne 33554432 -or
        $partitions[0].Offset -ne 33554432 -or $partitions[0].DriveLetter -ne 'D') {
        throw 'The expected D: 32-MiB diagnostic partition is not present.'
    }
    return $partitions
}

function Get-BytesHash([byte[]]$data) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($data))
}

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator rights are required for raw SD-card access.'
    }
    $partitions = @(Assert-TargetCard)
    $image = [IO.File]::ReadAllBytes($imagePath)
    if ($image.Length -ne 67108864 -or (Get-BytesHash $image) -ne $expectedHash) {
        throw 'Image size/hash does not match the selected verified image.'
    }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class CardVolumeControl {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool DeviceIoControl(SafeFileHandle handle, uint code,
        IntPtr input, uint inputSize, IntPtr output, uint outputSize,
        out uint returned, IntPtr overlapped);
}
'@
    foreach ($partition in $partitions) {
        $volumePath = '\\.\' + $partition.DriveLetter + ':'
        $handle = [IO.FileStream]::new($volumePath, [IO.FileMode]::Open,
            [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
        $volumeHandles += $handle
        [uint32]$returned = 0
        foreach ($control in @(0x00090018, 0x00090020)) {
            if (-not [CardVolumeControl]::DeviceIoControl($handle.SafeFileHandle,
                $control, [IntPtr]::Zero, 0, [IntPtr]::Zero, 0,
                [ref]$returned, [IntPtr]::Zero)) {
                throw "Volume lock/dismount failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
            }
        }
    }
    $null = Assert-TargetCard
    $deviceStream = [IO.FileStream]::new('\\.\PhysicalDrive1', [IO.FileMode]::Open,
        [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite, 1048576)
    $before = [byte[]]::new($image.Length)
    $deviceStream.ReadExactly($before, 0, $before.Length)
    $backupDirectory = Join-Path $projectPath 'backups'
    $null = New-Item -ItemType Directory -Path $backupDirectory -Force
    $backupPath = Join-Path $backupDirectory ("card1-first64MiB-before-$Version-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.bin')
    $backupStream = [IO.FileStream]::new($backupPath, [IO.FileMode]::CreateNew)
    try { $backupStream.Write($before, 0, $before.Length); $backupStream.Flush($true) }
    finally { $backupStream.Dispose() }
    if ((Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash -ne (Get-BytesHash $before)) {
        throw 'Backup verification failed. Card not modified.'
    }
    $null = Assert-TargetCard
    $deviceStream.Position = 0
    $writeStarted = $true
    $deviceStream.Write($image, 0, $image.Length)
    $deviceStream.Flush($true)
    # Close and reopen the physical device before read-back verification.
    $deviceStream.Dispose()
    $deviceStream = [IO.FileStream]::new('\\.\PhysicalDrive1', [IO.FileMode]::Open,
        [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite, 1048576)
    $after = [byte[]]::new($image.Length)
    $deviceStream.ReadExactly($after, 0, $after.Length)
    $readbackHash = Get-BytesHash $after
    if ($readbackHash -ne $expectedHash) { throw 'Card read-back SHA256 mismatch.' }
    @{ success = $true; disk = $diskNumber; serial = $expectedSerial;
       writtenBytes = $image.Length; image = $imagePath; sha256 = $readbackHash;
       backup = $backupPath; backupSha256 = (Get-BytesHash $before);
       hardwareBootTested = $false } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
} catch {
    @{ success = $false; error = $_.Exception.Message; writeStarted = $writeStarted;
       backup = $backupPath } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
    exit 1
} finally {
    if ($null -ne $deviceStream) { $deviceStream.Dispose() }
    foreach ($handle in $volumeHandles) { $handle.Dispose() }
}
