<#
  Windows bootstrap for the Google Flow Director skill. Idempotent: run it as often as you like.

    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1

  Installs only what is missing, per-user (no admin needed where possible), never asks questions,
  and prints ONE JSON report at the end: items[] with found / version / installed_now / fix_if_failed,
  plus the python to use. Read the report; if something failed, do what fix_if_failed says and re-run.
  Needs: Windows 10/11, PowerShell 5.1+, internet. winget is used when present, direct downloads otherwise.
#>
param([switch]$SkipChrome)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
$env:PYTHONUTF8 = '1'

$FlowHome = if ($env:FLOW_DIRECTOR_HOME) { $env:FLOW_DIRECTOR_HOME } else { Join-Path $env:USERPROFILE '.flow-director' }
$BinDir = Join-Path $FlowHome 'bin'
$SkillDir = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path $FlowHome, $BinDir | Out-Null
$Report = New-Object System.Collections.ArrayList

function Add-Item($Item, $Found, $Version, $Installed, $Fix) {
    [void]$Report.Add([ordered]@{ item = $Item; found = [bool]$Found; version = "$Version"; installed_now = [bool]$Installed; fix_if_failed = $Fix })
}

function Update-SessionPath {
    # Re-read PATH so tools installed a second ago are usable now, without reopening the terminal.
    $parts = @(
        [Environment]::GetEnvironmentVariable('Path', 'Machine'),
        [Environment]::GetEnvironmentVariable('Path', 'User'),
        $BinDir,
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links')
    )
    $env:Path = ($parts | Where-Object { $_ }) -join ';'
}

function Get-Download($Url, $Dest) { Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing }

function Install-Winget($Id, [bool]$UserScope) {
    # winget exit codes are unreliable ("already installed" is non-zero), so callers re-detect instead.
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $false }
    $a = @('install', '--id', $Id, '-e', '--silent', '--accept-package-agreements', '--accept-source-agreements')
    if ($UserScope) { $a += @('--scope', 'user') }
    try { & winget @a 2>&1 | Out-Null } catch {}
    Update-SessionPath
    return $true
}

function Find-Python {
    $cands = New-Object System.Collections.ArrayList
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try { $o = & py -3 -c "import sys;print(sys.executable)" 2>$null; if ($o) { [void]$cands.Add("$o".Trim()) } } catch {}
    }
    foreach ($c in @(Get-Command python -All -ErrorAction SilentlyContinue)) {
        # The Microsoft Store "python.exe" in WindowsApps is a stub, not Python.
        if ($c.Source -and $c.Source -notmatch 'WindowsApps') { [void]$cands.Add($c.Source) }
    }
    foreach ($root in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles\Python*")) {
        Get-ChildItem -Path $root -Filter python.exe -Recurse -Depth 2 -ErrorAction SilentlyContinue |
            ForEach-Object { [void]$cands.Add($_.FullName) }
    }
    foreach ($c in $cands) {
        if (-not (Test-Path $c)) { continue }
        try {
            $v = & $c -c "import sys;print(sys.executable if sys.version_info>=(3,10) else '')" 2>$null
            if ($v) { return "$v".Trim() }
        } catch {}
    }
    return $null
}

function Find-Tool($Name) {
    $c = Get-Command $Name -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $p = Join-Path $BinDir "$Name.exe"
    if (Test-Path $p) { return $p }
    return $null
}

function Find-Chrome {
    $paths = New-Object System.Collections.ArrayList
    foreach ($hive in @('HKLM', 'HKCU')) {
        try {
            $v = (Get-ItemProperty "${hive}:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -ErrorAction Stop).'(default)'
            if ($v) { [void]$paths.Add($v) }
        } catch {}
    }
    foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if ($root) { [void]$paths.Add((Join-Path $root 'Google\Chrome\Application\chrome.exe')) }
    }
    foreach ($p in $paths) { if ($p -and (Test-Path $p)) { return $p } }
    foreach ($root in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if ($root) { $e = Join-Path $root 'Microsoft\Edge\Application\msedge.exe'; if (Test-Path $e) { return $e } }
    }
    return $null
}

Update-SessionPath

# ---- Python 3.10+ -----------------------------------------------------------------------------
$python = Find-Python
$installedNow = $false
if (-not $python) {
    Install-Winget 'Python.Python.3.12' $true | Out-Null
    $python = Find-Python
    if (-not $python) {
        $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
        $installer = Join-Path $env:TEMP "python-3.12.8-$arch.exe"
        try {
            Get-Download "https://www.python.org/ftp/python/3.12.8/python-3.12.8-$arch.exe" $installer
            Start-Process -FilePath $installer -Wait -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=0', 'Include_test=0'
        } catch {}
        Update-SessionPath
        $python = Find-Python
    }
    $installedNow = [bool]$python
}
$pyVer = if ($python) { (& $python -c "import sys;print(sys.version.split()[0])" 2>$null) } else { '' }
Add-Item 'python' $python $pyVer $installedNow 'Install Python 3.10+ from https://www.python.org/downloads/windows/ (tick "Add python.exe to PATH"), then re-run this script.'

# ---- ffmpeg + ffprobe -------------------------------------------------------------------------
$ffmpeg = Find-Tool 'ffmpeg'; $ffprobe = Find-Tool 'ffprobe'
$installedNow = $false
if (-not ($ffmpeg -and $ffprobe)) {
    Install-Winget 'Gyan.FFmpeg' $false | Out-Null
    $ffmpeg = Find-Tool 'ffmpeg'; $ffprobe = Find-Tool 'ffprobe'
    if (-not ($ffmpeg -and $ffprobe)) {
        $zip = Join-Path $env:TEMP 'ffmpeg-essentials.zip'
        $tmp = Join-Path $env:TEMP 'ffmpeg-essentials'
        try {
            Get-Download 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' $zip
            if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
            Expand-Archive -Path $zip -DestinationPath $tmp -Force
            foreach ($n in @('ffmpeg.exe', 'ffprobe.exe')) {
                $f = Get-ChildItem -Path $tmp -Filter $n -Recurse | Select-Object -First 1
                if ($f) { Copy-Item $f.FullName (Join-Path $BinDir $n) -Force }
            }
        } catch {}
        Update-SessionPath
        $ffmpeg = Find-Tool 'ffmpeg'; $ffprobe = Find-Tool 'ffprobe'
    }
    $installedNow = [bool]($ffmpeg -and $ffprobe)
}
$ffVer = if ($ffmpeg) { ((& $ffmpeg -version 2>$null | Select-Object -First 1) -replace 'ffmpeg version ', '') } else { '' }
Add-Item 'ffmpeg+ffprobe' ($ffmpeg -and $ffprobe) $ffVer $installedNow 'Download the "essentials" zip from https://www.gyan.dev/ffmpeg/builds/ , copy ffmpeg.exe and ffprobe.exe into ~\.flow-director\bin, re-run.'

# ---- Chrome (Edge is an acceptable fallback; it ships with Windows) ------------------------------
if (-not $SkipChrome) {
    $chrome = Find-Chrome
    $installedNow = $false
    if (-not $chrome -or $chrome -match 'msedge') {
        Install-Winget 'Google.Chrome' $false | Out-Null
        $after = Find-Chrome
        if ($after -and $after -ne $chrome) { $installedNow = $true }
        if ($after) { $chrome = $after }
    }
    Add-Item 'browser' $chrome $(if ($chrome) { Split-Path -Leaf $chrome } else { '' }) $installedNow 'Install Google Chrome from https://www.google.com/chrome/ (Edge also works), then re-run.'
}

# ---- private venv with playwright + pillow -------------------------------------------------------
$venv = Join-Path $FlowHome 'venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
$depsOk = $false; $installedNow = $false
if ($python) {
    if (-not (Test-Path $venvPy)) { & $python -m venv $venv 2>&1 | Out-Null; $installedNow = $true }
    if (Test-Path $venvPy) {
        $check = & $venvPy -c "import playwright, PIL; print('ok')" 2>$null
        if ($check -ne 'ok') {
            & $venvPy -m pip install --upgrade pip --quiet 2>&1 | Out-Null
            & $venvPy -m pip install --quiet playwright pillow 2>&1 | Out-Null
            $check = & $venvPy -c "import playwright, PIL; print('ok')" 2>$null
            $installedNow = $true
        }
        $depsOk = ($check -eq 'ok')
    }
}
Add-Item 'python-deps (playwright, pillow)' $depsOk '' $(if ($depsOk) { $installedNow } else { $false }) 'Run: python -m venv "$env:USERPROFILE\.flow-director\venv" ; then "$env:USERPROFILE\.flow-director\venv\Scripts\python.exe" -m pip install playwright pillow'

# ---- captions font ------------------------------------------------------------------------------
$fontsDir = Join-Path $(if ($env:WINDIR) { $env:WINDIR } else { 'C:\Windows' }) 'Fonts'
$font = @('segoeui.ttf', 'arial.ttf', 'calibri.ttf') | ForEach-Object { Join-Path $fontsDir $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
Add-Item 'caption-font' $font '' $false 'Set "font" in ~\.flow-director\config.json to any .ttf file (Pillow also has a built-in fallback).'

$result = [ordered]@{
    ok     = [bool]($python -and ($ffmpeg -and $ffprobe) -and $depsOk)
    items  = @($Report)
    python = $venvPy
    flow   = (Join-Path $SkillDir 'scripts\flow.py')
    next   = "Run: `"$venvPy`" `"$(Join-Path $SkillDir 'scripts\flow.py')`" setup   (flow.py also runs under any Python 3.10+ and re-launches itself in the venv)"
}
$result | ConvertTo-Json -Depth 5
