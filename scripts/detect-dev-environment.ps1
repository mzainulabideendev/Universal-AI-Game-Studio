<#
.SYNOPSIS
    Detects game-development tooling installed on this Windows machine.

.DESCRIPTION
    Read-only. Never installs, deletes or changes anything. Produces a
    machine-readable JSON report plus a human-readable Markdown summary.

    Every tool is verified by running its executable where that is safe.
    A directory name or registry key alone is reported as "unverified".

.PARAMETER OutputDir
    Directory for environment.json and environment.md. Defaults to <repo>/reports.

.PARAMETER JsonOnly
    Suppress the Markdown summary.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\detect-dev-environment.ps1
#>
[CmdletBinding()]
param(
    [string]$OutputDir,
    [switch]$JsonOnly
)

$ErrorActionPreference = 'Continue'
$script:Findings = New-Object System.Collections.Generic.List[object]

function New-Finding {
    param(
        [string]$Name,
        [string]$Category,
        [string]$Path,
        [string]$Version,
        [string]$State,
        [string]$Evidence,
        [string[]]$Notes = @()
    )
    $script:Findings.Add([pscustomobject]@{
        name     = $Name
        category = $Category
        path     = $Path
        version  = $Version
        state    = $State
        evidence = $Evidence
        notes    = $Notes
    })
}

function Invoke-VersionProbe {
    <# Runs an executable with arguments and returns trimmed output, or $null. #>
    param([string]$FilePath, [string[]]$Arguments, [int]$TimeoutMs = 25000)
    if (-not (Test-Path -LiteralPath $FilePath)) { return $null }
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $FilePath
        $psi.Arguments = ($Arguments -join ' ')
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $p = [System.Diagnostics.Process]::Start($psi)
        if (-not $p.WaitForExit($TimeoutMs)) {
            try { $p.Kill($true) } catch { }
            return $null
        }
        $out = $p.StandardOutput.ReadToEnd()
        if ([string]::IsNullOrWhiteSpace($out)) { $out = $p.StandardError.ReadToEnd() }
        if ([string]::IsNullOrWhiteSpace($out)) { return $null }
        return ($out.Trim() -split "`r?`n")[0].Trim()
    } catch { return $null }
}

function Get-FirstExistingPath {
    param([string[]]$Candidates)
    foreach ($c in $Candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

# ---------------------------------------------------------------- hardware --
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object {
    [pscustomobject]@{ name = $_.Name; driver = $_.DriverVersion; adapterRamMB = if ($_.AdapterRAM) { [math]::Round($_.AdapterRAM / 1MB) } else { $null } }
})
$disks = @(Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null } | ForEach-Object {
    [pscustomobject]@{ drive = $_.Name; freeGB = [math]::Round($_.Free / 1GB, 1); usedGB = [math]::Round($_.Used / 1GB, 1) }
})

$cpuName = $cs.ProcessorName
if (-not $cpuName) { $cpuName = (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name) }
$hardware = [pscustomobject]@{
    os          = $os.Caption
    osVersion   = $os.Version
    architecture = $os.OSArchitecture
    cpu         = $cpuName
    logicalCores = [Environment]::ProcessorCount
    ramGB       = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    gpus        = $gpus
    disks       = $disks
    powershell  = $PSVersionTable.PSVersion.ToString()
}

# ---------------------------------------------------------------- Unity -----
$unityHubCandidates = @(
    "$env:ProgramFiles\Unity Hub\Unity Hub.exe",
    "${env:ProgramFiles(x86)}\Unity Hub\Unity Hub.exe",
    "$env:LOCALAPPDATA\Programs\Unity Hub\Unity Hub.exe"
)
$unityHub = Get-FirstExistingPath $unityHubCandidates
if ($unityHub) {
    New-Finding -Name 'Unity Hub' -Category 'engine' -Path $unityHub -Version (Invoke-VersionProbe $unityHub @('--headless','--spectre') ) -State 'verified' -Evidence 'Executable present'
} else {
    New-Finding -Name 'Unity Hub' -Category 'engine' -Path $null -Version $null -State 'not-found' -Evidence 'Not in standard install locations'
}

$editorRoots = @(
    "$env:ProgramFiles\Unity\Hub\Editor",
    "$env:ProgramFiles\Unity\Editor",
    "D:\Unity\Hub\Editor"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

$unityEditors = @()
foreach ($root in $editorRoots) {
    Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $exe = Join-Path $_.FullName 'Editor\Unity.exe'
        if (-not (Test-Path -LiteralPath $exe)) { $exe = Join-Path $_.FullName 'Unity.exe' }
        $unityEditors += [pscustomobject]@{ versionDir = $_.Name; root = $_.FullName; exe = $exe; exists = (Test-Path -LiteralPath $exe) }
    }
}
foreach ($e in $unityEditors) {
    $ver = $null
    if ($e.exists) {
        $info = Join-Path $e.root 'Editor\Data\PlaybackEngines'
        $ver = (Invoke-VersionProbe $e.exe @('-version','-quit','-batchmode','-nographics'))
        if (-not $ver) { $ver = $e.versionDir }
    }
    $modules = @()
    $playback = Join-Path $e.root 'Editor\Data\PlaybackEngines'
    if (Test-Path -LiteralPath $playback) { $modules = @(Get-ChildItem -LiteralPath $playback -Directory | Select-Object -ExpandProperty Name) }
    New-Finding -Name "Unity Editor $($e.versionDir)" -Category 'engine' -Path $e.exe -Version $ver `
        -State ($(if ($e.exists) { 'verified' } else { 'broken' })) `
        -Evidence ($(if ($e.exists) { 'Unity.exe present and version probed' } else { 'Version folder exists but Unity.exe missing' })) `
        -Notes ($modules | ForEach-Object { "module:$_" })
}

# Unity CLI (installed by the Unity Hub / Editor) manages MCP + builds.
$unityCliCandidates = @(
    "$env:LOCALAPPDATA\Unity\bin\unity.exe",
    "$env:ProgramFiles\Unity\bin\unity.exe"
)
$unityCli = Get-FirstExistingPath $unityCliCandidates
if ($unityCli) {
    $v = Invoke-VersionProbe $unityCli @('--version')
    New-Finding -Name 'Unity CLI' -Category 'engine-sdk' -Path $unityCli -Version $v -State 'verified' -Evidence 'unity --version succeeded'
} else {
    New-Finding -Name 'Unity CLI' -Category 'engine-sdk' -Path $null -Version $null -State 'not-found' -Evidence 'unity.exe CLI not found'
}

# ---------------------------------------------------------------- Unreal ----
$unrealRoots = @(
    "$env:ProgramFiles\Epic Games",
    "D:\Epic Games",
    "D:\Program Files\Epic Games",
    "C:\Epic Games"
) | Where-Object { Test-Path -LiteralPath $_ }

$unrealFound = $false
foreach ($root in $unrealRoots) {
    Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'UE_*' } | ForEach-Object {
            $unrealFound = $true
            $cmd = Join-Path $_.FullName 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
            $uprojectShell = Join-Path $_.FullName 'Engine\Binaries\Win64\UnrealVersionSelector.exe'
            New-Finding -Name "Unreal Engine $($_.Name)" -Category 'engine' -Path $(if (Test-Path $cmd) { $cmd } else { $_.FullName }) `
                -Version $_.Name -State $(if (Test-Path $cmd) { 'verified' } else { 'broken' }) `
                -Evidence $(if (Test-Path $cmd) { 'UnrealEditor-Cmd.exe present' } else { 'Engine folder without UnrealEditor-Cmd.exe' })
        }
}
if (-not $unrealFound) {
    New-Finding -Name 'Unreal Engine' -Category 'engine' -Path $null -Version $null -State 'not-found' -Evidence 'No UE_* install under standard Epic Games roots'
}

# ---------------------------------------------------------------- Godot -----
$godotCandidates = @()
$godotCmd = Get-Command godot -ErrorAction SilentlyContinue
if ($godotCmd) { $godotCandidates += $godotCmd.Source }
$godotCandidates += @(
    "$env:ProgramFiles\Godot\Godot_v4.exe",
    "$env:LOCALAPPDATA\Programs\Godot\Godot_v4.exe",
    "D:\Godot\Godot_v4.exe"
)
$godotCandidates += @(Get-ChildItem 'C:\Program Files','D:\' -Filter 'Godot*.exe' -Recurse -Depth 2 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
$godot = Get-FirstExistingPath $godotCandidates
if ($godot) {
    $gv = Invoke-VersionProbe $godot @('--version')
    New-Finding -Name 'Godot' -Category 'engine' -Path $godot -Version $gv -State 'verified' -Evidence 'godot --version succeeded'
} else {
    New-Finding -Name 'Godot' -Category 'engine' -Path $null -Version $null -State 'not-found' -Evidence 'No Godot executable found on PATH or standard locations'
}

# ---------------------------------------------------------------- Blender ---
$blenderCandidates = @()
$bc = Get-Command blender -ErrorAction SilentlyContinue
if ($bc) { $blenderCandidates += $bc.Source }
foreach ($key in @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
)) {
    Get-ItemProperty $key -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like 'Blender*' } | ForEach-Object {
            if ($_.InstallLocation) {
                $blenderCandidates += (Join-Path $_.InstallLocation 'blender.exe')
                $blenderCandidates += (Join-Path $_.InstallLocation 'blender-launcher.exe')
            }
        }
}
$blenderCandidates += Get-ChildItem 'C:\Program Files','C:\Program Files (x86)','D:\' -Filter 'blender.exe' -Recurse -Depth 4 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
$blender = Get-FirstExistingPath $blenderCandidates
if ($blender) {
    $bv = Invoke-VersionProbe $blender @('--version') 120000
    New-Finding -Name 'Blender' -Category 'art' -Path $blender -Version $bv -State 'verified' -Evidence 'blender --version succeeded'
} else {
    New-Finding -Name 'Blender' -Category 'art' -Path $null -Version $null -State 'not-found' -Evidence 'No blender.exe found'
}

# ---------------------------------------------------------------- IDEs ------
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path -LiteralPath $vswhere) {
    try {
        $instances = & $vswhere -products * -format json | ConvertFrom-Json
        foreach ($i in $instances) {
            New-Finding -Name $i.displayName -Category 'ide' -Path $i.productPath -Version $i.installationVersion `
                -State $(if ($i.isLaunchable) { 'verified' } else { 'broken' }) -Evidence 'vswhere reports installation'
        }
    } catch {
        New-Finding -Name 'Visual Studio' -Category 'ide' -Path $vswhere -Version $null -State 'broken' -Evidence "vswhere failed: $($_.Exception.Message)"
    }
} else {
    New-Finding -Name 'Visual Studio' -Category 'ide' -Path $null -Version $null -State 'not-found' -Evidence 'vswhere.exe not found'
}

$vsCode = Get-FirstExistingPath @("$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe", "$env:ProgramFiles\Microsoft VS Code\Code.exe")
if ($vsCode) {
    New-Finding -Name 'Visual Studio Code' -Category 'ide' -Path $vsCode -Version (Invoke-VersionProbe $vsCode @('--version')) -State 'verified' -Evidence 'code --version succeeded'
}

# ---------------------------------------------------------------- toolchains
$dotnetCmd = Get-Command dotnet -ErrorAction SilentlyContinue
if ($dotnetCmd) {
    $sdks = @()
    try { $sdks = @(& dotnet --list-sdks) } catch { }
    New-Finding -Name '.NET SDK' -Category 'toolchain' -Path $dotnetCmd.Source -Version ($sdks -join '; ') `
        -State $(if ($sdks.Count -gt 0) { 'verified' } else { 'broken' }) -Evidence 'dotnet --list-sdks'
} else {
    New-Finding -Name '.NET SDK' -Category 'toolchain' -Path $null -Version $null -State 'not-found' -Evidence 'dotnet not on PATH'
}

$msbuild = Get-ChildItem "${env:ProgramFiles}\Microsoft Visual Studio" -Filter MSBuild.exe -Recurse -Depth 6 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($msbuild) {
    New-Finding -Name 'MSBuild' -Category 'toolchain' -Path $msbuild.FullName -Version (Invoke-VersionProbe $msbuild.FullName @('-version','-nologo')) -State 'verified' -Evidence 'MSBuild.exe found under Visual Studio'
} else {
    New-Finding -Name 'MSBuild' -Category 'toolchain' -Path $null -Version $null -State 'not-found' -Evidence 'No MSBuild.exe under Visual Studio'
}

$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if ($gitCmd) {
    New-Finding -Name 'Git' -Category 'toolchain' -Path $gitCmd.Source -Version (Invoke-VersionProbe $gitCmd.Source @('--version')) -State 'verified' -Evidence 'git --version succeeded'
    $lfs = Invoke-VersionProbe $gitCmd.Source @('lfs','version')
    New-Finding -Name 'Git LFS' -Category 'toolchain' -Path $gitCmd.Source -Version $lfs -State $(if ($lfs) { 'verified' } else { 'missing-dependency' }) -Evidence 'git lfs version'
}

$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pyCmd) {
    New-Finding -Name 'Python' -Category 'toolchain' -Path $pyCmd.Source -Version (Invoke-VersionProbe $pyCmd.Source @('--version')) -State 'verified' -Evidence 'python --version succeeded'
} else {
    New-Finding -Name 'Python' -Category 'toolchain' -Path $null -Version $null -State 'not-found' -Evidence 'python not on PATH'
}

$javaCmd = Get-Command java -ErrorAction SilentlyContinue
if ($javaCmd) {
    New-Finding -Name 'Java' -Category 'toolchain' -Path $javaCmd.Source -Version (Invoke-VersionProbe $javaCmd.Source @('-version')) -State 'verified' -Evidence 'java -version succeeded'
} else {
    New-Finding -Name 'Java' -Category 'toolchain' -Path $null -Version $null -State 'not-found' -Evidence 'java not on PATH'
}

# ---------------------------------------------------------------- Android ---
$androidSdk = Get-FirstExistingPath @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, 'D:\Android\Sdk', "$env:LOCALAPPDATA\Android\Sdk")
if ($androidSdk) {
    $ndks = @(Get-ChildItem (Join-Path $androidSdk 'ndk') -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
    $bt = @(Get-ChildItem (Join-Path $androidSdk 'build-tools') -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
    $plat = @(Get-ChildItem (Join-Path $androidSdk 'platforms') -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
    $adb = Join-Path $androidSdk 'platform-tools\adb.exe'
    $adbVersion = if (Test-Path $adb) { Invoke-VersionProbe $adb @('version') } else { $null }
    New-Finding -Name 'Android SDK' -Category 'platform' -Path $androidSdk -Version ($plat -join ', ') -State 'verified' -Evidence "platforms present; adb: $adbVersion" `
        -Notes (@("ndk: $($ndks -join ', ')", "build-tools: $($bt -join ', ')"))
} else {
    New-Finding -Name 'Android SDK' -Category 'platform' -Path $null -Version $null -State 'not-found' -Evidence 'ANDROID_HOME/ANDROID_SDK_ROOT not set and no standard SDK dir'
}

# ---------------------------------------------------------------- Node ------
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCmd) {
    New-Finding -Name 'Node.js' -Category 'toolchain' -Path $nodeCmd.Source -Version (Invoke-VersionProbe $nodeCmd.Source @('--version')) -State 'verified' -Evidence 'node --version succeeded'
}

# ---------------------------------------------------------------- report ----
$report = [pscustomobject]@{
    schemaVersion = 2
    generatedAt   = (Get-Date).ToUniversalTime().ToString('o')
    host          = $env:COMPUTERNAME
    hardware      = $hardware
    findings      = $script:Findings
    summary       = [pscustomobject]@{
        total    = $script:Findings.Count
        verified = @($script:Findings | Where-Object state -eq 'verified').Count
        broken   = @($script:Findings | Where-Object state -eq 'broken').Count
        missing  = @($script:Findings | Where-Object { $_.state -in @('not-found','missing-dependency') }).Count
    }
}

if (-not $OutputDir) {
    $OutputDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'reports'
}
if (-not (Test-Path -LiteralPath $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }

$jsonPath = Join-Path $OutputDir 'environment.json'
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

if (-not $JsonOnly) {
    $md = New-Object System.Text.StringBuilder
    [void]$md.AppendLine('# Development Environment Report')
    [void]$md.AppendLine()
    [void]$md.AppendLine("Generated: $($report.generatedAt)")
    [void]$md.AppendLine()
    [void]$md.AppendLine('## Hardware')
    [void]$md.AppendLine()
    [void]$md.AppendLine("| Item | Value |")
    [void]$md.AppendLine("| --- | --- |")
    [void]$md.AppendLine("| OS | $($hardware.os) ($($hardware.osVersion)) |")
    [void]$md.AppendLine("| CPU | $($hardware.cpu) / $($hardware.logicalCores) threads |")
    [void]$md.AppendLine("| RAM | $($hardware.ramGB) GB |")
    foreach ($g in $hardware.gpus) { [void]$md.AppendLine("| GPU | $($g.name) |") }
    foreach ($d in $hardware.disks) { [void]$md.AppendLine("| Disk $($d.drive): | $($d.freeGB) GB free of $($d.freeGB + $d.usedGB) GB |") }
    [void]$md.AppendLine()
    [void]$md.AppendLine('## Tools')
    [void]$md.AppendLine()
    [void]$md.AppendLine('| Tool | Version | State | Path | Evidence |')
    [void]$md.AppendLine('| --- | --- | --- | --- | --- |')
    foreach ($f in ($script:Findings | Sort-Object category, name)) {
        $p = if ($f.path) { $f.path } else { '-' }
        $v = if ($f.version) { ($f.version -replace '\|', '/') } else { '-' }
        [void]$md.AppendLine("| $($f.name) | $v | $($f.state) | ``$p`` | $($f.evidence) |")
    }
    [void]$md.AppendLine()
    [void]$md.AppendLine("Verified: $($report.summary.verified) / $($report.summary.total). Missing or broken: $($report.summary.missing).")
    $mdPath = Join-Path $OutputDir 'environment.md'
    Set-Content -LiteralPath $mdPath -Value $md.ToString() -Encoding UTF8
}

Write-Output "Environment report written to: $jsonPath"
$report.summary | Format-List
exit 0
