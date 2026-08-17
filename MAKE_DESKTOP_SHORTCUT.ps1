$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ico = Join-Path $dir "anpr_icon.ico"
$bat = Join-Path $dir "START_ANPR.bat"
if (-not (Test-Path $bat)) { throw "START_ANPR.bat not found in $dir" }

$d = [Environment]::GetFolderPath("Desktop")
$n = [string]([char]0x0410) + [char]0x0432 + [char]0x0442 + [char]0x043E + [char]0x043D + [char]0x043E + [char]0x043C + [char]0x0435 + [char]0x0440 + [char]0x0430
$name = $n + " Seetong.lnk"
$p = Join-Path $d $name

# Overwrite in place. Do not delete the .lnk first: START from that icon would kill itself.
$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut($p)
$s.TargetPath = $bat
$s.WorkingDirectory = $dir
$s.WindowStyle = 1
$s.Description = "ANPR Seetong"
if (Test-Path $ico) {
    $s.IconLocation = $ico + ",0"
}
$s.Save()

# Also drop the Latin-name shortcut created by the python one-liner.
$latin = Join-Path $d "Avtonomera Seetong.lnk"
if ((Test-Path $latin) -and ($latin -ne $p)) { Remove-Item -Force $latin }

try { Start-Process -FilePath "ie4uinit.exe" -ArgumentList "-show" -WindowStyle Hidden } catch {}
Write-Host ("OK: " + $p)
