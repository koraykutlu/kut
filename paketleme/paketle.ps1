# Kut.exe derleyici (Windows PowerShell 5.1). Calistir: powershell -ExecutionPolicy Bypass -File paketleme\paketle.ps1 [-Cikti KLASOR]
# Ayri bir venv'e sabit surum PyInstaller kurar; dist\Kut.exe ve yaninda Kut.exe.sha256 uretir. Global hicbir sey kurmaz.
# Surum kut\surum.py'den okunur (exe dosya bilgisine yazilir). Yayin: GitHub Release'e Kut.exe + Kut.exe.sha256 yuklenir (README 'Yayin').
param([string]$Cikti = '')
$ErrorActionPreference = 'Stop'
$PyInstallerSurum = '6.11.1'
$depo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Cikti) { $Cikti = Join-Path $depo 'build-exe' }
New-Item -ItemType Directory -Force $Cikti | Out-Null
$sm = Select-String -Path (Join-Path $depo 'kut\surum.py') -Pattern '^SURUM\s*=\s*"(\d+)\.(\d+)\.(\d+)"'
if (-not $sm) { throw 'kut\surum.py icinde SURUM bulunamadi' }
$sv = $sm.Matches[0].Groups
$surum = '{0}.{1}.{2}' -f $sv[1].Value, $sv[2].Value, $sv[3].Value
$vs = "VSVersionInfo(ffi=FixedFileInfo(filevers=($($sv[1].Value),$($sv[2].Value),$($sv[3].Value),0), prodvers=($($sv[1].Value),$($sv[2].Value),$($sv[3].Value),0), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)), kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','Kut'),StringStruct('FileDescription','Kut'),StringStruct('FileVersion','$surum'),StringStruct('InternalName','Kut'),StringStruct('OriginalFilename','Kut.exe'),StringStruct('ProductName','Kut'),StringStruct('ProductVersion','$surum')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])"
$vsDosya = Join-Path $Cikti 'surum-bilgisi.txt'
[IO.File]::WriteAllText($vsDosya, $vs, (New-Object Text.ASCIIEncoding))
$env:KUT_SURUM_BILGISI = $vsDosya
$venv = Join-Path $Cikti 'venv'
if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
    & py -3 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'venv kurulamadi (Python 3 var mi?)' }
}
$py = Join-Path $venv 'Scripts\python.exe'
& $py -m pip install --disable-pip-version-check "pyinstaller==$PyInstallerSurum"
if ($LASTEXITCODE -ne 0) { throw 'pyinstaller kurulamadi' }
& $py -m PyInstaller --noconfirm --clean --distpath (Join-Path $Cikti 'dist') --workpath (Join-Path $Cikti 'work') (Join-Path $depo 'paketleme\kut.spec')
if ($LASTEXITCODE -ne 0) { throw 'derleme basarisiz' }
$exe = Join-Path $Cikti 'dist\Kut.exe'
$h = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
# Guncelleme sistemi bu dosyayi (ya da API'deki digest alanini) dogrulama icin kullanir; ASCII, BOM'suz: "<sha256>  Kut.exe"
[IO.File]::WriteAllText((Join-Path $Cikti 'dist\Kut.exe.sha256'), ($h + '  Kut.exe' + "`n"), (New-Object Text.ASCIIEncoding))
Write-Host ("Hazir: Kut {0}  {1} ({2:N1} MB) SHA-256 {3}" -f $surum, $exe, ((Get-Item $exe).Length / 1MB), $h)
Write-Host ("Yayin icin yukle: {0} ve {0}.sha256" -f $exe)
