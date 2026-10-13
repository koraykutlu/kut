"""Test yalıtımı: kut modülleri içe aktarılmadan ÖNCE LOCALAPPDATA ve AGIM_VERI geçici dizine çevrilir.

ag_ice_aktar.DEPO (ayarlar.json, sunucu.log, analiz/, sohbet/, ses/ ...) ve türevleri içe aktarma anında sabitlendiği için
bu modül her test dosyasında ilk içe aktarma olmalıdır (tests/__init__.py de aynısını yapar). Geçici dizin süreç çıkışında silinir.
Gerçek klasöre hiçbir koşulda dokunulmaz; yalnız yol karşılaştırması için ADI saklanır."""
import atexit
import os
import shutil
import tempfile

GERCEK_LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")   # yalnız karşılaştırma için; içeriği okunmaz
GERCEK_DEPO = os.path.join(GERCEK_LOCALAPPDATA, "agim") if GERCEK_LOCALAPPDATA else os.path.join(os.path.expanduser("~"), ".agim")

if os.environ.get("KUT_TEST_YALITIM_KOK"):   # alt süreç / yeniden içe aktarma: aynı geçici kökü kullan
    KOK = os.environ["KUT_TEST_YALITIM_KOK"]
    _SAHIP = False
else:
    KOK = tempfile.mkdtemp(prefix="kut-test-")
    os.environ["KUT_TEST_YALITIM_KOK"] = KOK
    _SAHIP = True
    atexit.register(lambda: shutil.rmtree(KOK, ignore_errors=True))

LOCALAPPDATA = os.path.join(KOK, "localappdata")
VERI = os.path.join(KOK, "veri")
os.makedirs(os.path.join(LOCALAPPDATA, "agim"), exist_ok=True)   # testler ia.DEPO'yu yamalasa da sunucu.GUNLUK (içe aktarmada sabitlenen) yazılabilsin
os.environ["LOCALAPPDATA"] = LOCALAPPDATA
os.environ["AGIM_VERI"] = VERI
