"""Güncelleme sistemi: sürüm karşılaştırma, rıza ve haftalık sınır, sağlama toplamı/ana makine denetimi, git engelleri, göç, API kapısı.
Ağ ve alt süreçler taklit edilir; gerçek GitHub'a çıkılmaz."""
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
import urllib.error
import urllib.request
import zipfile
from unittest import mock

KOK_DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOK = os.path.join(KOK_DEPO, "kut")
sys.path.insert(0, KOK)
import ag_guncelle as gu  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_kaynak as kn  # noqa: E402
import goc  # noqa: E402
import surum as sv  # noqa: E402

EXE_BAYT = b"MZ" + b"kut-exe-icerik" * 50
EXE_SHA = hashlib.sha256(EXE_BAYT).hexdigest()
INDIR = "https://github.com/koraykutlu/kut/releases/download/v1.5.0/"


def yayin(surum="1.5.0", digest=EXE_SHA, sums=None, exe_url=None, exe=True):
    assets = []
    if exe:
        a = {"name": "Kut.exe", "size": len(EXE_BAYT), "browser_download_url": exe_url or INDIR + "Kut.exe"}
        if digest:
            a["digest"] = "sha256:" + digest
        assets.append(a)
    if sums:
        assets.append({"name": sums, "size": 100, "browser_download_url": INDIR + sums})
    return json.dumps({"tag_name": "v" + surum, "body": "Notlar " * 500, "html_url": f"https://github.com/koraykutlu/kut/releases/tag/v{surum}",
                       "published_at": "2026-10-20T10:00:00Z", "assets": assets}).encode()


class Temel(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.ayar = mock.patch.object(ia, "AYARLAR", os.path.join(self.d.name, "ayarlar.json"))
        self.ayar.start()
        self.agdan = mock.patch.object(gu, "_ag_oku", side_effect=AssertionError("ağa çıkılmamalıydı"))
        self.ag = self.agdan.start()

    def tearDown(self):
        mock.patch.stopall()
        self.d.cleanup()


class SurumTest(unittest.TestCase):
    def test_karsilastirma(self):
        self.assertEqual(sv.karsilastir("1.10.0", "1.9.9"), 1)
        self.assertEqual(sv.karsilastir("v1.0.0", "1.0.0"), 0)
        self.assertEqual(sv.karsilastir("0.9.12", "1.0.0"), -1)
        self.assertTrue(sv.yeni_mi("v1.0.1", "1.0.0"))
        self.assertFalse(sv.yeni_mi("1.0.0", "1.0.0"))
        for kotu in ("1.2", "1.2.3-beta", "abc", "", None, "1.2.3.4", "v1.x.0"):
            with self.assertRaises(ValueError, msg=kotu):
                sv.ayristir(kotu)

    def test_surum_sabiti(self):
        self.assertEqual(sv.SURUM, "1.4.0")
        sv.ayristir(sv.SURUM)


class RizaVeSinirTest(Temel):
    def test_sorulmadiysa_ag_yok(self):
        self.assertIsNone(gu.otomatik())
        self.assertTrue(gu.durum()["sorulmadi"])
        self.assertFalse(gu.otomatik_gerekli())
        self.assertIsNone(gu.otomatik_denetim())
        gu.denetle(elle=False)   # otomatik çağrı + rıza yok → sessiz, ağsız
        self.ag.assert_not_called()

    def test_hayir_ise_ag_yok(self):
        gu.otomatik_ayarla(False)
        self.assertFalse(gu.durum()["sorulmadi"])
        self.assertIsNone(gu.otomatik_denetim())
        gu.denetle(elle=False)
        self.ag.assert_not_called()
        self.assertIs(ia.ayarlar()["guncelleme"]["otomatik"], False)

    def test_haftalik_sinir(self):
        gu.otomatik_ayarla(True)
        t = [1_000_000.0]
        self.ag.side_effect = None
        self.ag.return_value = yayin("1.0.0")
        with mock.patch.object(gu, "_simdi", lambda: t[0]):
            gu.otomatik_denetim()
            self.assertEqual(self.ag.call_count, 1)
            t[0] += 86400
            gu.otomatik_denetim()
            t[0] += 5 * 86400
            gu.otomatik_denetim()
            self.assertEqual(self.ag.call_count, 1)   # 6 gün: hâlâ yok
            t[0] += 2 * 86400
            gu.otomatik_denetim()
            self.assertEqual(self.ag.call_count, 2)   # 8 gün

    def test_elle_denetim_riza_olmadan_calisir_ve_onbellege_yazar(self):
        self.ag.side_effect = None
        self.ag.return_value = yayin("1.5.0", sums="Kut.exe.sha256")
        d = gu.denetle(elle=True)
        self.assertEqual(self.ag.call_count, 1)
        self.assertTrue(d["yeni"])
        self.assertTrue(d["sorulmadi"])   # elle denetim rıza yerine geçmez
        self.assertEqual(d["son"]["surum"], "1.5.0")
        self.assertEqual(d["son"]["exe"]["sha256"], EXE_SHA)
        self.assertLessEqual(len(d["son"]["notlar"]), gu.NOT_AZAMI)
        self.assertEqual(self.ag.call_args[0][0], gu.API_URL)
        self.assertEqual(ia.ayarlar()["guncelleme"]["son"]["surum"], "1.5.0")   # önbellek ayar dosyasında

    def test_ayni_surum_yeni_degil_ve_bozuk_etiket_reddedilir(self):
        self.ag.side_effect = None
        self.ag.return_value = yayin("1.0.0")
        self.assertFalse(gu.denetle(elle=True)["yeni"])
        self.ag.return_value = json.dumps({"tag_name": "nightly", "assets": []}).encode()
        with self.assertRaises(ValueError):
            gu.denetle(elle=True)

    def test_ag_hatasi_okunur_iletiye_donusur(self):
        self.ag.side_effect = urllib.error.URLError("yok")
        with self.assertRaises(ValueError):
            gu.denetle(elle=True)
        self.ag.side_effect = urllib.error.HTTPError(gu.API_URL, 404, "x", {}, None)
        with self.assertRaisesRegex(ValueError, "Henüz"):
            gu.denetle(elle=True)


class AgGuvenligiTest(unittest.TestCase):
    def test_izin_listesi(self):
        gu._https_izinli("https://github.com/x", gu.INDIRME_HOSTLAR)
        gu._https_izinli("https://release-assets.githubusercontent.com/a", gu.INDIRME_HOSTLAR)
        for kotu in ("http://github.com/x", "https://evil.example/x", "https://github.com.evil.example/x", "https://127.0.0.1/x", "ftp://github.com/x"):
            with self.assertRaises(ValueError, msg=kotu):
                gu._https_izinli(kotu, gu.INDIRME_HOSTLAR)

    def test_yonlendirme_izin_listesi_disina_cikamaz(self):
        acici = gu._acici(gu.INDIRME_HOSTLAR)
        yon = next(h for h in acici.handlers if isinstance(h, kn.GuvenliYonlendirme))
        istek = urllib.request.Request(INDIR + "Kut.exe")
        with mock.patch.object(kn, "_guvenli_url", lambda u, k=None: u):
            with self.assertRaises(urllib.error.URLError):
                yon.redirect_request(istek, None, 302, "Found", {}, "https://evil.example/Kut.exe")
            with self.assertRaises(urllib.error.URLError):
                yon.redirect_request(istek, None, 302, "Found", {}, "http://objects.githubusercontent.com/Kut.exe")   # https olmalı
            yon.redirect_request(istek, None, 302, "Found", {}, "https://release-assets.githubusercontent.com/x")

    def test_ssrf_korumasi_atlanmaz(self):
        # izin listesindeki bir ana makine bile yerel adrese çözülürse _guvenli_url reddeder
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(OSError):
                gu._istek_ac("https://api.github.com/repos/x", gu.API_HOSTLAR, 3)


class ExeUygulamaTest(Temel):
    def setUp(self):
        super().setUp()
        self.k = os.path.join(self.d.name, "uygulama")
        os.makedirs(self.k)
        self.yollar = (os.path.join(self.k, "Kut.exe"), os.path.join(self.k, "Kut.new.exe"), os.path.join(self.k, "Kut.prev.exe"))
        open(self.yollar[0], "wb").write(b"eski")
        mock.patch.object(gu, "kurulum_turu", return_value="exe").start()
        mock.patch.object(gu, "_exe_yollari", return_value=self.yollar).start()
        self.degistir = mock.patch.object(gu, "_degistirici_baslat").start()
        self.kapat = mock.patch.object(gu, "_kapat_planla").start()
        self.indir_ozet = EXE_SHA
        self.indir = mock.patch.object(gu, "_indir", side_effect=self._indir).start()
        self.ag.side_effect = None

    def _indir(self, url, hedef, azami, *a, **k):
        open(hedef, "wb").write(EXE_BAYT)
        return len(EXE_BAYT), self.indir_ozet

    def test_basarili_guncelleme(self):
        self.ag.return_value = yayin("1.5.0")
        if os.name != "nt":
            self.skipTest("exe güncellemesi yalnız Windows")
        r = gu.uygula()
        self.assertTrue(r["yeniden"])
        self.degistir.assert_called_once_with(*[self.yollar[0], self.yollar[1], self.yollar[2]])
        self.kapat.assert_called_once()
        self.assertTrue(os.path.isfile(self.yollar[1]))
        self.assertEqual(ia.ayarlar()["guncelleme"]["onceki"]["surum"], "1.4.0")

    def test_sums_dosyasindan_dogrulama(self):
        if os.name != "nt":
            self.skipTest("exe güncellemesi yalnız Windows")
        self.ag.side_effect = [yayin("1.5.0", digest=None, sums="Kut.exe.sha256"), (EXE_SHA + "  Kut.exe\r\n").encode()]
        gu.uygula()
        self.degistir.assert_called_once()

    def test_sağlama_uyusmazligi_reddedilir(self):
        if os.name != "nt":
            self.skipTest("exe güncellemesi yalnız Windows")
        self.ag.return_value = yayin("1.5.0")
        self.indir_ozet = "0" * 64
        with self.assertRaisesRegex(ValueError, "uyuşmuyor"):
            gu.uygula()
        self.assertFalse(os.path.exists(self.yollar[1]))   # indirilen dosya silindi
        self.degistir.assert_not_called()
        self.kapat.assert_not_called()
        self.assertEqual(open(self.yollar[0], "rb").read(), b"eski")

    def test_sağlama_toplami_yoksa_reddedilir(self):
        if os.name != "nt":
            self.skipTest("exe güncellemesi yalnız Windows")
        self.ag.return_value = yayin("1.5.0", digest=None)
        with self.assertRaisesRegex(ValueError, "sağlama toplamı"):
            gu.uygula()
        self.indir.assert_not_called()   # indirmeden önce reddedildi
        self.degistir.assert_not_called()

    def test_sums_dosyasi_exe_icin_hash_icermiyorsa_reddedilir(self):
        if os.name != "nt":
            self.skipTest("exe güncellemesi yalnız Windows")
        self.ag.side_effect = [yayin("1.5.0", digest=None, sums="SHA256SUMS"), (EXE_SHA + "  baska.zip\n").encode()]
        with self.assertRaisesRegex(ValueError, "sağlama toplamı"):
            gu.uygula()
        self.indir.assert_not_called()

    def test_izinsiz_ana_makine_reddedilir(self):
        if os.name != "nt":
            self.skipTest("exe güncellemesi yalnız Windows")
        for kotu in ("https://evil.example/Kut.exe", "http://github.com/koraykutlu/kut/releases/download/v1.5.0/Kut.exe",
                     "https://github.com/baska/depo/releases/download/v1.5.0/Kut.exe", "https://127.0.0.1/Kut.exe"):
            self.ag.return_value = yayin("1.5.0", exe_url=kotu)
            with self.assertRaises(ValueError, msg=kotu):
                gu.uygula()
        self.indir.assert_not_called()
        self.degistir.assert_not_called()

    def test_exe_varligi_yoksa_reddedilir(self):
        if os.name != "nt":
            self.skipTest("exe güncellemesi yalnız Windows")
        self.ag.return_value = yayin("1.5.0", exe=False)
        with self.assertRaises(ValueError):
            gu.uygula()
        self.indir.assert_not_called()

    def test_guncel_ise_uygulanmaz(self):
        self.ag.return_value = yayin("1.0.0")
        with self.assertRaisesRegex(ValueError, "en son"):
            gu.uygula()
        self.indir.assert_not_called()

    def test_geri_donus(self):
        if os.name != "nt":
            self.skipTest("exe güncellemesi yalnız Windows")
        with self.assertRaises(ValueError):
            gu.geri()   # Kut.prev.exe yok
        open(self.yollar[2], "wb").write(b"onceki")
        self.assertTrue(gu.durum()["geri_var"])
        gu.geri()
        self.degistir.assert_called_once_with(self.yollar[0], self.yollar[2], self.yollar[2])

    def test_degistirici_betigi_ascii(self):
        gu.DEGISTIRICI_PS1.encode("ascii")

    def test_sums_ayristirma(self):
        self.assertEqual(gu._sums_coz((EXE_SHA.upper() + " *Kut.exe").encode(), "Kut.exe", False), EXE_SHA)
        self.assertEqual(gu._sums_coz(EXE_SHA.encode(), "Kut.exe", True), EXE_SHA)
        self.assertIsNone(gu._sums_coz(EXE_SHA.encode(), "Kut.exe", False))   # SHA256SUMS'ta adsız satır sayılmaz
        self.assertEqual(gu._sums_coz((EXE_SHA + "  Kut.exe\n").encode("utf-16"), "Kut.exe", False), EXE_SHA)
        self.assertIsNone(gu._sums_coz(b"xyz  Kut.exe", "Kut.exe", False))


class GitTest(Temel):
    def setUp(self):
        super().setUp()
        self.ag.side_effect = None
        self.ag.return_value = yayin("1.5.0")
        mock.patch.object(gu, "kurulum_turu", return_value="git").start()
        self.durum = {"remote": "origin\thttps://github.com/koraykutlu/kut.git", "kirli": "", "ff": 0, "head": "a" * 40, "etiket": "b" * 40}
        self.cagrilar = []
        mock.patch.object(gu, "_git", side_effect=self._git).start()
        self.planla = mock.patch.object(gu, "_yeniden_baslat_planla").start()
        self.kapat = mock.patch.object(gu, "_kapat_planla").start()

    def _git(self, *a, zaman=120):
        self.cagrilar.append(a)
        if a[0] == "config":
            return (0, f"remote.origin.url {self.durum['remote'].split(chr(9))[1]}", "") if self.durum["remote"] else (1, "", "")
        if a[0] == "status":
            return 0, self.durum["kirli"], ""
        if a[0] == "fetch":
            return 0, "", ""
        if a[0] == "rev-parse" and a[-1].startswith("refs/tags/"):
            return 0, self.durum["etiket"], ""
        if a[0] == "rev-parse" and a[1] == "HEAD":
            return 0, self.durum["head"], ""
        if a[0] == "merge-base":
            return self.durum["ff"], "", ""
        if a[0] == "merge":
            return 0, "", ""
        if a[0] == "cat-file":
            return 0, "", ""
        if a[0] == "reset":
            return 0, "", ""
        return 1, "", "bilinmeyen"

    def birlestirme_oldu(self):
        return any(c[0] == "merge" for c in self.cagrilar)

    def test_kirli_agac_reddedilir(self):
        self.durum["kirli"] = " M kut/ag_sunucu.py"
        with self.assertRaisesRegex(ValueError, "kaydedilmemiş"):
            gu.uygula()
        self.assertFalse(self.birlestirme_oldu())
        self.assertFalse(any(c[0] == "fetch" for c in self.cagrilar))   # ağa da çıkılmadı
        self.planla.assert_not_called()

    def test_genel_depoyu_izlemeyen_kisisel_depo_yalniz_bildirir(self):
        self.durum["remote"] = "origin\thttps://example.com/benim/kisisel.git"
        with self.assertRaisesRegex(ValueError, "izlemiyor"):
            gu.uygula()
        self.assertFalse(self.birlestirme_oldu())
        self.durum["remote"] = ""
        self.assertIn("izlemiyor", gu.durum()["engel"])   # arayüze engel nedeni gider

    def test_ileri_sarilamiyorsa_reddedilir(self):
        self.durum["ff"] = 1
        with self.assertRaisesRegex(ValueError, "ileri sarılamıyor"):
            gu.uygula()
        self.assertFalse(self.birlestirme_oldu())

    def test_basarili_ileri_sarma_ve_geri_donus(self):
        r = gu.uygula()
        self.assertTrue(r["yeniden"])
        self.assertIn(("merge", "--ff-only", "b" * 40), self.cagrilar)
        self.assertIn(("fetch", "--tags", "origin"), self.cagrilar)
        self.assertEqual(ia.ayarlar()["guncelleme"]["onceki"]["commit"], "a" * 40)   # geri dönüş için önceki commit
        self.assertTrue(gu.durum()["geri_var"])
        self.durum["kirli"] = " M x"
        with self.assertRaisesRegex(ValueError, "geri dönüş reddedildi"):
            gu.geri()
        self.assertFalse(any(c[0] == "reset" for c in self.cagrilar))
        self.durum["kirli"] = ""
        gu.geri()
        self.assertIn(("reset", "--hard", "a" * 40), self.cagrilar)
        self.assertFalse(gu.durum()["geri_var"])

    def test_kaynak_kopya_yalniz_baglanti_verir(self):
        with mock.patch.object(gu, "kurulum_turu", return_value="kaynak"):
            with self.assertRaisesRegex(ValueError, "git deposu değil"):
                gu.uygula()
            with self.assertRaises(ValueError):
                gu.geri()


class GocTest(Temel):
    def setUp(self):
        super().setUp()
        self.veri = os.path.join(self.d.name, "veri")
        os.makedirs(os.path.join(self.veri, "kisiler"))
        open(os.path.join(self.veri, "kisiler", "a.md"), "w", encoding="utf-8").write("ad: A\n")

    def test_goc_yoksa_hicbir_sey_yazilmaz(self):
        self.assertEqual(goc.calistir(self.veri, hedef="1.0.0"), [])
        self.assertFalse(os.path.exists(os.path.join(self.veri, "arsiv")))
        self.assertFalse(os.path.exists(ia.AYARLAR))

    def test_goc_varsa_once_yedek_sonra_calisir(self):
        sira = []

        def f(veri):
            sira.append(("goc", [z for z in os.listdir(os.path.join(veri, "arsiv", "goc"))]))
        with mock.patch.object(goc, "MIGRASYONLAR", [("1.0.5", "deneme", f)]), mock.patch.object(goc.sv, "SURUM", "1.1.0"):
            self.assertEqual(goc.calistir(self.veri, hedef="1.1.0"), ["deneme"])
            self.assertEqual(goc.calistir(self.veri, hedef="1.1.0"), [])   # ikinci kez çalışmaz
        self.assertEqual(len(sira), 1)
        zipler = os.listdir(os.path.join(self.veri, "arsiv", "goc"))
        self.assertEqual(len(zipler), 1)
        with zipfile.ZipFile(os.path.join(self.veri, "arsiv", "goc", zipler[0])) as z:
            self.assertIn("kisiler/a.md", z.namelist())
        self.assertEqual(ia.ayarlar()["veri_surumu"], "1.1.0")
        self.assertEqual(open(os.path.join(self.veri, "kisiler", "a.md"), encoding="utf-8").read(), "ad: A\n")


class StatikTest(unittest.TestCase):
    def test_arayuz_soruyu_ve_uclari_icerir(self):
        h = open(os.path.join(KOK, "ag_sablon.html"), encoding="utf-8").read()
        self.assertIn("Güncellemeleri haftada bir denetleyeyim mi?", h)
        self.assertIn("GitHub'dan yalnız sürüm bilgisi alınır", h)
        for yol in ("/api/guncelleme", "/api/guncelleme/denetle", "/api/guncelleme/ayar", "/api/guncelleme/uygula", "/api/guncelleme/geri"):
            self.assertIn(yol, h)

    def test_paketleme_betigi_ascii_ve_sha256_yazar(self):
        ham = open(os.path.join(KOK_DEPO, "paketleme", "paketle.ps1"), "rb").read()
        ham.decode("ascii")
        self.assertIn(b"Kut.exe.sha256", ham)
        self.assertIn(b"surum.py", ham)


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class GuncellemeApiTest(unittest.TestCase):
    """Ayrı süreçte sunucu, geçici LOCALAPPDATA: kilit ve CSRF kapısı. Ağa çıkan uçlar yalnız kapı denetimiyle denenir."""
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.TemporaryDirectory()
        la = os.path.join(cls.d.name, "la")
        cls.ayar = os.path.join(la, "agim", "ayarlar.json")
        cls.port = bos_port()
        env = {**os.environ, "LOCALAPPDATA": la, "AGIM_VERI": os.path.join(cls.d.name, "veri"), "PYTHONIOENCODING": "utf-8"}
        kod = ("import sys;sys.path.insert(0,%r);import ag_sunucu as s;from http.server import ThreadingHTTPServer;s.PORT=%d;"
               "ThreadingHTTPServer(('127.0.0.1',%d),s.Isleyici).serve_forever()") % (KOK, cls.port, cls.port)
        cls.p = subprocess.Popen([sys.executable, "-c", kod], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()
        cls.p.wait()
        cls.d.cleanup()

    def istek(self, yontem, yol, govde=None, basliklar=None):
        h = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        b = json.dumps(govde).encode() if govde is not None else None
        h.request(yontem, yol, b, {"Content-Type": "application/json", **(basliklar or {})})
        y = h.getresponse()
        veri = y.read()
        r = (y.status, y.getheader("Set-Cookie"), veri)
        h.close()
        return r

    def test_kilit_ve_csrf_kapisi(self):
        uclar = [("GET", "/api/guncelleme", None)] + [("POST", "/api/guncelleme/" + u, {}) for u in ("denetle", "ayar", "uygula", "geri")]
        for y, yol, g in uclar:
            self.assertEqual(self.istek(y, yol, g)[0], 401 if y == "GET" else 403, (y, yol))   # kilitli / anahtarsız
        kod, cerez, _ = self.istek("POST", "/api/kilit/kur", {"pin": "4321", "pin2": "4321"})
        self.assertEqual(kod, 200)
        cerez = {"Cookie": cerez.split(";")[0]}
        sayfa = self.istek("GET", "/", None, cerez)[2].decode("utf-8")
        anahtar = re.search(r'"anahtar":\s*"([^"]+)"', sayfa).group(1)
        a = {**cerez, "X-Ag-Anahtar": anahtar}
        for y, yol, g in uclar:
            self.assertEqual(self.istek(y, yol, g, cerez)[0], 403, (y, yol))   # oturum var, anahtar yok
        self.assertEqual(self.istek("POST", "/api/guncelleme/denetle", {}, {"X-Ag-Anahtar": anahtar})[0], 401)   # anahtar var, oturum yok
        kod, _, g = self.istek("GET", "/api/guncelleme", None, a)
        self.assertEqual(kod, 200)
        d = json.loads(g)
        self.assertEqual(d["surum"], "1.4.0")
        self.assertTrue(d["sorulmadi"])
        self.assertIsNone(d["otomatik"])
        self.assertFalse(os.path.exists(self.ayar) and "guncelleme" in open(self.ayar, encoding="utf-8").read())   # sormadan hiçbir şey yazılmadı
        self.assertEqual(self.istek("POST", "/api/guncelleme/ayar", {"otomatik": "evet"}, a)[0], 400)
        self.assertEqual(self.istek("POST", "/api/guncelleme/ayar", {"otomatik": False}, a)[0], 200)
        d = json.loads(self.istek("GET", "/api/guncelleme", None, a)[2])
        self.assertFalse(d["sorulmadi"])
        self.assertIs(d["otomatik"], False)
        self.assertIs(json.load(open(self.ayar, encoding="utf-8"))["guncelleme"]["otomatik"], False)


if __name__ == "__main__":
    unittest.main()
