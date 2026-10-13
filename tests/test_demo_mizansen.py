"""Demo önizlemesi ("Deniz'in salısı"): senaryo verisi, yalıtım (gerçek veri/ayar klasörüne yazma yok), kapanışta silme, kapılar
(anahtar / Origin / kilit), ağ ve model yokluğu, arayüzde esc ile basım, sessiz çalışma ve Gemini TTS betiği (statik).
Tarayıcı gerekmez; sunucu testleri ayrı süreçte, geçici LOCALAPPDATA ve geçici TMP ile çalışır."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import hashlib
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from datetime import date, timedelta
from unittest import mock

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOK = os.path.join(DEPO, "kut")
sys.path.insert(0, KOK)
import ag_cekirdek as c  # noqa: E402
import ag_demo  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_kaynak as kn  # noqa: E402
import ag_model as mdl  # noqa: E402
import ag_sunucu as sunucu  # noqa: E402

SABLON = os.path.join(KOK, "ag_sablon.html")
BETIK = os.path.join(DEPO, "paketleme", "demo_seslendir.py")


def sablon():
    with open(SABLON, encoding="utf-8") as f:
        return f.read()


def goruntu(klasor):
    """Klasördeki her dosyanın (yol → boyut, sha1) anlık görüntüsü."""
    s = {}
    for kok, _, dosyalar in os.walk(klasor):
        for d in dosyalar:
            y = os.path.join(kok, d)
            with open(y, "rb") as f:
                s[os.path.relpath(y, klasor)] = (os.path.getsize(y), hashlib.sha1(f.read()).hexdigest())
    return s


class DemoOrtami(unittest.TestCase):
    """Her test: geçici TMP (demo klasörleri oraya düşer), geçici gerçek veri + ayar klasörü; gerçek modül demoyla değişmemeli."""

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.tmp = os.path.join(self.t.name, "tmp")
        self.veri = os.path.join(self.t.name, "gercek-veri")
        self.depo = os.path.join(self.t.name, "ayar")
        for d in (self.tmp, self.depo):
            os.makedirs(d)
        self.eski = (c.VERI, ia.DEPO, ia.AYARLAR, ia.ADAYLAR, tempfile.tempdir, sunucu.GUNLUK)
        ia.DEPO, ia.AYARLAR, ia.ADAYLAR = self.depo, os.path.join(self.depo, "ayarlar.json"), os.path.join(self.depo, "adaylar.json")
        sunucu.GUNLUK = os.path.join(self.depo, "sunucu.log")
        tempfile.tempdir = self.tmp
        c.veri_klasoru(self.veri)
        c.kisi_yaz("ada-gercek", {"ad": "Ada Gercek", "tur": "yakin", "yakinlik": "3"}, "# Ada Gercek\n\n## Temas\n- (henüz yok)\n")
        self.gercek_once, self.ayar_once = goruntu(self.veri), goruntu(self.depo)
        ag_demo.kapat()

    def tearDown(self):
        ag_demo.kapat()
        c.veri_klasoru(self.eski[0])
        ia.DEPO, ia.AYARLAR, ia.ADAYLAR, tempfile.tempdir, sunucu.GUNLUK = self.eski[1:]
        self.t.cleanup()

    def demo_dizinleri(self):
        return [d for d in os.listdir(self.tmp) if d.startswith(ag_demo.DIZIN_ONEKI)]

    def selin(self, veri):
        return next(k for k in veri["kisiler"] if k["id"] == ag_demo.SELIN)


class SenaryoVerisiTest(DemoOrtami):
    def test_baslangic_durumu_selin_sogumus(self):
        ag_demo.baslat()
        veri, meta, anahtar = ag_demo.sayfa_verisi()
        ids = {k["id"] for k in veri["kisiler"]}
        self.assertEqual(ag_demo.SELIN, "selin-hoca")
        self.assertTrue({"selin-hoca", "baran-sanalioglu", "hande-efsane", "tuna-kurguner"} <= ids)
        self.assertEqual(veri["ben"]["ad"], "Deniz Demo")
        selin = self.selin(veri)
        self.assertEqual(selin["yakinlik"], 1)
        self.assertLess(selin["puan"]["sicaklik"], 30)   # soğumuş: gri-mavi bölge
        self.assertEqual((date.today() - date.fromisoformat(selin["son_temas"])).days, 150)   # ~5 ay
        self.assertEqual([k["ad"] for k in veri["kisiler"][1:] if k["yakinlik"] >= 1 and (k["puan"]["sicaklik"] or 0) < 30], ["Selin Hoca"])
        self.assertTrue(any(b["id"] == "selin-hoca" and "150 gündür" in b["neden"] for b in veri["bu_hafta"]))
        # bağlar: Selin Hoca → Baran'ın hocası, Hande ile tanışık, Deniz'in eski danışmanı (mentor)
        bag = {(i["a"], i["b"], i["tip"]) for i in veri["iliskiler"]}
        self.assertIn(("selin-hoca", "baran-sanalioglu", "hocasi"), bag)
        self.assertIn(("selin-hoca", "hande-efsane", "tanisiyor"), bag)
        self.assertIn(("selin-hoca", "ben", "mentor"), bag)
        self.assertNotIn("anahtar", json.dumps(meta).lower().replace('"anahtar"', ""))   # meta sahne verisidir, anahtar taşımaz
        self.assertTrue(anahtar and anahtar != sunucu.ANAHTAR)

    def test_sahneler_ve_metinler(self):
        self.assertEqual(ag_demo.SAHNE_IDLERI, ["ag", "pusula", "sor", "soz", "isinma", "kilit"])
        for s in ag_demo.SAHNELER:
            self.assertTrue(s["baslik"] and s["metin"] and s["anlatim"], s["id"])
            self.assertLess(len(s["metin"]), 260)   # sıcak, kısa, abartısız
        sahne = {s["id"]: s for s in ag_demo.SAHNELER}
        self.assertIn("Halkalar yakınlığı, renkler sıcaklığı gösterir", sahne["ag"]["metin"])
        self.assertIn("Cuma kapanıyor", sahne["pusula"]["metin"])
        self.assertIn("Kut olmasaydı", sahne["isinma"]["metin"])
        self.assertIn("hiçbir şey dışarı çıkmaz", sahne["kilit"]["metin"])

    def test_pusula_selin_hamlesi(self):
        p = ag_demo.pusula_verisi()
        h = p["strateji"]["hamleler"][0]
        self.assertEqual(h["kim"], "selin-hoca")
        self.assertEqual(date.fromisoformat(h["son_tarih"]).weekday(), 4)   # Cuma
        self.assertTrue(h["kanit"])
        self.assertEqual(p["hedefler"][0]["durum"], "aktif")
        self.assertTrue(p["vekil"]["kapali"] and p["etkinlik"]["kapali"])   # keşif/dış kaynak kapalı

    def test_sor_hazir_cevaplar_ve_soz_yakalama(self):
        ag_demo.baslat()
        r = ag_demo.sor({"soru": ag_demo.SORU_CUMLESI})
        self.assertIn("Baran Sanalıoğlu", r["cevap"])
        self.assertIn("Hande Efsane", r["cevap"])
        self.assertNotIn("soz_onay", r)
        self.assertIn("hazır sorulara", ag_demo.sor({"soru": "rastgele bir şey"})["cevap"])
        r = ag_demo.sor({"soru": ag_demo.SOZ_CUMLESI})
        self.assertEqual([(o["kisi"], o["yon"]) for o in r["soz_onay"]], [("selin-hoca", "ben")])
        self.assertIn("söz olarak ekleyeyim mi", r["soz_onay"][0]["soru"])
        veri, _, _ = ag_demo.sayfa_verisi()   # yalnız öneri: onaylanmadan hiçbir şey yazılmadı
        self.assertEqual(self.selin(veri)["sozler"], [])
        with self.assertRaises(ValueError):
            ag_demo.sor({"soru": "  "})

    def test_soz_onayi_ve_isinma(self):
        ag_demo.baslat()
        eski = self.selin(ag_demo.sayfa_verisi()[0])["puan"]["sicaklik"]
        o = ag_demo.sor({"soru": ag_demo.SOZ_CUMLESI})["soz_onay"][0]
        r = ag_demo.soz_onayla({k: o[k] for k in ("kisi", "yon", "metin", "son")})
        s = self.selin(r["veri"])
        self.assertEqual([(x["durum"], x["yon"]) for x in s["sozler"]], [("acik", "ben")])
        ag_demo.soz_onayla({k: o[k] for k in ("kisi", "yon", "metin", "son")})   # çift tıklama zarar vermez
        with self.assertRaises(ValueError):
            ag_demo.soz_onayla({"kisi": "yok-boyle-biri", "yon": "ben", "metin": "x"})
        r = ag_demo.isinma()
        s = self.selin(r["veri"])
        self.assertGreater(s["puan"]["sicaklik"], 90)
        self.assertGreater(s["puan"]["sicaklik"], eski)
        self.assertEqual(s["yakinlik"], 2)   # halka merkeze yaklaşır
        self.assertEqual(s["son_temas"], date.today().isoformat())
        self.assertEqual([x["durum"] for x in s["sozler"]], ["tamam"])
        self.assertIn("Taslağı gönderdim", s["govde"])
        self.assertEqual([k["ad"] for k in r["veri"]["kisiler"][1:] if k["yakinlik"] >= 1 and (k["puan"]["sicaklik"] or 0) < 30], [])
        self.assertEqual(r["zaman"], ag_demo.ZAMAN_ETIKETI)

    def test_isinma_soz_onaylanmamissa_da_calisir(self):
        ag_demo.baslat()
        s = self.selin(ag_demo.isinma()["veri"])
        self.assertEqual([x["durum"] for x in s["sozler"]], ["tamam"])

    def test_sayfa_her_acilista_senaryoyu_sifirlar(self):
        ag_demo.baslat()
        ag_demo.isinma()
        veri, _, _ = ag_demo.sayfa_verisi()
        self.assertLess(self.selin(veri)["puan"]["sicaklik"], 30)

    def test_genel_demo_senaryosu_bozulmadi(self):
        """demo_veri.py: genel mod eskisi gibi, --senaryo sali aynı senaryoyu gerçek modülle yazar."""
        ortam = {**os.environ, "AGIM_VERI": os.path.join(self.t.name, "d0"), "LOCALAPPDATA": os.path.join(self.t.name, "d1"), "PYTHONIOENCODING": "utf-8"}
        for ek, beklenen in (([], "selin-uydurmaz.md"), (["--senaryo", "sali"], "selin-hoca.md")):
            hedef = os.path.join(self.t.name, "cikti" + str(len(ek)))
            r = subprocess.run([sys.executable, "-W", "ignore", os.path.join(DEPO, "demo", "demo_veri.py"), "--hedef", hedef] + ek,
                               env=ortam, capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-300:])
            self.assertIn(beklenen, os.listdir(os.path.join(hedef, "kisiler")))


class YalitimTest(DemoOrtami):
    def demo_yuru(self):
        ag_demo.baslat()
        self.assertTrue(self.demo_dizinleri())
        ag_demo.sayfa_verisi()
        o = ag_demo.sor({"soru": ag_demo.SOZ_CUMLESI})["soz_onay"][0]
        ag_demo.soz_onayla({k: o[k] for k in ("kisi", "yon", "metin", "son")})
        ag_demo.isinma()

    def test_gercek_veri_ve_ayar_klasorune_yazma_yok(self):
        yol0, depo0 = c.VERI, ia.DEPO
        with mock.patch.object(c, "veri_klasoru", side_effect=AssertionError("gerçek modülün yolu demoda değiştirilemez")), \
                mock.patch.object(c, "kisi_yaz", side_effect=AssertionError("gerçek modül yazamaz")), \
                mock.patch.object(ia, "ayar_yaz", side_effect=AssertionError("ayar yazılamaz")):
            self.demo_yuru()
            ag_demo.kapat()
        self.assertEqual(c.VERI, yol0)
        self.assertEqual(ia.DEPO, depo0)
        self.assertEqual(goruntu(self.veri), self.gercek_once)
        self.assertEqual(goruntu(self.depo), self.ayar_once)
        self.assertEqual([k["id"] for k in c.kisileri_oku()], ["ada-gercek"])   # demo kişileri gerçek veriye karışmadı

    def test_kapaninca_gecici_veri_silinir(self):
        ag_demo.baslat()
        (dizin,) = self.demo_dizinleri()
        yol = os.path.join(self.tmp, dizin)
        self.assertTrue(os.path.isfile(os.path.join(yol, "kisiler", "selin-hoca.md")))
        self.assertTrue(ag_demo.aktif() and ag_demo.anahtar())
        ag_demo.kapat()
        self.assertFalse(os.path.exists(yol))
        self.assertFalse(ag_demo.aktif())
        self.assertIsNone(ag_demo.anahtar())
        with self.assertRaises(ValueError):
            ag_demo.isinma()           # kapalı demoya yazılamaz
        ag_demo.kapat()                # ikinci kapat zararsız

    def test_yeni_baslat_oncekini_siler_ve_anahtar_yenilenir(self):
        ag_demo.baslat()
        a1, (d1,) = ag_demo.anahtar(), self.demo_dizinleri()
        ag_demo.baslat()
        self.assertNotEqual(a1, ag_demo.anahtar())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, d1)))
        self.assertEqual(len(self.demo_dizinleri()), 1)

    def test_omur_dolunca_kendiliginden_kapanir(self):
        ag_demo.baslat()
        (dizin,) = self.demo_dizinleri()
        ag_demo._durum["t"] -= ag_demo.OMUR_SN + 5
        self.assertIsNone(ag_demo.anahtar())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, dizin)))

    def test_artik_temizligi_yalniz_isaretli_eski_klasorleri_siler(self):
        eski = time.time() - ag_demo.ESKI_SN - 60
        isaretli, isaretsiz, taze = (os.path.join(self.tmp, ag_demo.DIZIN_ONEKI + x) for x in ("a", "b", "c"))
        for d in (isaretli, isaretsiz, taze):
            os.makedirs(d)
        for d in (isaretli, isaretsiz):
            os.utime(d, (eski, eski))
        for d in (isaretli, taze):
            open(os.path.join(d, ag_demo.ISARET), "w").close()
        os.utime(isaretli, (eski, eski))
        ag_demo.baslat()
        self.assertFalse(os.path.exists(isaretli))     # işaretli + eski: çökmüş sürecin artığı
        self.assertTrue(os.path.exists(isaretsiz))     # işaretsiz: bize ait değil
        self.assertTrue(os.path.exists(taze))          # başka canlı demo olabilir

    def test_kapsul_gercek_modullerden_ayri(self):
        k = ag_demo.kapsul()
        self.assertIsNot(k.c, c)
        self.assertIsNot(k.soz, sys.modules["ag_soz"])
        self.assertIs(k.soz.c, k.c)                    # kapsüldeki söz modülü kapsüldeki çekirdeği kullanır
        ag_demo.baslat()
        self.assertTrue(k.c.VERI.startswith(self.tmp))
        self.assertEqual(c.VERI, self.veri)

    def test_modul_ag_ve_model_icermez(self):
        with open(os.path.join(KOK, "ag_demo.py"), encoding="utf-8") as f:
            kaynak = f.read()
        ice = set(re.findall(r"^\s*(?:import|from)\s+([\w.]+)", kaynak, re.M))
        for yasak in ("ag_model", "ag_kaynak", "ag_guncelle", "ag_kesif", "ag_strateji", "ag_ses", "ag_ses_kur", "ag_analiz", "ag_takvim",
                      "ag_linkedin", "ag_okullar", "ag_akademik", "ag_vault", "ag_kasa_kisi", "ag_ice_aktar", "ag_hedef", "urllib", "http", "socket",
                      "subprocess", "ssl", "requests", "webbrowser", "ftplib", "smtplib"):
            self.assertNotIn(yasak, {i.split(".")[0] for i in ice}, yasak)

    def test_demo_calisirken_model_ve_ag_cagrilmaz(self):
        def yasak(ad):
            return mock.Mock(side_effect=AssertionError(ad + " demoda çağrılamaz"))
        with mock.patch.object(mdl, "cagir", yasak("model")), mock.patch.object(kn, "_istek", yasak("kaynak isteği")), \
                mock.patch("socket.socket.connect", yasak("soket")), mock.patch("socket.create_connection", yasak("bağlantı")), \
                mock.patch("socket.getaddrinfo", yasak("DNS")), mock.patch("urllib.request.urlopen", yasak("urlopen")), \
                mock.patch("subprocess.Popen", yasak("süreç")):
            self.demo_yuru()
            for yol, g in (("/api/demo/sor", {"soru": ag_demo.SORU_CUMLESI}), ("/api/demo/sor", {"soru": ag_demo.SOZ_CUMLESI}), ("/api/demo/isinma", {})):
                sunucu.ISLEMLER[yol](g)
            sunucu.ISLEMLER["/api/demo/kapat"]({})

    def test_ses_dosyasi_yoksa_demo_sessiz_calisir(self):
        with tempfile.TemporaryDirectory() as bos, mock.patch.object(ag_demo, "KOK", bos):
            self.assertTrue(all(ag_demo.ses_dosyasi(s) is None for s in ag_demo.SAHNE_IDLERI))
            ag_demo.baslat()
            veri, meta, _ = ag_demo.sayfa_verisi()
            self.assertEqual([s["ses"] for s in meta["sahneler"]], [False] * 6)
            self.assertLess(self.selin(veri)["puan"]["sicaklik"], 30)   # demo yine tam çalışır
            ag_demo.isinma()
        with tempfile.TemporaryDirectory() as var, mock.patch.object(ag_demo, "KOK", var):
            os.makedirs(os.path.join(var, "demo_ses"))
            for ad in ("ag.wav", "soz.ogg", "gecersiz.wav"):
                open(os.path.join(var, "demo_ses", ad), "wb").write(b"RIFF")
            self.assertTrue(ag_demo.ses_dosyasi("ag").endswith("ag.wav"))
            self.assertTrue(ag_demo.ses_dosyasi("soz").endswith("soz.ogg"))
            self.assertEqual(ag_demo.ses_tipi(ag_demo.ses_dosyasi("soz")), "audio/ogg")
            self.assertIsNone(ag_demo.ses_dosyasi("gecersiz"))         # beyaz liste dışı kimlik
            self.assertIsNone(ag_demo.ses_dosyasi("../ag"))
            ag_demo.baslat()
            self.assertEqual([s["ses"] for s in ag_demo.sayfa_verisi()[1]["sahneler"]], [True, False, False, True, False, False])


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def mini_wav(yol):
    with wave.open(yol, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 240)


class SunucuKapilariTest(unittest.TestCase):
    """Ayrı süreçte sunucu: kilit (401), anahtar ve Origin kapıları (403), anahtar ayrımı, yalıtım ve silme uçtan uca."""
    PIN = "4321"

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.TemporaryDirectory()
        la, cls.tmp, cls.kut = (os.path.join(cls.d.name, x) for x in ("la", "tmp", "kut"))
        os.makedirs(cls.tmp)
        os.makedirs(os.path.join(cls.kut, "demo_ses"))
        mini_wav(os.path.join(cls.kut, "demo_ses", "ag.wav"))
        cls.veri = os.path.join(cls.d.name, "veri")
        cls.ayar, cls.log = os.path.join(la, "agim", "ayarlar.json"), os.path.join(la, "agim", "sunucu.log")
        cls.port = bos_port()
        env = {**os.environ, "LOCALAPPDATA": la, "AGIM_VERI": cls.veri, "TMP": cls.tmp, "TEMP": cls.tmp, "TMPDIR": cls.tmp, "PYTHONIOENCODING": "utf-8"}
        kod = ("import sys;sys.path.insert(0,%r);import ag_sunucu as s;from http.server import ThreadingHTTPServer;s.PORT=%d;s.ag_demo.KOK=%r;"
               "ThreadingHTTPServer(('127.0.0.1',%d),s.Isleyici).serve_forever()") % (KOK, cls.port, cls.kut, cls.port)
        cls.p = subprocess.Popen([sys.executable, "-W", "ignore", "-c", kod], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        kod, cerez, *_ = cls().istek("POST", "/api/kilit/kur", {"pin": cls.PIN, "pin2": cls.PIN})
        assert kod == 200, kod
        cls.gercek = re.search(r'"anahtar":\s*"([^"]+)"', cls().istek("GET", "/", None, {"Cookie": cerez.split(";")[0]})[2].decode("utf-8")).group(1)

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()
        cls.p.wait()
        cls.d.cleanup()

    def runTest(self):   # setUpClass içinde istek yardımcısı için
        pass

    def istek(self, yontem, yol, govde=None, basliklar=None):
        h = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h.request(yontem, yol, json.dumps(govde).encode() if govde is not None else None, {"Content-Type": "application/json", **(basliklar or {})})
        y = h.getresponse()
        r = (y.status, y.getheader("Set-Cookie"), y.read(), y.getheader("Location"), y.getheader("Content-Type"))
        h.close()
        return r

    def giris(self):
        kod, cerez, _, _, _ = self.istek("POST", "/api/kilit/ac", {"pin": self.PIN})
        self.assertEqual(kod, 200)
        return {"Cookie": cerez.split(";")[0]}

    def origin(self):
        return {"Origin": f"http://127.0.0.1:{self.port}"}

    def demo_ac(self):
        """Gerçek anahtarla demo başlatır; (çerez, demo anahtarı) döndürür."""
        cerez = self.giris()
        kod, _, v, _, _ = self.istek("POST", "/api/demo/baslat", {}, {**cerez, "X-Ag-Anahtar": self.gercek, **self.origin()})
        self.assertEqual(kod, 200, v)
        self.assertEqual(json.loads(v)["adres"], "/demo")
        sayfa = self.istek("GET", "/demo", None, cerez)
        self.assertEqual(sayfa[0], 200)
        return cerez, re.search(r'"anahtar":\s*"([^"]+)"', sayfa[2].decode("utf-8")).group(1), sayfa[2].decode("utf-8")

    def demo_kapat(self, cerez, demo):
        return self.istek("POST", "/api/demo/kapat", {}, {**cerez, "X-Ag-Anahtar": demo, **self.origin()})[0]

    def demo_dizinleri(self):
        return [d for d in os.listdir(self.tmp) if d.startswith(ag_demo.DIZIN_ONEKI)]

    def tearDown(self):
        # test ortasında kalan demo sonraki testi bozmasın: kilit kapanınca demo da silinir
        cerez = self.giris()
        self.istek("POST", "/api/kilit/kapat", {}, {**cerez, "X-Ag-Anahtar": self.gercek})

    def test_baslat_kapilari(self):
        yol, govde = "/api/demo/baslat", {}
        cerez = self.giris()
        self.assertEqual(self.istek("POST", yol, govde)[0], 403)                                              # anahtarsız
        self.assertEqual(self.istek("POST", yol, govde, {**cerez, "X-Ag-Anahtar": "yanlis"})[0], 403)           # yanlış anahtar
        self.assertEqual(self.istek("POST", yol, govde, {**cerez, "X-Ag-Anahtar": self.gercek, "Origin": "http://evil.example"})[0], 403)   # yabancı kaynak
        self.assertEqual(self.demo_dizinleri(), [])                                                              # reddedilen istek hiçbir şey üretmedi
        self.assertEqual(self.istek("GET", yol, None, {**cerez, "X-Ag-Anahtar": self.gercek})[0], 404)          # yalnız POST
        self.assertEqual(self.istek("POST", yol, govde, {"X-Ag-Anahtar": self.gercek, **self.origin()})[0], 401)   # oturum yok: kilitli
        self.assertEqual(self.demo_dizinleri(), [])
        cerez, demo, _ = self.demo_ac()
        self.assertEqual(len(self.demo_dizinleri()), 1)
        # demo anahtarı baslat'ı açamaz (yalnız gerçek anahtar), gerçek anahtar demo uçlarını açamaz
        self.assertEqual(self.istek("POST", yol, govde, {**cerez, "X-Ag-Anahtar": demo, **self.origin()})[0], 403)
        for u in ("/api/demo/sor", "/api/demo/soz", "/api/demo/isinma", "/api/demo/kapat"):
            self.assertEqual(self.istek("POST", u, {}, {**cerez, "X-Ag-Anahtar": self.gercek, **self.origin()})[0], 403, u)
        self.assertEqual(self.demo_kapat(cerez, demo), 200)

    def test_demo_uclari_kilit_anahtar_origin(self):
        cerez, demo, _ = self.demo_ac()
        a = {**cerez, "X-Ag-Anahtar": demo, **self.origin()}
        for u in ("/api/demo/sor", "/api/demo/soz", "/api/demo/isinma"):
            self.assertEqual(self.istek("POST", u, {}, cerez)[0], 403, u)                                       # anahtarsız
            self.assertEqual(self.istek("POST", u, {}, {**cerez, "X-Ag-Anahtar": "x", **self.origin()})[0], 403, u)
            self.assertEqual(self.istek("POST", u, {}, {**a, "Origin": "http://evil.example"})[0], 403, u)       # yabancı kaynak
            self.assertEqual(self.istek("POST", u, {}, {"X-Ag-Anahtar": demo, **self.origin()})[0], 401, u)     # çerez yok: kilitli
        self.assertEqual(self.istek("POST", "/api/demo/sor", {"soru": ""}, a)[0], 400)
        kod, _, v, _, _ = self.istek("POST", "/api/demo/sor", {"soru": ag_demo.SORU_CUMLESI}, a)
        self.assertEqual(kod, 200)
        self.assertIn("Baran Sanalıoğlu", json.loads(v)["cevap"])
        self.assertEqual(self.istek("GET", "/api/demo/durum", None, {**cerez, "X-Ag-Anahtar": demo})[0], 200)
        self.assertEqual(self.istek("GET", "/api/demo/durum", None, {**cerez, "X-Ag-Anahtar": self.gercek})[0], 403)
        self.demo_kapat(cerez, demo)

    def test_kilitliyken_401(self):
        cerez, demo, _ = self.demo_ac()
        self.istek("POST", "/api/kilit/kapat", {}, {**cerez, "X-Ag-Anahtar": self.gercek})   # kilitle (demo da silinir)
        self.assertEqual(self.demo_dizinleri(), [])
        self.assertEqual(self.istek("POST", "/api/demo/baslat", {}, {**cerez, "X-Ag-Anahtar": self.gercek, **self.origin()})[0], 401)
        self.assertEqual(self.istek("GET", "/api/demo/ses?s=ag", None, cerez)[0], 401)
        self.assertEqual(self.istek("GET", "/api/demo/durum", None, {**cerez, "X-Ag-Anahtar": demo})[0], 401)   # kilitli: önce kilit
        k = self.istek("GET", "/demo", None, cerez)
        self.assertEqual((k[0], k[3]), (302, "/"))                                  # kilitliyken demo sayfası kilit ekranına döner
        self.assertNotIn(b"Selin Hoca", self.istek("GET", "/", None, cerez)[2])     # kilit ekranı kişisel/demo veri taşımaz

    def test_demo_sayfasi_gercek_anahtari_tasimaz(self):
        cerez, demo, sayfa = self.demo_ac()
        self.assertNotEqual(demo, self.gercek)
        self.assertNotIn(self.gercek, sayfa)                                         # gerçek oturum anahtarı demo sayfasında yok
        self.assertIn("Selin Hoca", sayfa)
        self.assertRegex(sayfa, r'"demo":\s*\{')
        # demo anahtarı gerçek uçlarda geçmez
        for yol, g in (("/api/temas", {"id": "x", "metin": "y"}), ("/api/ben", {"ad": "Z"}), ("/api/sor", {"soru": "a", "kisi": "", "oturum": ""}),
                       ("/api/kaynaklar", {"id": "etkinlik", "acik": True}), ("/api/guncelleme/denetle", {}), ("/api/saglayici", {"saglayici": "ollama"})):
            self.assertEqual(self.istek("POST", yol, g, {**cerez, "X-Ag-Anahtar": demo, **self.origin()})[0], 403, yol)
        for yol in ("/api/pusula", "/api/kaynaklar", "/api/guncelleme", "/api/saglayici"):
            self.assertEqual(self.istek("GET", yol, None, {**cerez, "X-Ag-Anahtar": demo})[0], 403, yol)
        self.demo_kapat(cerez, demo)
        self.assertEqual(self.istek("GET", "/demo", None, cerez)[0], 302)            # kapanınca demo sayfası yok

    def test_uctan_uca_yalitim_ve_silme(self):
        ayar0 = open(self.ayar, "rb").read()
        log0 = open(self.log, "rb").read()
        cerez, demo, _ = self.demo_ac()
        a = {**cerez, "X-Ag-Anahtar": demo, **self.origin()}
        oner = json.loads(self.istek("POST", "/api/demo/sor", {"soru": ag_demo.SOZ_CUMLESI}, a)[2])["soz_onay"][0]
        kod, _, v, _, _ = self.istek("POST", "/api/demo/soz", {k: oner[k] for k in ("kisi", "yon", "metin", "son")}, a)
        self.assertEqual(kod, 200)
        self.assertEqual(self.istek("POST", "/api/demo/soz", {"kisi": "yok", "yon": "ben", "metin": "x"}, a)[0], 400)
        kod, _, v, _, _ = self.istek("POST", "/api/demo/isinma", {}, a)
        self.assertEqual(kod, 200)
        selin = next(k for k in json.loads(v)["veri"]["kisiler"] if k["id"] == "selin-hoca")
        self.assertGreater(selin["puan"]["sicaklik"], 90)
        self.assertEqual(len(self.demo_dizinleri()), 1)
        # gerçek ayar klasörü ve günlüğü, gerçek veri klasörü: demo yazmadı
        self.assertEqual(open(self.ayar, "rb").read(), ayar0)
        self.assertEqual(open(self.log, "rb").read(), log0)
        self.assertNotIn(b"/api/demo", open(self.log, "rb").read())
        self.assertEqual(os.listdir(os.path.join(self.veri, "kisiler")) if os.path.isdir(os.path.join(self.veri, "kisiler")) else [], [])
        self.assertFalse(os.path.exists(os.path.join(self.veri, "ag.html")))
        self.assertEqual(self.demo_kapat(cerez, demo), 200)
        self.assertEqual(self.demo_dizinleri(), [])                                   # kapanınca geçici veri silindi

    def test_kilit_kapaninca_demo_silinir(self):
        cerez, demo, _ = self.demo_ac()
        self.assertEqual(len(self.demo_dizinleri()), 1)
        self.assertEqual(self.istek("POST", "/api/kilit/kapat", {}, {**cerez, "X-Ag-Anahtar": self.gercek})[0], 200)
        self.assertEqual(self.demo_dizinleri(), [])

    def test_anlatim_sesi_varsa_calar_yoksa_404(self):
        cerez, demo, sayfa = self.demo_ac()
        ses = json.loads(re.search(r'"sahneler":\s*(\[.*?\]),\s*"pusula"', sayfa, re.S).group(1))
        self.assertEqual({s["id"]: s["ses"] for s in ses}, {"ag": True, "pusula": False, "sor": False, "soz": False, "isinma": False, "kilit": False})
        kod, _, v, _, tip = self.istek("GET", "/api/demo/ses?s=ag", None, cerez)
        self.assertEqual((kod, tip), (200, "audio/wav"))
        self.assertEqual(v[:4], b"RIFF")
        self.assertEqual(self.istek("GET", "/api/demo/ses?s=pusula", None, cerez)[0], 404)       # dosya yok: sessiz
        self.assertEqual(self.istek("GET", "/api/demo/ses?s=../ag", None, cerez)[0], 404)
        self.assertEqual(self.istek("GET", "/api/demo/ses", None, cerez)[0], 404)
        self.demo_kapat(cerez, demo)
        self.assertEqual(self.istek("GET", "/api/demo/ses?s=ag", None, cerez)[0], 404)           # demo kapalıyken de yok


class ArayuzTest(unittest.TestCase):
    def bolum(self):
        h = sablon()
        bas = h.index("// ---- Demo önizlemesi (\"Deniz'in salısı\") ----")
        return h[bas:h.index("ortala(); filtrele(); isit(1);", bas)]

    def test_api_demoda_gercek_uclara_gitmez(self):
        h = sablon()
        api = h[h.index("async function api(yol, govde) {"):]
        api = api[:api.index("\n}\n")]
        self.assertLess(api.index("if (DEMO) return demoApi(yol, govde);"), api.index("fetch("))   # fetch'ten önce yönlenir
        b = self.bolum()
        izinli = re.findall(r'y === "(/api/[^"]+)"', b)
        self.assertEqual(sorted(izinli), ["/api/arayuz/ses", "/api/pusula", "/api/sor", "/api/soz/onayla"])
        self.assertIn('throw new Error("Bu işlem örnekte kapalı', b)
        # demo bölümündeki ham fetch'ler yalnız demo uçlarına gider
        for m in re.finditer(r'fetch\(([^,)]+)', b):
            self.assertRegex(m.group(1), r'yol|"/api/demo/durum"')
        for m in re.finditer(r'"(/api/[a-z/-]+)"', b):
            self.assertTrue(m.group(1) in izinli or m.group(1).startswith("/api/demo/"), m.group(1))

    def test_demo_metinleri_esc_veya_textcontent_ile_basilir(self):
        b = self.bolum()
        # sahne metni/başlığı/soru/cevap hiçbir innerHTML'e girmez; kart textContent ile dolar
        for satir in b.splitlines():
            if "innerHTML" in satir:
                self.assertNotRegex(satir, r"DEMO\.|\.metin|\.baslik|sahneler|\$\{(?!\})", satir)
        h = sablon()
        self.assertIn('$("tur-metin").textContent = typeof a.metin', h)
        self.assertIn('$("tur-baslik").textContent = a.baslik', h)
        self.assertIn("e.textContent = m;", b)                       # zaman etiketi
        self.assertIn("${esc(", h[h.index("function sihKartHtml()"):h.index("function arayuzSesHtml()")] + "${esc(")   # kart kullanıcı verisi basmaz
        # kullanıcı/demo adı bulunan kısa basımlar esc'li: bildir ve textContent
        self.assertIn('bildir("Temas kaydedildi: " + k.ad', b)       # bildir() textContent kullanır

    def test_sayfa_betik_kapatamaz(self):
        meta = {"sahneler": [{"id": "ag", "baslik": "</script><script>alert(1)</script>", "metin": "<img src=x onerror=alert(1)><!--", "ses": False}],
                "pusula": {}, "zaman": "x", "selin": "selin-hoca", "soz": "s", "soru": "q", "ornekler": []}
        html = c.sayfa({"turler": {}, "tipler": {}, "kisiler": [], "iliskiler": [], "ben": {}}, {"anahtar": "k", "demo": meta}, {"acik": True})
        self.assertEqual(html.count("</script>"), sablon().count("</script>"))
        self.assertNotIn("<!--alert", html.replace("<\\!--", ""))

    def test_giris_noktalari_ve_cikis(self):
        h = sablon()
        self.assertIn('id="sih-demo">Önce bir örnekle göster', h)                              # sihirbaz hoş geldin
        self.assertIn('id="ay-demo">Önce bir örnekle göster', h)                                # Ayarlar → Kurulum ve tanıtım
        self.assertIn('on("#ay-demo", () => demoBaslat())', h)
        self.assertIn('$("sih-demo").onclick = demoBaslat;', h)
        b = self.bolum()
        self.assertIn('api("/api/demo/baslat", {})', b)
        self.assertIn('location.href = "/demo"', b)
        for parca in ("Kendi ağımı kur", "Demoyu kapat", "kut-demo-sihirbaz", "Anlatımı sustur", "Baştan oynat"):
            self.assertIn(parca, b)
        self.assertIn('sessionStorage.getItem("kut-demo-sihirbaz")', h)                          # gerçek sayfa: sihirbaza dön

    def test_sahne_isigi_motoru_yeniden_kullanilir_ve_azaltilmis_hareket(self):
        b = self.bolum()
        self.assertEqual(re.findall(r'\{ id: "(\w+)", hedef:', b), ["ag", "pusula", "sor", "soz", "isinma", "kilit"])
        for k in ("TUR.adimlar = demoAdimlari()", "turGit(0, 1)", "document.addEventListener(\"keydown\", turTus, true)"):
            self.assertIn(k, b)
        self.assertIn("azHareket", b[b.index("function demoIsit"):b.index("async function demoIsinma")])   # renk geçişi anında
        self.assertIn('arayuzSes("tamam")', b)                                                   # doruk akoru ayara uyar
        self.assertIn("prefers-reduced-motion:reduce", sablon()[sablon().index("/* ---- Demo önizlemesi"):])
        h = sablon()
        self.assertIn("if (DEMO) demoPerde(r);", h)
        self.assertIn("try { const v = TUR.adimlar[i].varis; if (v) v(yon); } catch {}", h)

    def test_demo_gercek_oturum_ve_sohbet_gecmisine_dokunmaz(self):
        h = sablon()
        self.assertIn("if (!DEMO) Object.assign(SH, JSON.parse(sessionStorage.getItem(\"kut-sohbet\")", h)
        self.assertIn("const shKaydet = () => { if (DEMO) return;", h)
        self.assertIn("if (KILIT && KILIT.acik && MOD && !DEMO) {", h)                           # pagehide beacon / boşta kilit: demoda yok
        self.assertIn("!DEMO && !sessionStorage.getItem(\"kut-kilit-acik\")", h)
        self.assertNotIn("sendBeacon", self.bolum())

    def test_yeni_renk_yok(self):
        css = sablon()[sablon().index("/* ---- Demo önizlemesi"):]
        css = css[:css.index("</style>") if "</style>" in css else None]
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", css), [])                            # renkler yalnız değişkenlerden/rgba(242,193,78) sarıdan
        self.assertEqual(set(re.findall(r"rgba?\(([\d,.\s]+)\)", css)), {"242,193,78,.55", "242,193,78,.25", "242,193,78,.95"})


class SesBetigiTest(unittest.TestCase):
    def kaynak(self):
        with open(BETIK, encoding="utf-8") as f:
            return f.read()

    def test_anahtar_yalniz_ortamdan_okunur_ve_sizmaz(self):
        k = self.kaynak()
        self.assertEqual(re.findall(r"os\.environ\.get\(\"([A-Z_]+)\"", k), ["GEMINI_API_KEY"])
        self.assertEqual(len(re.findall(r"environ|getenv", k)), 1)                             # başka ortam okuması yok
        self.assertNotRegex(k, r"add_argument\(\"--(anahtar|key|api)")                          # komut satırı bayrağı değil
        self.assertNotRegex(k, r"\?key=|&key=")                                                 # adrese eklenmez
        self.assertIn('"x-goog-api-key": anahtar', k)                                           # başlıkta gider
        self.assertNotRegex(k, r"print\([^)]*anahtar\b(?!\s*=)")                                # yazdırılmaz
        for yasak in ("open(", "logging", "getpass"):
            if yasak == "open(":
                self.assertEqual(len(re.findall(r"(?<![.\w])open\(", k)), 0)                    # dosya yazımı yalnız wave ile (anahtar dosyaya yazılamaz)
            else:
                self.assertNotIn(yasak, k)
        self.assertNotIn("json.dump(", k)

    def test_kuru_calisma_metin_listesi_ag_ve_anahtar_yok(self):
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        env.update(PYTHONIOENCODING="utf-8", AGIM_VERI=tempfile.mkdtemp(), LOCALAPPDATA=tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-W", "ignore", BETIK, "--kuru"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        for s in ag_demo.SAHNELER:
            self.assertIn(f"[{s['id']}] {s['anlatim']}", r.stdout)
        self.assertIn("Sakin, sıcak, samimi", r.stdout)
        # anahtar varken de kuru çalışma onu yazmaz ve dosya üretmez
        env["GEMINI_API_KEY"] = "SENTINEL-DEMO-ANAHTARI-123"
        with tempfile.TemporaryDirectory() as cikti:
            r2 = subprocess.run([sys.executable, "-W", "ignore", BETIK, "--kuru", "--cikti", cikti], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(r2.returncode, 0)
            self.assertNotIn("SENTINEL", r2.stdout + r2.stderr)
            self.assertEqual(os.listdir(cikti), [])
        r3 = subprocess.run([sys.executable, "-W", "ignore", BETIK, "--sahne", "yok"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertNotEqual(r3.returncode, 0)

    def test_anahtarsiz_gercek_calisma_ag_denemez(self):
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        env.update(PYTHONIOENCODING="utf-8", AGIM_VERI=tempfile.mkdtemp(), LOCALAPPDATA=tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-W", "ignore", BETIK], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("GEMINI_API_KEY", r.stdout + r.stderr)

    def test_istek_biciminde_anahtar_govdede_degil(self):
        sys.path.insert(0, os.path.join(DEPO, "paketleme"))
        import demo_seslendir as ds
        g = ds.istek_govdesi("Merhaba", "Sulafat")
        self.assertEqual(g["generationConfig"]["responseModalities"], ["AUDIO"])
        self.assertEqual(g["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"], "Sulafat")
        self.assertIn("Sakin, sıcak, samimi", g["contents"][0]["parts"][0]["text"])
        self.assertNotIn("key", json.dumps(g).lower().replace("responsemodalities", ""))
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "x.wav")
            ds.wav_yaz(yol, b"\x01\x00" * 100)
            with wave.open(yol) as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()), (1, 2, 24000, 100))


class DenetimDuzeltmeTest(DemoOrtami):
    """Yayın öncesi denetim: temizlikte bağ/junction güvenliği, donmuş .exe için kapsül yedeği."""

    def eski_isaretli(self, yol):
        os.makedirs(yol)
        with open(os.path.join(yol, ag_demo.ISARET), "w", encoding="utf-8") as f:
            f.write("x")
        with open(os.path.join(yol, "kalmali.txt"), "w", encoding="utf-8") as f:
            f.write("başka klasörün dosyası")
        eski = time.time() - ag_demo.ESKI_SN - 600
        os.utime(yol, (eski, eski))

    def test_artik_temizlik_gercek_eski_klasoru_siler(self):
        yol = os.path.join(self.tmp, ag_demo.DIZIN_ONEKI + "eski")
        self.eski_isaretli(yol)
        ag_demo._artik_temizle()
        self.assertFalse(os.path.exists(yol))

    def test_artik_temizlik_junction_ya_da_baglanti_izlemez(self):
        hedef = os.path.join(self.t.name, "baska-klasor")
        self.eski_isaretli(hedef)
        bag = os.path.join(self.tmp, ag_demo.DIZIN_ONEKI + "bag")
        if os.name == "nt":
            p = subprocess.run(["cmd", "/c", "mklink", "/J", bag, hedef], capture_output=True)
            if p.returncode != 0:
                self.skipTest("junction oluşturulamadı")
        else:
            try:
                os.symlink(hedef, bag, target_is_directory=True)
            except OSError:
                self.skipTest("sembolik bağ oluşturulamadı")
        self.assertFalse(ag_demo._gercek_klasor(bag))
        ag_demo._artik_temizle()
        self.assertTrue(os.path.isfile(os.path.join(hedef, "kalmali.txt")), "bağın gösterdiği klasör silindi")
        self.assertTrue(os.path.isfile(os.path.join(hedef, ag_demo.ISARET)))
        if os.name == "nt":
            os.rmdir(bag)   # junction'ı hedefe dokunmadan kaldır
        else:
            os.unlink(bag)

    def test_kapat_isaretsiz_ya_da_baglanti_olan_klasoru_silmez(self):
        ag_demo.baslat()
        dizin = ag_demo.dizin()
        os.remove(os.path.join(dizin, ag_demo.ISARET))   # işaret yok: silme
        ag_demo.kapat()
        self.assertTrue(os.path.isdir(dizin))
        self.assertIsNone(ag_demo.anahtar())

    def test_kapsul_get_code_yoksa_kaynak_dosyadan_yuklenir(self):
        """Donmuş .exe'de yükleyici get_code vermese bile (ya da find_spec şaşsa) kapsül kaynak dosyadan kurulur; hiçbiri yoksa ValueError."""
        class Yukleyicisiz:
            pass

        class Spec:
            loader, origin = Yukleyicisiz(), None
        with mock.patch.object(ag_demo.importlib.util, "find_spec", return_value=Spec()):
            kod, yol = ag_demo._kod_al("ag_soz")
            self.assertTrue(yol.endswith("ag_soz.py") and os.path.isfile(yol))
            self.assertEqual(kod.co_filename, yol)
            ev = ag_demo.Kapsul()
            self.assertIsNot(ev.c, c)                       # gerçek modülün özel kopyası
            self.assertTrue(ev.c.DEMO_KAPSULU)
        with mock.patch.object(ag_demo.importlib.util, "find_spec", side_effect=ImportError("yok")), \
                mock.patch.object(ag_demo, "KOK", self.t.name), mock.patch.object(ag_demo.sys, "_MEIPASS", self.t.name, create=True):
            with self.assertRaisesRegex(ValueError, "kullanılamıyor"):
                ag_demo._kod_al("ag_cekirdek")

    def test_demo_kurulamazsa_gecici_klasor_birakilmaz(self):
        with mock.patch.object(ag_demo, "_kod_al", side_effect=ValueError("Örnek bu kurulumda kullanılamıyor")):
            ag_demo._kapsul = None
            try:
                with self.assertRaises(ValueError):
                    ag_demo.baslat()
            finally:
                ag_demo._kapsul = None
        self.assertEqual(self.demo_dizinleri(), [])
        self.assertIsNone(ag_demo.anahtar())

    def test_paketleme_tarifi_kapsul_kaynaklarini_pakete_koyar(self):
        with open(os.path.join(DEPO, "paketleme", "kut.spec"), encoding="utf-8") as f:
            spec = f.read()
        self.assertIn("'ag_cekirdek.py'", spec)
        self.assertIn("'ag_soz.py'", spec)


if __name__ == "__main__":
    unittest.main()
