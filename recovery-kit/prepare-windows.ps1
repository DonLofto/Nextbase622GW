#requires -Version 5.1
<#
Prepare, inspect, or remove the temporary 622GW R13.3 Bluetooth recovery kit.
Uses only PowerShell/.NET built-ins; never formats or ejects a card.
#>
[CmdletBinding()]
param(
    [ValidateSet('Prepare', 'Status', 'Remove')]
    [string]$Action = 'Prepare',
    [string]$Volume
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$OwnerText = "Nextbase622GW Bluetooth Recovery Kit 0.2.0`n"
$PayloadNames = @('autoexec.ash', 'nb-bt-recover.sh', 'usb.console')
$MarkerName = 'nb-bt-recovery-kit.txt'
$GuardName = 'nb-bt-recovery.claimed'
$Hashes = @{}

function Get-ExistingItem([string]$Path) {
    $Items = @(Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue)
    if ($Items.Count -gt 0) { return $Items[0] }
    return $null
}

function Assert-PlainItem($Item, [bool]$Directory, [string]$Description) {
    if ($null -eq $Item) { throw "Missing $Description." }
    if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing a symlink or reparse point at $Description."
    }
    if ([bool]$Item.PSIsContainer -ne $Directory) { throw "Unexpected file type at $Description." }
}

function Test-ExactOwner([string]$Path) {
    $Item = Get-ExistingItem $Path
    Assert-PlainItem $Item $false 'ownership file'
    $Expected = [Text.Encoding]::ASCII.GetBytes($OwnerText)
    $Actual = [IO.File]::ReadAllBytes($Item.FullName)
    if ($Actual.Length -ne $Expected.Length) { throw 'Ownership file does not match this kit.' }
    for ($Index = 0; $Index -lt $Expected.Length; $Index++) {
        if ($Actual[$Index] -ne $Expected[$Index]) { throw 'Ownership file does not match this kit.' }
    }
}

function Assert-CompatibleCard([string]$Root) {
    Assert-PlainItem (Get-ExistingItem $Root) $true 'card root'
    $Info = Get-ExistingItem (Join-Path $Root 'Nextbase.info')
    Assert-PlainItem $Info $false 'Nextbase.info'
    if ($Info.Length -gt 1MB) { throw 'Nextbase.info is unexpectedly large.' }
    $Text = [IO.File]::ReadAllText($Info.FullName)
    if ($Text.IndexOf([char]0) -ge 0) { throw 'Nextbase.info contains malformed data.' }
    $Models = [regex]::Matches($Text, '(?im)^[ \t]*Model[ \t]*:([^\r\n]*)\r?$')
    $Firmware = [regex]::Matches($Text, '(?im)^[ \t]*Firmware[ \t]*:([^\r\n]*)\r?$')
    if ($Models.Count -ne 1 -or $Firmware.Count -ne 1) {
        throw 'Nextbase.info must contain exactly one Model and one Firmware record.'
    }
    if ($Models[0].Groups[1].Value.Trim() -cne '622GW' -or $Firmware[0].Groups[1].Value.Trim() -cne 'R13.3') {
        throw 'Only model 622GW with firmware R13.3 is supported.'
    }
}

function Find-CardRoot {
    if (-not [string]::IsNullOrWhiteSpace($Volume)) {
        $Root = [IO.Path]::GetFullPath($Volume)
        Assert-CompatibleCard $Root
        return (Get-Item -LiteralPath $Root -Force).FullName
    }
    $Candidates = @()
    $Roots = @(Get-PSDrive -PSProvider FileSystem | ForEach-Object { $_.Root } | Sort-Object -Unique)
    foreach ($Root in $Roots) {
        try {
            Assert-CompatibleCard $Root
            $Candidates += (Get-Item -LiteralPath $Root -Force).FullName
        } catch {
            # Unrelated, unavailable, malformed and incompatible drives are not candidates.
        }
    }
    if ($Candidates.Count -ne 1) {
        throw 'Auto-detection requires exactly one compatible mounted card. Specify -Volume E:\ explicitly.'
    }
    return $Candidates[0]
}

function Read-PayloadHashes {
    Assert-PlainItem (Get-ExistingItem $PSScriptRoot) $true 'kit directory'
    $PayloadRoot = Join-Path $PSScriptRoot 'payload'
    Assert-PlainItem (Get-ExistingItem $PayloadRoot) $true 'payload directory'
    $Manifest = Get-ExistingItem (Join-Path $PSScriptRoot 'SHA256SUMS')
    Assert-PlainItem $Manifest $false 'SHA256SUMS'
    if ($Manifest.Length -gt 4096) { throw 'SHA256SUMS is unexpectedly large.' }
    $Entries = @([IO.File]::ReadAllLines($Manifest.FullName))
    if ($Entries.Count -ne 3) { throw 'SHA256SUMS must contain exactly the three payload entries.' }
    foreach ($Line in $Entries) {
        $Match = [regex]::Match($Line, '^([0-9a-fA-F]{64})  (autoexec\.ash|nb-bt-recover\.sh|usb\.console)$')
        if (-not $Match.Success) { throw 'Malformed or unknown entry in SHA256SUMS.' }
        $Name = $Match.Groups[2].Value
        if ($Hashes.ContainsKey($Name)) { throw 'Duplicate entry in SHA256SUMS.' }
        $Hashes[$Name] = $Match.Groups[1].Value.ToUpperInvariant()
    }
    foreach ($Name in $PayloadNames) {
        if (-not $Hashes.ContainsKey($Name)) { throw 'A payload hash is missing.' }
        Assert-PayloadFile (Join-Path $PayloadRoot $Name) $Name
    }
}

function Assert-PayloadFile([string]$Path, [string]$Name) {
    Assert-PlainItem (Get-ExistingItem $Path) $false $Name
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -cne $Hashes[$Name]) {
        throw "SHA256 verification failed for $Name. No unknown or modified file will be overwritten or removed."
    }
}

function Assert-NoConflictingHooks([string]$Root) {
    $LegacyNames = @('bt-diagnostics.sh', 'bt-late-diagnostics.sh', 'bt-storage-diagnostics.sh', 'bt-start-test.sh')
    foreach ($Item in @(Get-ChildItem -LiteralPath $Root -Force)) {
        $Name = $Item.Name
        if ($Name -ilike 'FW*.bin' -or $Name -ilike 'LD*.bin') { throw 'Remove firmware update binaries from the card before using this kit.' }
        if ($Name -ilike 'usb*.console' -and $Name -ine 'usb.console') { throw 'An unknown USB console hook exists. Preserve it and resolve it manually.' }
        if (($Name -ilike 'autoexec*.ash' -and $Name -ine 'autoexec.ash') -or $Name -ilike 'bt-*.claimed' -or $LegacyNames -icontains $Name) {
            throw 'A legacy diagnostic/startup hook exists. Preserve it and resolve it manually.'
        }
    }
    foreach ($Name in ($PayloadNames + @($MarkerName, $GuardName))) {
        $Item = Get-ExistingItem (Join-Path $Root $Name)
        if ($null -ne $Item) { Assert-PlainItem $Item ($Name -ceq $GuardName) $Name }
    }
}

function Assert-OwnedInstallation([string]$Root) {
    Test-ExactOwner (Join-Path $Root $MarkerName)
    Assert-PayloadFile (Join-Path $Root 'autoexec.ash') 'autoexec.ash'
    Assert-PayloadFile (Join-Path $Root 'nb-bt-recover.sh') 'nb-bt-recover.sh'
    $Token = Get-ExistingItem (Join-Path $Root 'usb.console')
    if ($null -ne $Token) { Assert-PayloadFile $Token.FullName 'usb.console' }
    $Guard = Get-ExistingItem (Join-Path $Root $GuardName)
    if ($null -ne $Guard) {
        Assert-PlainItem $Guard $true $GuardName
        Test-ExactOwner (Join-Path $Guard.FullName 'owner.txt')
        $Entries = @(Get-ChildItem -LiteralPath $Guard.FullName -Force)
        if ($Entries.Count -ne 1 -or $Entries[0].Name -cne 'owner.txt') { throw 'Runtime guard contains unknown files; refusing cleanup.' }
    }
}

function Prepare-Card([string]$Root) {
    foreach ($Name in ($PayloadNames + @($MarkerName, $GuardName))) {
        if ($null -ne (Get-ExistingItem (Join-Path $Root $Name))) {
            throw 'A recovery file or runtime guard already exists. Use Status, then Remove before rearming; unknown files must be resolved manually.'
        }
    }
    # All kit and card checks have completed before the first write.
    $Stage = Join-Path $Root ('.nb-bt-recovery-stage-' + [Guid]::NewGuid().ToString('N'))
    $Created = @()
    $PendingMove = $null
    $StageCreated = $false
    try {
        # A random exclusive name avoids reuse or deletion of an existing directory.
        if ($null -ne (Get-ExistingItem $Stage)) { throw 'Staging name already exists.' }
        [void](New-Item -ItemType Directory -Path $Stage -ErrorAction Stop)
        $StageCreated = $true
        foreach ($Name in $PayloadNames) {
            $Destination = Join-Path $Stage $Name
            Copy-Item -LiteralPath (Join-Path (Join-Path $PSScriptRoot 'payload') $Name) -Destination $Destination -ErrorAction Stop
            Assert-PayloadFile $Destination $Name
        }
        [IO.File]::WriteAllText((Join-Path $Stage $MarkerName), $OwnerText, [Text.Encoding]::ASCII)
        Test-ExactOwner (Join-Path $Stage $MarkerName)
        # Install the boot hook last: interrupted copies cannot arm a partial payload.
        foreach ($Name in @('nb-bt-recover.sh', 'usb.console', $MarkerName, 'autoexec.ash')) {
            $Destination = Join-Path $Root $Name
            if ($null -ne (Get-ExistingItem $Destination)) { throw "A file appeared during preparation: $Name. Refusing overwrite." }
            $PendingMove = $Name
            Move-Item -LiteralPath (Join-Path $Stage $Name) -Destination $Destination -ErrorAction Stop
            $Created += $Name
            $PendingMove = $null
            if ($Name -ceq $MarkerName) { Test-ExactOwner $Destination }
            else { Assert-PayloadFile $Destination $Name }
        }
    } catch {
        $OriginalFailure = $_
        # A provider can report an error after a rename completed. A consumed
        # stage source plus exact destination bytes still belongs to this move.
        if ($null -ne $PendingMove -and $null -eq (Get-ExistingItem (Join-Path $Stage $PendingMove)) -and $null -ne (Get-ExistingItem (Join-Path $Root $PendingMove))) {
            $Created += $PendingMove
        }
        # Only exact bytes created by this attempt qualify for rollback; hook first.
        $RollbackNames = @($Created | Sort-Object { if ($_ -ceq 'autoexec.ash') { 0 } else { 1 } })
        foreach ($Name in $RollbackNames) {
            try {
                $Path = Join-Path $Root $Name
                if ($Name -ceq $MarkerName) { Test-ExactOwner $Path } else { Assert-PayloadFile $Path $Name }
                Remove-Item -LiteralPath $Path -ErrorAction Stop
            } catch { Write-Warning "Rollback preserved $Name because it could not verify or remove it. Inspect the card before rebooting." }
        }
        throw $OriginalFailure
    } finally {
        $StageItem = Get-ExistingItem $Stage
        if ($StageCreated -and $null -ne $StageItem -and $StageItem.PSIsContainer -and ($StageItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
            # Never recursively delete: only these files and an empty owned stage.
            foreach ($Name in ($PayloadNames + @($MarkerName))) {
                $Path = Join-Path $Stage $Name
                $Item = Get-ExistingItem $Path
                if ($null -ne $Item -and -not $Item.PSIsContainer -and ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
                    Remove-Item -LiteralPath $Path -ErrorAction SilentlyContinue
                }
            }
            if (@(Get-ChildItem -LiteralPath $Stage -Force).Count -eq 0) {
                # Directory.Delete is empty-only and also works for dot directories
                # on Unix test hosts without a forced or recursive deletion.
                [IO.Directory]::Delete($Stage)
            }
        }
    }
    Write-Host 'Prepared temporary Bluetooth recovery for 622GW R13.3.'
    Write-Host 'Safely eject the card in Windows before disconnecting. The tool does not eject it.'
    Write-Host 'With the camera off, insert the card. Reconnect the camera to the computer with a USB data cable at the camera body, then power on; wait at least one minute.'
    Write-Host 'Stop recording; open Connect App > Setup Phone and pair using the Nextbase app.'
    Write-Host 'This is one recovery attempt, not a persistent repair or confirmation of phone pairing.'
    Write-Host 'After a later reboot the temporary RAM recovery is lost. Remove then Prepare to rearm.'
}

function Remove-CardKit([string]$Root) {
    Assert-OwnedInstallation $Root
    # Disable startup first, then remove only unchanged files we own.
    foreach ($Name in @('autoexec.ash', 'usb.console', 'nb-bt-recover.sh')) {
        $Path = Join-Path $Root $Name
        if ($null -ne (Get-ExistingItem $Path)) {
            Assert-PayloadFile $Path $Name
            Remove-Item -LiteralPath $Path -ErrorAction Stop
        }
    }
    $GuardPath = Join-Path $Root $GuardName
    if ($null -ne (Get-ExistingItem $GuardPath)) {
        Assert-PlainItem (Get-ExistingItem $GuardPath) $true $GuardName
        Test-ExactOwner (Join-Path $GuardPath 'owner.txt')
        if (@(Get-ChildItem -LiteralPath $GuardPath -Force).Count -ne 1) { throw 'Runtime guard changed during removal; preserving it.' }
        Remove-Item -LiteralPath (Join-Path $GuardPath 'owner.txt') -ErrorAction Stop
        Remove-Item -LiteralPath $GuardPath -ErrorAction Stop
    }
    Test-ExactOwner (Join-Path $Root $MarkerName)
    Remove-Item -LiteralPath (Join-Path $Root $MarkerName) -ErrorAction Stop
    Write-Host 'Removed this kit and its runtime guard. Videos, user files and all result directories were preserved.'
    Write-Host 'Safely eject the card in Windows before disconnecting. Prepare again to rearm.'
}

try {
    Read-PayloadHashes
    $CardRoot = Find-CardRoot
    Assert-NoConflictingHooks $CardRoot
    switch ($Action) {
        'Prepare' { Prepare-Card $CardRoot }
        'Remove' { Remove-CardKit $CardRoot }
        'Status' {
            $ManagedPresent = @($PayloadNames + @($MarkerName, $GuardName) | Where-Object { $null -ne (Get-ExistingItem (Join-Path $CardRoot $_)) })
            if ($ManagedPresent.Count -eq 0) { Write-Host 'Compatible 622GW R13.3 card. Recovery kit is not prepared.' }
            else {
                Assert-OwnedInstallation $CardRoot
                if ($null -ne (Get-ExistingItem (Join-Path $CardRoot $GuardName))) {
                    Write-Host 'Recovery kit is claimed. An attempt was started; this does not establish phone pairing success.'
                } else { Write-Host 'Recovery kit is prepared and has not been claimed.' }
                Write-Host 'Use Remove followed by Prepare to rearm. Result directories and videos are preserved.'
            }
        }
    }
    exit 0
} catch {
    Write-Host ('Recovery kit stopped: ' + $_.Exception.Message)
    exit 1
}
