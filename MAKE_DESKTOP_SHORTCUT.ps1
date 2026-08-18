$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ico = Join-Path $dir "anpr_icon.ico"
$bat = Join-Path $dir "START_ANPR.bat"
$pyw = Join-Path $dir "anpr_gui.py"
if (-not (Test-Path $bat)) { throw "START_ANPR.bat not found in $dir" }
if (-not (Test-Path $pyw)) { throw "anpr_gui.py not found in $dir" }

$d = [Environment]::GetFolderPath("Desktop")
$n = [string]([char]0x0410) + [char]0x0432 + [char]0x0442 + [char]0x043E + [char]0x043D + [char]0x043E + [char]0x043C + [char]0x0435 + [char]0x0440 + [char]0x0430
$name = $n + " Seetong.lnk"
$p = Join-Path $d $name

# Find full path to pythonw.exe so the shortcut does not open a black cmd window.
$pywExe = "pythonw.exe"
try {
    $cmd = Get-Command "pythonw.exe" -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        $pywExe = $cmd.Source
    } else {
        $pyCmd = Get-Command "python.exe" -ErrorAction SilentlyContinue
        if ($pyCmd -and $pyCmd.Source) {
            $candidate = Join-Path (Split-Path -Parent $pyCmd.Source) "pythonw.exe"
            if (Test-Path $candidate) { $pywExe = $candidate }
        }
    }
} catch {}

$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut($p)
$s.TargetPath = $pywExe
$s.Arguments = "`"$pyw`""
$s.WorkingDirectory = $dir
$s.WindowStyle = 1
$s.Description = "ANPR Seetong"
if (Test-Path $ico) {
    $s.IconLocation = $ico + ",0"
}
$s.Save()

$latin = Join-Path $d "Avtonomera Seetong.lnk"
if ($latin -ne $p) {
    $s2 = $w.CreateShortcut($latin)
    $s2.TargetPath = $pywExe
    $s2.Arguments = "`"$pyw`""
    $s2.WorkingDirectory = $dir
    $s2.WindowStyle = 1
    if (Test-Path $ico) { $s2.IconLocation = $ico + ",0" }
    $s2.Save()
}

try { Start-Process -FilePath "ie4uinit.exe" -ArgumentList "-show" -WindowStyle Hidden } catch {}
Write-Host ("OK: " + $p)
