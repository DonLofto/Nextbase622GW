param(
    [Parameter(Mandatory=$true)][ValidateSet('Info','Ports')][string]$Action,
    [ValidatePattern('^[A-Za-z]:\\$')][string]$Volume
)
# Metadata only. Filesystem checking/ejection are separate checked host calls.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
try {
    if ($Action -eq 'Ports') {
        $Ports = @(Get-CimInstance Win32_SerialPort | Where-Object { $_.PNPDeviceID -like 'USB\*' } | ForEach-Object {
            @{ Port = [string]$_.DeviceID; Instance = [string]$_.PNPDeviceID }
        })
        ConvertTo-Json -InputObject $Ports -Compress
    } else {
        if ([string]::IsNullOrEmpty($Volume)) { throw 'A drive root is required.' }
        $Letter = $Volume.Substring(0,1)
        $Volumes = @(Get-Volume -DriveLetter $Letter)
        $Partitions = @(Get-Partition -DriveLetter $Letter)
        if ($Volumes.Count -ne 1 -or $Partitions.Count -ne 1) { throw 'Volume mapping is ambiguous.' }
        $Disks = @($Partitions[0] | Get-Disk)
        if ($Disks.Count -ne 1) { throw 'Physical disk mapping is ambiguous.' }
        $Disk = $Disks[0]
        foreach ($Property in @('IsBoot','IsSystem','IsReadOnly','IsOffline')) {
            if ($Disk.$Property -isnot [bool]) { throw 'Disk flags are unavailable.' }
        }
        @{ Root = ($Letter.ToUpperInvariant() + ':\'); Filesystem = [string]$Volumes[0].FileSystem;
           BusType = [string]$Disk.BusType; IsBoot = [bool]$Disk.IsBoot; IsSystem = [bool]$Disk.IsSystem;
           IsReadOnly = [bool]$Disk.IsReadOnly; IsOffline = [bool]$Disk.IsOffline;
           Health = [string]$Disk.HealthStatus; VolumeHealth = [string]$Volumes[0].HealthStatus } | ConvertTo-Json -Compress
    }
    exit 0
} catch {
    [Console]::Error.WriteLine('Storage/USB metadata query failed. Check administrator access, drive and USB driver.')
    exit 1
}
