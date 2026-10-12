# Kut (eski adi Agim) kurulumu (Windows). Calistir: sag tik -> "PowerShell ile calistir"
# ya da: powershell -ExecutionPolicy Bypass -File baslatma\kur.ps1 [-Veri KLASOR]
# -Veri verilirse kisayol Kut'u o veri klasoruyle acar (kisisel veri depo disinda tutulur).
# Python bulur, masaustu + Baslat menusune "Kut" kisayolu kurar, agi acar. Internetten bir sey indirmez.
param([string]$Veri = '')
$ErrorActionPreference = 'Stop'
$kok = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$arg = '"' + (Join-Path $kok 'kut.pyw') + '"'
if ($Veri) { $arg += ' --veri "' + $Veri + '"' }

$py = $null
foreach ($aday in @('pyw.exe', 'pythonw.exe')) {
    $k = Get-Command $aday -ErrorAction SilentlyContinue
    if ($k -and $k.Source -notmatch 'WindowsApps') { $py = $k.Source; break }
}
if (-not $py) {
    $yerel = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter pythonw.exe -Recurse -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
    if ($yerel) { $py = $yerel.FullName }
}
if (-not $py) {
    Write-Host 'Python bulunamadi. Once Python 3 kur:' -ForegroundColor Yellow
    Write-Host '  winget install Python.Python.3.12   (ya da python.org/downloads, "Add to PATH" isaretli)'
    Write-Host 'Sonra bu dosyayi tekrar calistir.'
    Read-Host 'Kapatmak icin Enter'
    exit 1
}

$ad = 'Kut'
$sh = New-Object -ComObject WScript.Shell
$yerler = @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))
foreach ($yer in $yerler) {
    $s = $sh.CreateShortcut((Join-Path $yer "$ad.lnk"))
    $s.TargetPath = $py
    $s.Arguments = $arg
    $s.WorkingDirectory = $kok
    $ico = Join-Path $kok 'kut\kut.ico'
    if (Test-Path $ico) { $s.IconLocation = "$ico,0" } else { $s.IconLocation = "$env:SystemRoot\System32\shell32.dll,17" }
    $s.Description = 'Kut: kisisel ag'
    $s.Save()
}
if ($Veri) { $vy = $Veri } else { $vy = Join-Path $kok 'veri' }
Write-Host "Kuruldu. Masaustundeki '$ad' kisayolu agi acar. Veriler: $vy" -ForegroundColor Green
Start-Process $py -ArgumentList $arg -WorkingDirectory $kok
