param(
    [switch]$FromStable
)

$ErrorActionPreference = "Continue"

function Get-StableDir {
    if (Test-Path "D:\") {
        return "D:\AvtonomeraSeetong"
    }
    return Join-Path $env:USERPROFILE "AvtonomeraSeetong"
}

function Get-FullPath([string]$path) {
    if (-not $path) { return "" }
    try {
        return [IO.Path]::GetFullPath($path.TrimEnd("\", "/"))
    } catch {
        return $path
    }
}

function Get-SearchRoots {
    $roots = New-Object System.Collections.Generic.List[string]
    foreach ($item in @(
        $PSScriptRoot,
        [Environment]::GetFolderPath("Desktop"),
        (Join-Path $env:USERPROFILE "Desktop"),
        (Join-Path $env:USERPROFILE "Downloads"),
        [Environment]::GetFolderPath("MyDocuments"),
        "D:\",
        "C:\"
    )) {
        if ($item -and (Test-Path $item)) {
            $roots.Add((Get-FullPath $item)) | Out-Null
        }
    }
    return $roots
}

function Find-AnprSource([string]$start) {
    $hits = New-Object System.Collections.Generic.List[object]
    if ($start -and (Test-Path (Join-Path $start "anpr_gui.py"))) {
        $gui = Get-Item (Join-Path $start "anpr_gui.py")
        $hits.Add([pscustomobject]@{ Path = (Get-FullPath $start); Time = $gui.LastWriteTimeUtc }) | Out-Null
    }
    foreach ($root in Get-SearchRoots) {
        if (Test-Path (Join-Path $root "anpr_gui.py")) {
            $gui = Get-Item (Join-Path $root "anpr_gui.py")
            $hits.Add([pscustomobject]@{ Path = (Get-FullPath $root); Time = $gui.LastWriteTimeUtc }) | Out-Null
        }
        Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -like "my_search_gpu_bot*" -or $_.Name -eq "AvtonomeraSeetong"
        } | ForEach-Object {
            $guiPath = Join-Path $_.FullName "anpr_gui.py"
            if (Test-Path $guiPath) {
                $gui = Get-Item $guiPath
                $hits.Add([pscustomobject]@{ Path = (Get-FullPath $_.FullName); Time = $gui.LastWriteTimeUtc }) | Out-Null
            }
            Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                $nested = Join-Path $_.FullName "anpr_gui.py"
                if (Test-Path $nested) {
                    $gui = Get-Item $nested
                    $hits.Add([pscustomobject]@{ Path = (Get-FullPath $_.FullName); Time = $gui.LastWriteTimeUtc }) | Out-Null
                }
            }
        }
    }
    if ($hits.Count -eq 0) { return $null }
    # Prefer the newest extract so an old D:\AvtonomeraSeetong is not kept forever.
    $best = $hits | Sort-Object Time -Descending | Select-Object -First 1
    return $best.Path
}

function Stop-AnprProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match "python" -and $_.CommandLine -match "anpr_gui.py"
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Copy-Anpr([string]$src, [string]$dst) {
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    $anprDst = Join-Path $dst "anpr"
    if (Test-Path $anprDst) {
        Remove-Item $anprDst -Recurse -Force -ErrorAction SilentlyContinue
    }
    $names = @(
        "anpr_gui.py", "anpr_icon.ico", "START_ANPR.bat", "INSTALL_ANPR.bat",
        "DESKTOP_SHORTCUT_ANPR.bat", "MAKE_DESKTOP_SHORTCUT.ps1",
        "FIX_AND_CLEAN.ps1", "FIX_AND_CLEAN.bat", "requirements-anpr.txt",
        "UNINSTALL_COMPLETE.ps1", "UNINSTALL_COMPLETE.bat", "UPDATE_NOW.bat"
    )
    foreach ($name in $names) {
        $from = Join-Path $src $name
        if (Test-Path $from) {
            Copy-Item $from (Join-Path $dst $name) -Force
        }
    }
    Get-ChildItem $src -File -ErrorAction SilentlyContinue | Where-Object {
        $_.Extension -in ".bat", ".ps1" -and $_.Name -notmatch "bot|sports|wechat|START_APP|START_GUI"
    } | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $dst $_.Name) -Force
    }
    $anprSrc = Join-Path $src "anpr"
    if (Test-Path $anprSrc) {
        Copy-Item $anprSrc $anprDst -Recurse -Force
    }
}

function Copy-NewestDatabase([string]$stable) {
    $destDir = Join-Path $stable "anpr_data"
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $found = @()
    foreach ($root in Get-SearchRoots) {
        Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -like "my_search_gpu_bot*" -or $_.Name -eq "AvtonomeraSeetong"
        } | ForEach-Object {
            $db = Join-Path $_.FullName "anpr_data\anpr.db"
            if (Test-Path $db) { $found += Get-Item $db }
            Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                $nested = Join-Path $_.FullName "anpr_data\anpr.db"
                if (Test-Path $nested) { $found += Get-Item $nested }
            }
        }
    }
    if (-not $found) { return }
    $best = $found | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $destDb = Join-Path $destDir "anpr.db"
    if ((-not (Test-Path $destDb)) -or ($best.LastWriteTime -gt (Get-Item $destDb).LastWriteTime)) {
        Copy-Item (Join-Path $best.DirectoryName "*") $destDir -Recurse -Force
        Write-Host ("Kept vehicle database from: " + $best.FullName)
    }
}

function Remove-LeftoverCopies([string]$stable) {
    $stableFull = Get-FullPath $stable
    $telega = -join @(
        [char]0x0442, [char]0x0435, [char]0x043B, [char]0x0435, [char]0x0433, [char]0x0430,
        " ",
        [char]0x0431, [char]0x043E, [char]0x0442
    )
    foreach ($root in Get-SearchRoots) {
        Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -like "my_search_gpu_bot*" -or $_.Name -eq $telega
        } | ForEach-Object {
            $full = Get-FullPath $_.FullName
            if ($full -eq $stableFull) { return }
            if ($full -like "*\Seetong*") { return }
            Write-Host ("Deleting extra folder: " + $_.FullName)
            Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
        Get-ChildItem $root -File -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -like "my_search_gpu_bot*.zip"
        } | ForEach-Object {
            Write-Host ("Deleting extra zip: " + $_.FullName)
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        }
    }
    $botFast = Join-Path $env:USERPROFILE "bot_fast.py"
    if (Test-Path $botFast) {
        Remove-Item $botFast -Force -ErrorAction SilentlyContinue
    }
}

function Install-Packages([string]$dir) {
    $req = Join-Path $dir "requirements-anpr.txt"
    $py = $null
    foreach ($cmd in @("py", "python")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { $py = $found.Source; break }
    }
    if (-not $py) {
        Write-Host "Python not found. Install Python 3 and enable Add python.exe to PATH."
        return $false
    }
    $code = "import cv2,numpy,PIL,mss"
    & $py -c $code 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing packages, please wait..."
        if (Test-Path $req) {
            & $py -m pip install -r $req
        }
        if ($LASTEXITCODE -ne 0) {
            & $py -m pip install opencv-python Pillow mss numpy
        }
        & $py -m pip install rapidocr-onnxruntime 2>$null
    }
    return $true
}

function Start-Anpr([string]$dir) {
    $gui = Join-Path $dir "anpr_gui.py"
    $pyw = $null
    $cmd = Get-Command "pythonw.exe" -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        $pyw = $cmd.Source
    } else {
        $py = Get-Command "python.exe" -ErrorAction SilentlyContinue
        if ($py -and $py.Source) {
            $candidate = Join-Path (Split-Path -Parent $py.Source) "pythonw.exe"
            if (Test-Path $candidate) { $pyw = $candidate }
        }
    }
    if ($pyw) {
        Start-Process -FilePath $pyw -ArgumentList "`"$gui`"" -WorkingDirectory $dir
    } else {
        Start-Process -FilePath "python" -ArgumentList "`"$gui`"" -WorkingDirectory $dir
    }
}

$stable = Get-StableDir
$here = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$source = Find-AnprSource $here
if (-not $source) {
    Write-Host "anpr_gui.py not found. Close WinRAR. Open the yellow folder."
    if (-not $FromStable) { pause }
    exit 1
}

Write-Host ("Newest program folder: " + $source)
Write-Host ("Install to: " + $stable)

# Always refresh D:\AvtonomeraSeetong from the newest extract.
if ((Get-FullPath $source) -ne (Get-FullPath $stable)) {
    Stop-AnprProcesses
    Copy-Anpr $source $stable
    Copy-NewestDatabase $stable
    $next = Join-Path $stable "FIX_AND_CLEAN.ps1"
    if (-not (Test-Path $next)) {
        Write-Host "Copy failed."
        if (-not $FromStable) { pause }
        exit 1
    }
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $next, "-FromStable"
    ) -WorkingDirectory $stable
    exit 0
}

# Even when already in the stable folder, refresh files if a newer extract exists.
$newest = Find-AnprSource ""
if ($newest -and ((Get-FullPath $newest) -ne (Get-FullPath $stable))) {
    Write-Host ("Updating from newer folder: " + $newest)
    Stop-AnprProcesses
    Copy-Anpr $newest $stable
}

Copy-NewestDatabase $stable
if (-not (Install-Packages $stable)) {
    if (-not $FromStable) { pause }
    exit 1
}

$shortcut = Join-Path $stable "MAKE_DESKTOP_SHORTCUT.ps1"
if (Test-Path $shortcut) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $shortcut
}

$verFile = Join-Path $stable "anpr\version.py"
if (Test-Path $verFile) {
    Write-Host ("Version file: " + (Get-Content $verFile | Select-String "APP_VERSION"))
}

Stop-AnprProcesses
Start-Anpr $stable
Start-Sleep -Seconds 1
Remove-LeftoverCopies $stable

Write-Host ""
Write-Host "Ready. Check window title contains: 2026.08.22-r4"
Write-Host "Use desktop icon: Avtonomera Seetong / Автономера Seetong"
Write-Host ("Folder: " + $stable)
Write-Host "If title has no 2026.08.22-r4 — you still opened the OLD program."
if (-not $FromStable) {
    Start-Sleep -Seconds 6
}
exit 0
