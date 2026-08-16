<#
.SYNOPSIS
    Toggle SteamVR's null (headless) HMD driver.

.DESCRIPTION
    Lets a VR game launch far enough to load its script extender and plugins with no
    headset connected. The game is NOT playable this way — it renders to nowhere — but it
    initialises, which is all an automated verification pass needs.

    That distinction is the whole point for this project: the acceptance signal is a
    plugin answering over HTTP, not pixels. So verification does not need a human wearing
    a headset, which means it can run unattended and in CI.

    Writes to the USER config (Steam\config\steamvr.vrsettings), not the SteamVR install's
    default.vrsettings. The install's defaults are overwritten on every SteamVR update;
    the user config is not.

.NOTES
    THIS IS GLOBAL AND IT AFFECTS NORMAL VR USE. `forcedDriver=null` forces the null HMD
    even when a real headset IS connected. Always -Disable before using VR for real.
    -Enable backs up the original config once, next to the file.

.EXAMPLE
    .\steamvr-null.ps1 -Status
    .\steamvr-null.ps1 -Enable
    .\steamvr-null.ps1 -Disable
#>
[CmdletBinding(DefaultParameterSetName = 'Status')]
param(
    [Parameter(ParameterSetName = 'Enable')][switch]$Enable,
    [Parameter(ParameterSetName = 'Disable')][switch]$Disable,
    [Parameter(ParameterSetName = 'Status')][switch]$Status,
    [string]$SteamPath = 'C:\Program Files (x86)\Steam'
)

$ErrorActionPreference = 'Stop'
$cfg    = Join-Path $SteamPath 'config\steamvr.vrsettings'
$backup = Join-Path $SteamPath 'config\steamvr.vrsettings.pre-modlist-agent.bak'

if (-not (Test-Path $cfg)) { throw "SteamVR user config not found at $cfg" }

# Refuse to reconfigure drivers underneath a running SteamVR — it will not pick the
# change up, and it will write the old values back over ours on exit.
$running = Get-Process vrserver, vrmonitor -ErrorAction SilentlyContinue
if ($running -and -not $Status) {
    throw "SteamVR is running (vrserver/vrmonitor). Close it first, or the change is both ignored and overwritten on exit."
}

function Read-Cfg { Get-Content $cfg -Raw | ConvertFrom-Json }

function Write-Cfg($obj) {
    # Depth matters: the config nests several levels and the default (2) silently
    # stringifies anything deeper.
    $obj | ConvertTo-Json -Depth 12 | Set-Content $cfg -Encoding utf8
}

function Set-Prop($obj, [string]$name, $value) {
    if ($obj.PSObject.Properties.Name -contains $name) { $obj.$name = $value }
    else { $obj | Add-Member -NotePropertyName $name -NotePropertyValue $value }
}

function Get-State {
    $d = Read-Cfg
    $sv = $d.steamvr
    $nul = $d.driver_null
    [pscustomobject]@{
        requireHmd             = if ($sv -and $sv.PSObject.Properties.Name -contains 'requireHmd') { $sv.requireHmd } else { $null }
        forcedDriver           = if ($sv -and $sv.PSObject.Properties.Name -contains 'forcedDriver') { $sv.forcedDriver } else { $null }
        activateMultipleDrivers = if ($sv -and $sv.PSObject.Properties.Name -contains 'activateMultipleDrivers') { $sv.activateMultipleDrivers } else { $null }
        driver_null_enable     = if ($nul -and $nul.PSObject.Properties.Name -contains 'enable') { $nul.enable } else { $null }
        NullActive             = ($sv -and $sv.PSObject.Properties.Name -contains 'forcedDriver' -and $sv.forcedDriver -eq 'null')
    }
}

switch ($PSCmdlet.ParameterSetName) {

    'Enable' {
        if (-not (Test-Path $backup)) {
            Copy-Item $cfg $backup
            Write-Output "backed up original -> $backup"
        }
        $d = Read-Cfg
        if (-not $d.steamvr) { $d | Add-Member -NotePropertyName steamvr -NotePropertyValue ([pscustomobject]@{}) }
        Set-Prop $d.steamvr 'requireHmd' $false
        Set-Prop $d.steamvr 'forcedDriver' 'null'
        Set-Prop $d.steamvr 'activateMultipleDrivers' $true

        # driver_null lives in the null driver's own default.vrsettings, but a block here
        # overrides it — so the whole toggle stays in one user-owned file.
        $nullCfg = [pscustomobject]@{
            enable                   = $true
            loadPriority             = -999
            serialNumber             = 'Null Serial Number'
            modelNumber              = 'Null Model Number'
            windowX                  = 0
            windowY                  = 0
            windowWidth              = 2160
            windowHeight             = 1200
            renderWidth              = 1512
            renderHeight             = 1680
            secondsFromVsyncToPhotons = 0.01111111
            displayFrequency         = 90.0
        }
        Set-Prop $d 'driver_null' $nullCfg
        Write-Cfg $d
        Write-Output 'null driver ENABLED. SteamVR will start headless.'
        Write-Output 'REMEMBER: -Disable before using the Quest 3 for real.'
        Get-State | Format-List
    }

    'Disable' {
        $d = Read-Cfg
        if ($d.steamvr) {
            Set-Prop $d.steamvr 'requireHmd' $true
            Set-Prop $d.steamvr 'forcedDriver' ''
            Set-Prop $d.steamvr 'activateMultipleDrivers' $false
        }
        if ($d.driver_null) { Set-Prop $d.driver_null 'enable' $false }
        Write-Cfg $d
        Write-Output 'null driver DISABLED. Real headsets work normally again.'
        Get-State | Format-List
    }

    default {
        $s = Get-State
        Write-Output ("null driver active: {0}" -f $s.NullActive)
        $s | Format-List
        if (Test-Path $backup) { Write-Output "backup exists: $backup" }
    }
}
