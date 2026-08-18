$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ico = Join-Path $dir "anpr_icon.ico"
$bat = Join-Path $dir "START_ANPR.bat"
$pyw = Join-Path $dir "anpr_gui.py"
if (-not (Test-Path $bat)) { throw "START_ANPR.bat not found in $dir" }

$d = [Environment]::GetFolderPath("Desktop")
$n = [string]([char]0x0410) + [char]0x0432 + [char]0x0442 + [char]0x043E + [char]0x043D + [char]0x043E + [char]0x043C + [char]0x0435 + [char]0x0440 + [char]0x0430
$name = $n + " Seetong.lnk"
$p = Join-Path $d $name

$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut($p)
$s.TargetPath = "pythonw.exe"
$s.Arguments = "`"$pyw`""
$s.WorkingDirectory = $dir
$s.WindowStyle = 1
$s.Description = "ANPR Seetong"
if (Test-Path $ico) {
    $s.IconLocation = $ico + ",0"
}
$s.Save()

# Also ensure English name shortcut points to pythonw directly
$latin = Join-Path $d "Avtonomera Seetong.lnk"
if ($latin -ne $p) {
    $s2 = $w.CreateShortcut($latin)
    $s2.TargetPath = "pythonw.exe"
    $s2.Arguments = "`"$pyw`""
    $s2.WorkingDirectory = $dir
    if (Test-Path $ico) { $s2.IconLocation = $ico + ",0" }
    $s2.Save()
}

try { Start-Process -FilePath "ie4uinit.exe" -ArgumentList "-show" -WindowStyle Hidden } catch {}
Write-Host ("OK: " + $p)
