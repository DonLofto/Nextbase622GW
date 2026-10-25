# Dependency-free integration tests. Run with Windows PowerShell 5.1 or pwsh.
# Fixtures contain no device identifiers and never touch a mounted camera.
param([string]$Filter = '*')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Installer = Join-Path $RepoRoot 'recovery-kit/prepare-windows.ps1'
$PowerShellExe = Join-Path $PSHOME 'powershell.exe'
if (-not (Test-Path -LiteralPath $PowerShellExe)) { $PowerShellExe = Join-Path $PSHOME 'pwsh' }
$SuiteRoot = Join-Path ([IO.Path]::GetTempPath()) ('nextbase-windows-tests-' + [Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($SuiteRoot)
$SuiteRoot = (Get-Item -LiteralPath $SuiteRoot).FullName
$OwnerText = "Nextbase622GW Bluetooth Recovery Kit 0.2.0`n"
$Names = @('autoexec.ash', 'nb-bt-recover.sh', 'usb.console')
$script:Passed = 0
$script:Failed = 0
$script:Skipped = 0

function Write-Ascii([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, [Text.Encoding]::ASCII)
}
function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function New-Fixture {
    $Base = Join-Path $SuiteRoot ([Guid]::NewGuid().ToString('N'))
    $Kit = Join-Path $Base 'kit'
    $Payload = Join-Path $Kit 'payload'
    $Card = Join-Path $Base 'card'
    [void][IO.Directory]::CreateDirectory($Payload)
    [void][IO.Directory]::CreateDirectory((Join-Path $Card 'DCIM'))
    if (Test-Path -LiteralPath $Installer) { Copy-Item -LiteralPath $Installer -Destination (Join-Path $Kit 'prepare-windows.ps1') }
    Write-Ascii (Join-Path $Card 'Nextbase.info') "NBDVR622GWA-R13.3`r`nModel:          622GW`r`nFirmware:       R13.3`r`nSerial No:      FIXTURE`r`n"
    Write-Ascii (Join-Path $Card 'DCIM/video.mp4') 'preserved video fixture'
    Write-Ascii (Join-Path $Payload 'autoexec.ash') "sleep 20000`nfixture boot hook`n"
    Write-Ascii (Join-Path $Payload 'nb-bt-recover.sh') "#!/bin/sh`nfixture payload`n"
    Write-Ascii (Join-Path $Payload 'usb.console') '0123456789abcdef0123456789abcdef'
    $Manifest = ''
    foreach ($Name in $Names) { $Manifest += (Get-FileHash -LiteralPath (Join-Path $Payload $Name) -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $Name + "`n" }
    Write-Ascii (Join-Path $Kit 'SHA256SUMS') $Manifest
    return @{ Base = $Base; Kit = $Kit; Card = $Card; Payload = $Payload }
}
function Invoke-Installer($Fixture, [string]$Action = 'Prepare', [string]$Before = '', [switch]$Auto) {
    $Runner = Join-Path $Fixture.Base ('runner-' + [Guid]::NewGuid().ToString('N') + '.ps1')
    $ScriptPath = (Join-Path $Fixture.Kit 'prepare-windows.ps1').Replace("'", "''")
    $CardPath = $Fixture.Card.Replace("'", "''")
    $Arguments = "-Action '$Action'"
    if (-not $Auto) { $Arguments += " -Volume '$CardPath'" }
    Write-Ascii $Runner ($Before + "`n& '$ScriptPath' $Arguments`nexit `$LASTEXITCODE`n")
    $Output = & $PowerShellExe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Runner 2>&1
    return @{ Code = $LASTEXITCODE; Output = ($Output | Out-String) }
}
function Assert-Success($Result) { Assert-True ($Result.Code -eq 0) ("Expected success, got " + $Result.Code + ': ' + $Result.Output) }
function Assert-Refusal($Result) { Assert-True ($Result.Code -ne 0) ("Expected refusal, got success: " + $Result.Output) }
function Get-CardSnapshot([string]$Card) {
    $Rows = @(Get-ChildItem -LiteralPath $Card -Force -Recurse | ForEach-Object {
        $Relative = $_.FullName.Substring($Card.Length)
        if ($_.PSIsContainer) { 'D ' + $Relative }
        elseif (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { 'L ' + $Relative }
        else { 'F ' + $Relative + ' ' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    } | Sort-Object)
    return ($Rows -join "`n")
}
function Assert-UnchangedRefusal($Fixture, [string]$Action = 'Prepare', [string]$Before = '', [switch]$Auto) {
    $Snapshot = Get-CardSnapshot $Fixture.Card
    $Result = Invoke-Installer $Fixture $Action $Before -Auto:$Auto
    Assert-Refusal $Result
    $After = Get-CardSnapshot $Fixture.Card
    Assert-True ($After -ceq $Snapshot) ("Refusal mutated the card.`nBefore: $Snapshot`nAfter: $After`nOutput: " + $Result.Output)
}
function Test-Case([string]$Name, [scriptblock]$Body) {
    if ($Name -notlike $Filter) { return }
    try { & $Body; $script:Passed++; Write-Host ('PASS ' + $Name) }
    catch { $script:Failed++; Write-Host ('FAIL ' + $Name + ': ' + $_.Exception.Message) }
}

try {
    # Catches missing installation, incorrect payload copies, CRLF/BOM markers, and video deletion.
    Test-Case 'prepare writes verified files and exact ASCII LF marker, preserving videos' {
        $f = New-Fixture
        Assert-Success (Invoke-Installer $f)
        foreach ($Name in $Names) {
            Assert-True ((Get-FileHash -LiteralPath (Join-Path $f.Card $Name)).Hash -ceq (Get-FileHash -LiteralPath (Join-Path $f.Payload $Name)).Hash) ('Payload differs: ' + $Name)
        }
        $MarkerBytes = [IO.File]::ReadAllBytes((Join-Path $f.Card 'nb-bt-recovery-kit.txt'))
        Assert-True ([BitConverter]::ToString($MarkerBytes) -ceq [BitConverter]::ToString([Text.Encoding]::ASCII.GetBytes($OwnerText))) 'Ownership marker bytes differ'
        Assert-True (([IO.File]::ReadAllText((Join-Path $f.Card 'DCIM/video.mp4'))) -ceq 'preserved video fixture') 'Video changed'
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $f.Card 'nb-bt-recovery.claimed'))) 'Host prematurely claimed the one-shot run'
        Assert-True (@(Get-ChildItem -LiteralPath $f.Card -Force | Where-Object { $_.Name -like '.nb-bt-recovery-stage-*' }).Count -eq 0) 'Successful prepare left staging files'
    }
    foreach ($Identity in @('', "Model: 522GW`nFirmware: R13.3`n", "Model: 622GW`nFirmware: R12.4`n", "Model: 622GW`nModel: 622GW`nFirmware: R13.3`n", "Model: 622GW`nFirmware: R13.3`nFirmware: R13.3`n", "Model: 622GW-extra`nFirmware: R13.3`n")) {
        Test-Case ('refuse missing/wrong/duplicate/malformed identity: ' + $Identity.Replace("`n", '|')) {
            $f = New-Fixture; Write-Ascii (Join-Path $f.Card 'Nextbase.info') $Identity; Assert-UnchangedRefusal $f
        }
    }
    Test-Case 'refuse missing Nextbase.info' {
        $f = New-Fixture; Remove-Item -LiteralPath (Join-Path $f.Card 'Nextbase.info'); Assert-UnchangedRefusal $f
    }
    foreach ($Collision in @('autoexec.ash', 'usb.console', 'usb.multi.console', 'nb-bt-recover.sh', 'nb-bt-recovery-kit.txt', 'bt-start-test.sh', 'bt-diagnostics.sh', 'bt-late-diagnostics.sh', 'bt-storage-diagnostics.sh', 'autoexec-storage.ash', 'FW622GWA.bin', 'ld622gwa.BIN')) {
        Test-Case ('refuse existing hook/update: ' + $Collision) {
            $f = New-Fixture; Write-Ascii (Join-Path $f.Card $Collision) 'unknown user file'; Assert-UnchangedRefusal $f
        }
    }
    Test-Case 'refuse runtime guard before prepare' {
        $f = New-Fixture; [void][IO.Directory]::CreateDirectory((Join-Path $f.Card 'nb-bt-recovery.claimed')); Assert-UnchangedRefusal $f
    }
    Test-Case 'refuse legacy diagnostic claim directories without deleting their contents' {
        $f = New-Fixture
        [void][IO.Directory]::CreateDirectory((Join-Path $f.Card 'BT-start-test.CLAIMED'))
        Write-Ascii (Join-Path $f.Card 'BT-start-test.CLAIMED/user.txt') 'preserve prior diagnostic claim'
        Assert-UnchangedRefusal $f
    }
    Test-Case 'refuse corrupt bundled payload before mutation' {
        $f = New-Fixture; Write-Ascii (Join-Path $f.Payload 'nb-bt-recover.sh') 'corrupt'; Assert-UnchangedRefusal $f
    }
    Test-Case 'refuse manifest with additional or duplicate entries' {
        foreach ($Extra in @('unrelated.txt', 'usb.console')) {
            $f = New-Fixture; [IO.File]::AppendAllText((Join-Path $f.Kit 'SHA256SUMS'), ('a' * 64) + '  ' + $Extra + "`n"); Assert-UnchangedRefusal $f
        }
    }
    Test-Case 'status is read-only and identifies unprepared and claimed cards' {
        $f = New-Fixture; $Snapshot = Get-CardSnapshot $f.Card
        Assert-Success (Invoke-Installer $f 'Status')
        Assert-True ((Get-CardSnapshot $f.Card) -ceq $Snapshot) 'Status mutated unprepared card'
        Assert-Success (Invoke-Installer $f)
        [void][IO.Directory]::CreateDirectory((Join-Path $f.Card 'nb-bt-recovery.claimed'))
        Write-Ascii (Join-Path $f.Card 'nb-bt-recovery.claimed/owner.txt') $OwnerText
        $Snapshot = Get-CardSnapshot $f.Card; $Result = Invoke-Installer $f 'Status'; Assert-Success $Result
        Assert-True ($Result.Output -match '(?i)claimed') 'Status omitted claim state'
        Assert-True ((Get-CardSnapshot $f.Card) -ceq $Snapshot) 'Status mutated prepared card'
    }
    Test-Case 'remove preserves result directories and videos after consumed trigger' {
        $f = New-Fixture; Assert-Success (Invoke-Installer $f)
        [void][IO.Directory]::CreateDirectory((Join-Path $f.Card 'nb-bt-recovery-1'))
        Write-Ascii (Join-Path $f.Card 'nb-bt-recovery-1/result.txt') 'preserved results'
        Move-Item -LiteralPath (Join-Path $f.Card 'usb.console') -Destination (Join-Path $f.Card 'nb-bt-recovery-1/usb.console')
        [void][IO.Directory]::CreateDirectory((Join-Path $f.Card 'nb-bt-recovery.claimed'))
        Write-Ascii (Join-Path $f.Card 'nb-bt-recovery.claimed/owner.txt') $OwnerText
        Assert-Success (Invoke-Installer $f 'Remove')
        foreach ($Name in ($Names + @('nb-bt-recovery-kit.txt', 'nb-bt-recovery.claimed'))) { Assert-True (-not (Test-Path -LiteralPath (Join-Path $f.Card $Name))) ('Managed path remains: ' + $Name) }
        Assert-True (([IO.File]::ReadAllText((Join-Path $f.Card 'nb-bt-recovery-1/result.txt'))) -ceq 'preserved results') 'Result changed'
        Assert-True (Test-Path -LiteralPath (Join-Path $f.Card 'nb-bt-recovery-1/usb.console')) 'Consumed trigger removed from results'
        Assert-True (Test-Path -LiteralPath (Join-Path $f.Card 'DCIM/video.mp4')) 'Video removed'
    }
    Test-Case 'remove refuses all unknown or changed ownership and payload states without mutation' {
        foreach ($Changed in @('autoexec.ash', 'nb-bt-recover.sh', 'usb.console', 'nb-bt-recovery-kit.txt', 'guard-owner', 'guard-extra', 'guard-missing-owner')) {
            $f = New-Fixture; Assert-Success (Invoke-Installer $f)
            if ($Changed.StartsWith('guard-')) {
                [void][IO.Directory]::CreateDirectory((Join-Path $f.Card 'nb-bt-recovery.claimed'))
                if ($Changed -ne 'guard-missing-owner') { Write-Ascii (Join-Path $f.Card 'nb-bt-recovery.claimed/owner.txt') $OwnerText }
                if ($Changed -eq 'guard-owner') { Write-Ascii (Join-Path $f.Card 'nb-bt-recovery.claimed/owner.txt') 'unknown owner' }
                if ($Changed -eq 'guard-extra') { Write-Ascii (Join-Path $f.Card 'nb-bt-recovery.claimed/user.txt') 'preserve me' }
            } else { Write-Ascii (Join-Path $f.Card $Changed) 'changed by user' }
            Assert-UnchangedRefusal $f 'Remove'
        }
    }
    Test-Case 'remove refuses absent ownership even if payload names match' {
        $f = New-Fixture; foreach ($Name in $Names) { Copy-Item -LiteralPath (Join-Path $f.Payload $Name) -Destination (Join-Path $f.Card $Name) }; Assert-UnchangedRefusal $f 'Remove'
    }
    Test-Case 'prepare refuses already-owned card until explicitly removed' {
        $f = New-Fixture; Assert-Success (Invoke-Installer $f); Assert-UnchangedRefusal $f
    }
    Test-Case 'staging copy failure rolls back without leaving boot hook or staging files' {
        $f = New-Fixture
        $Before = @'
function global:Copy-Item {
    param([string]$LiteralPath, [string]$Destination, [string]$ErrorAction)
    if ([IO.Path]::GetFileName($LiteralPath) -eq 'usb.console') { throw 'injected copy failure' }
    Microsoft.PowerShell.Management\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -ErrorAction Stop
}
'@
        Assert-UnchangedRefusal $f 'Prepare' $Before
    }
    Test-Case 'staging verification catches silent copy corruption' {
        $f = New-Fixture
        $Before = @'
function global:Copy-Item {
    param([string]$LiteralPath, [string]$Destination, [string]$ErrorAction)
    Microsoft.PowerShell.Management\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -ErrorAction Stop
    if ([IO.Path]::GetFileName($LiteralPath) -eq 'usb.console') { [IO.File]::WriteAllText($Destination, 'corrupt') }
}
'@
        Assert-UnchangedRefusal $f 'Prepare' $Before
    }
    Test-Case 'promotion failure removes only files this attempt created' {
        $f = New-Fixture
        $Before = @'
function global:Move-Item {
    param([string]$LiteralPath, [string]$Destination, [string]$ErrorAction)
    if ([IO.Path]::GetFileName($Destination) -eq 'autoexec.ash') { throw 'injected promotion failure' }
    Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination -ErrorAction Stop
}
'@
        Assert-UnchangedRefusal $f 'Prepare' $Before
    }
    Test-Case 'promotion reporting failure after moving the boot hook still rolls back' {
        $f = New-Fixture
        $Before = @'
function global:Move-Item {
    param([string]$LiteralPath, [string]$Destination, [string]$ErrorAction)
    Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination -ErrorAction Stop
    if ([IO.Path]::GetFileName($Destination) -eq 'autoexec.ash') { throw 'injected post-move failure' }
}
'@
        Assert-UnchangedRefusal $f 'Prepare' $Before
    }
    Test-Case 'a user hook appearing during staging is preserved and prevents arming' {
        $f = New-Fixture
        $Before = @'
function global:Copy-Item {
    param([string]$LiteralPath, [string]$Destination, [string]$ErrorAction)
    Microsoft.PowerShell.Management\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -ErrorAction Stop
    if ([IO.Path]::GetFileName($LiteralPath) -eq 'usb.console') {
        $Card = Split-Path -Parent (Split-Path -Parent $Destination)
        [IO.File]::WriteAllText((Join-Path $Card 'autoexec.ash'), 'unknown concurrent user hook')
    }
}
'@
        Assert-Refusal (Invoke-Installer $f 'Prepare' $Before)
        Assert-True (([IO.File]::ReadAllText((Join-Path $f.Card 'autoexec.ash'))) -ceq 'unknown concurrent user hook') 'Concurrent user hook was changed or removed'
        foreach ($Name in @('nb-bt-recover.sh', 'usb.console', 'nb-bt-recovery-kit.txt')) { Assert-True (-not (Test-Path -LiteralPath (Join-Path $f.Card $Name))) ('Partial installation remains: ' + $Name) }
    }
    Test-Case 'auto-detect selects one compatible card and refuses ambiguity' {
        $f = New-Fixture; $g = New-Fixture
        $Root = $f.Card.Replace("'", "''")
        $One = "function global:Get-PSDrive { param(`$PSProvider) [pscustomobject]@{ Root = '$Root' } }"
        Assert-Success (Invoke-Installer $f 'Prepare' $One -Auto)
        Assert-Success (Invoke-Installer $f 'Remove')
        $Other = $g.Card.Replace("'", "''")
        $Two = "function global:Get-PSDrive { param(`$PSProvider) [pscustomobject]@{ Root = '$Root' }; [pscustomobject]@{ Root = '$Other' } }"
        Assert-UnchangedRefusal $f 'Prepare' $Two -Auto
        $None = "function global:Get-PSDrive { param(`$PSProvider) }"
        Assert-UnchangedRefusal $f 'Prepare' $None -Auto
    }
    Test-Case 'reparse point on a managed path is refused' {
        $f = New-Fixture; $Target = Join-Path $f.Base 'outside.sh'; Write-Ascii $Target 'outside user file'
        try { [void](New-Item -ItemType SymbolicLink -Path (Join-Path $f.Card 'autoexec.ash') -Target $Target -ErrorAction Stop) }
        catch { $script:Skipped++; Write-Host 'SKIP symbolic-link creation unavailable on this host'; return }
        Assert-UnchangedRefusal $f
        Assert-True (([IO.File]::ReadAllText($Target)) -ceq 'outside user file') 'Symlink target changed'
    }
    Test-Case 'remove refuses symlinks even when their targets have exact owned bytes' {
        foreach ($Name in @('autoexec.ash', 'nb-bt-recover.sh', 'usb.console', 'nb-bt-recovery-kit.txt')) {
            $f = New-Fixture; Assert-Success (Invoke-Installer $f)
            $Path = Join-Path $f.Card $Name
            $Target = Join-Path $f.Base ('outside-' + $Name)
            Copy-Item -LiteralPath $Path -Destination $Target
            Remove-Item -LiteralPath $Path
            try { [void](New-Item -ItemType SymbolicLink -Path $Path -Target $Target -ErrorAction Stop) }
            catch { $script:Skipped++; Write-Host 'SKIP symbolic-link creation unavailable on this host'; return }
            $Hash = (Get-FileHash -LiteralPath $Target).Hash
            Assert-UnchangedRefusal $f 'Remove'
            Assert-True ((Get-FileHash -LiteralPath $Target).Hash -ceq $Hash) 'Symlink target changed during removal'
        }
    }
} finally {
    Remove-Item -LiteralPath $SuiteRoot -Recurse -Force
}
Write-Host ("Windows installer tests: $script:Passed passed, $script:Failed failed, $script:Skipped skipped")
if ($script:Failed -ne 0) { exit 1 }
exit 0
