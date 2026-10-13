# PyInstaller tarifi: Kut.exe (tek dosya, konsolsuz). Derleme: paketle.ps1
# -*- mode: python -*-
import os
depo = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))
kok = os.path.join(depo, 'kut')   # uygulama kodu ve varliklar kut/ altinda

demo_ses = [(os.path.join(kok, 'demo_ses'), 'demo_ses')] if os.path.isdir(os.path.join(kok, 'demo_ses')) else []   # onceden uretilmis demo anlatimi (paketleme/demo_seslendir.py); yoksa demo sessiz calisir

a = Analysis(
    [os.path.join(kok, 'ag_sunucu.py')],
    pathex=[kok],
    datas=[(os.path.join(kok, 'ag_sablon.html'), '.'),
           (os.path.join(kok, 'ag_ses_isci.py'), '.'),   # ses isci betigi baska bir Python ile calisir; veri olarak gerekir
           (os.path.join(kok, 'ag_cekirdek.py'), '.'),   # demo onizlemesi (ag_demo.py) bu ikisinin ozel kopyasini kurar; PYZ get_code calismazsa kaynak dosyadan
           (os.path.join(kok, 'ag_soz.py'), '.')] + demo_ses,
    hiddenimports=[],
    excludes=['tkinter', 'unittest', 'pydoc', 'test'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='Kut',
    icon=os.path.join(kok, 'kut.ico'),
    console=False,
    version=os.environ.get('KUT_SURUM_BILGISI') or None,   # paketle.ps1 surum.py'den uretir
    upx=False,
)
