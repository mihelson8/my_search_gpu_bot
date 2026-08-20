param()

$ErrorActionPreference = "Continue"
Write-Host "========================================"
Write-Host " FULL REMOVE: Avtonomera Seetong"
Write-Host " Seetong camera program is NOT touched"
Write-Host "========================================"
Write-Host ""

function Get-FullPath([string]$path) {
    if (-not $path) { return "" }
    try { return [IO.Path]::GetFullPath($path.TrimEnd("\", "/")) }
    catch { return $path }
}

function Get-SearchRoots {
    $roots = New-Object System.Collections.Generic.List[string]
    foreach ($item in @(
        [Environment]::GetFolderPath("Desktop"),
        (Join-Path $env:USERPROFILE "Desktop"),
        (Join-Path $env:USERPROFILE "Downloads"),
        [Environment]::GetFolderPath("MyDocuments"),
        $env:USERPROFILE,
        "D:\",
        "C:\"
    )) {
        if ($item -and (Test-Path $item)) {
            $roots.Add((Get-FullPath $item)) | Out-Null
        }
    }
    return $roots
}

# 1. Stop running ANPR windows
Write-Host "1. Closing old program..."
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match "python" -and $_.CommandLine -match "anpr_gui\.py|AvtonomeraSeetong|START_ANPR"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

# 2. Remove desktop shortcuts
Write-Host "2. Removing desktop shortcuts..."
$desktop = [Environment]::GetFolderPath("Desktop")
$names = @(
    "Avtonomera Seetong.lnk",
    ([string]([char]0x0410) + [char]0x0432 + [char]0x0442 + [char]0x043E + [char]0x043D + [char]0x043E + [char]0x043C + [char]0x0435 + [char]0x0440 + [char]0x0430 + " Seetong.lnk"),
    "ANPR Seetong.lnk",
    "Автономера Seetong.lnk"
)
foreach ($name in $names) {
    $p = Join-Path $desktop $name
    if (Test-Path $p) {
        Remove-Item $p -Force -ErrorAction SilentlyContinue
        Write-Host ("   deleted: " + $p)
    }
}
# Also catch any .lnk that points to anpr_gui
Get-ChildItem $desktop -Filter "*.lnk" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $w = New-Object -ComObject WScript.Shell
        $s = $w.CreateShortcut($_.FullName)
        $target = ($s.TargetPath + " " + $s.Arguments + " " + $s.WorkingDirectory)
        if ($target -match "anpr_gui|AvtonomeraSeetong|START_ANPR|my_search_gpu_bot") {
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
            Write-Host ("   deleted shortcut: " + $_.Name)
        }
    } catch {}
}

# 3. Remove program folders
Write-Host "3. Removing program folders..."
$stableNames = @("AvtonomeraSeetong", "Avtonomera Seetong")
foreach ($root in Get-SearchRoots) {
    Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -like "my_search_gpu_bot*" -or
        $_.Name -in $stableNames -or
        $_.Name -like "my_search_gpu_bot-cursor-anpr*"
    } | ForEach-Object {
        if ($_.FullName -like "*\Seetong*") { return }
        Write-Host ("   deleting folder: " + $_.FullName)
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Explicit known paths
foreach ($path in @(
    "D:\AvtonomeraSeetong",
    (Join-Path $env:USERPROFILE "AvtonomeraSeetong"),
    "D:\my_search_gpu_bot-cursor-anpr-seetong-plates-6b83",
    "D:\my_search_gpu_bot-cursor-anpr-seetong-fix-0821"
)) {
    if (Test-Path $path) {
        Write-Host ("   deleting: " + $path)
        Remove-Item $path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# 4. Remove ZIP archives
Write-Host "4. Removing old ZIP files..."
foreach ($root in Get-SearchRoots) {
    Get-ChildItem $root -File -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -like "my_search_gpu_bot*.zip" -or
        $_.Name -like "*anpr-seetong*.zip"
    } | ForEach-Object {
        Write-Host ("   deleting zip: " + $_.FullName)
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
    }
}

# 5. Remove stray files
Write-Host "5. Removing leftover files..."
foreach ($path in @(
    (Join-Path $env:USERPROFILE "bot_fast.py"),
    (Join-Path $env:USERPROFILE "anpr_gui.py")
)) {
    if (Test-Path $path) {
        Remove-Item $path -Force -ErrorAction SilentlyContinue
        Write-Host ("   deleted: " + $path)
    }
}

Write-Host ""
Write-Host "DONE. Old Avtonomera program removed."
Write-Host "Seetong Lite Client is still installed."
Write-Host ""
Write-Host "Next:"
Write-Host "1. Download new ZIP"
Write-Host "2. Extract All"
Write-Host "3. Open yellow folder"
Write-Host "4. Double-click START_ANPR.bat"
Write-Host ""
pause
