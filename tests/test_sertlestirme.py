"""Güvenlik sertleştirme testleri (SSRF, şablon enjeksiyonu, yol aşımı, zip bombası, başlıklar, günlük). Yalnız sahte veri; gerçek ağ yok."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import email
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest
import urllib.request
import urllib.response
import zipfile
from unittest import mock

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
sys.path.insert(0, KOK)
import ag_cekirdek as c  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_kaynak as kn  # noqa: E402
import ag_vault as v  # noqa: E402


class SsrfTest(unittest.TestCase):
    def test_ozel_adresler_reddedilir(self):
        for u in ("http://localhost/x", "http://127.0.0.1:8080/", "http://127.5.5.5/", "http://10.0.0.5/", "http://192.168.1.1/",
                  "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "file:///etc/passwd", "ftp://93.184.216.34/", "gopher://x/", "//x/y", ""):
            with self.assertRaises(ValueError, msg=u):
                kn._guvenli_url(u)

    def test_genel_adres_kabul(self):
        self.assertEqual(kn._guvenli_url("https://93.184.216.34/a.jpg"), "https://93.184.216.34/a.jpg")

    def test_dns_istekten_hemen_once_cozulur(self):
        sahte = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 443))]
        with mock.patch.object(socket, "getaddrinfo", return_value=sahte):
            with self.assertRaises(ValueError):
                kn._guvenli_url("https://genel-gibi.example/")   # ad genel görünür ama özel adrese çözülüyor
        karma = sahte + [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with mock.patch.object(socket, "getaddrinfo", return_value=karma):
            with self.assertRaises(ValueError):
                kn._guvenli_url("https://karma.example/")   # adreslerden biri özelse hepsi reddedilir

    def test_kaynak_sitesi_disindaki_foto_baglantisi_bos(self):
        self.assertEqual(kn._ayni_site("https://mdbf.ornek.edu.tr", "/sites/f/a.jpg"), "https://mdbf.ornek.edu.tr/sites/f/a.jpg")
        self.assertEqual(kn._ayni_site("https://mdbf.ornek.edu.tr", "https://cdn.ornek.edu.tr/a.jpg"), "https://cdn.ornek.edu.tr/a.jpg")
        for kotu in ("http://169.254.169.254/x", "https://evil.example/a.jpg", "javascript:alert(1)", "file:///c:/x.jpg",
                     "https://ornek.edu.tr.evil.example/a"):
            self.assertEqual(kn._ayni_site("https://mdbf.ornek.edu.tr", kotu), "", kotu)

    def test_istek_ozel_adrese_gitmez(self):
        with self.assertRaises(OSError):
            kn._istek("http://127.0.0.1:9/")

    def test_yonlendirme_ozel_adrese_reddedilir(self):
        class Sahte(urllib.request.HTTPHandler):
            def http_open(self, req):
                if "93.184.216.34" in req.full_url:
                    r = urllib.response.addinfourl(io.BytesIO(b""), email.message_from_string("Location: http://10.0.0.5/x\n\n"), req.full_url, 302)
                    r.msg = "Found"
                    return r
                raise AssertionError("özel adrese istek gitti: " + req.full_url)
        with self.assertRaises(OSError):   # URLError, OSError alt sınıfıdır
            kn._istek("http://93.184.216.34/a", acici=kn.guvenli_acici(Sahte()))

    def test_okuma_siniri(self):
        self.assertEqual(kn.sinirli_oku(io.BytesIO(b"x" * 10), 10), b"x" * 10)
        with self.assertRaises(OSError):
            kn.sinirli_oku(io.BytesIO(b"x" * 11), 10)


class SayfaTest(unittest.TestCase):
    def test_yer_tutucu_enjeksiyonu(self):
        ad = "/*KILIT*/null /*MOD*/null /*VERI*/null"
        h = c.sayfa({"kisiler": [{"ad": ad}]}, {"anahtar": "ABC"}, {"acik": True})
        govde = h.split("const VERI = ", 1)[1].split(";\n", 1)[0]
        self.assertEqual(json.loads(govde.replace("<\\/", "</"))["kisiler"][0]["ad"], ad)
        self.assertIn('const MOD = {"anahtar": "ABC"};', h)
        self.assertIn('const KILIT = {"acik": true};', h)

    def test_script_etiketi_kapatilamaz(self):
        h = c.sayfa({"x": "</script><script>alert(1)</script><!-- "}, None, None)
        self.assertNotIn("</script><script>alert(1)", h)
        self.assertNotIn("<!--", h.split("const VERI = ", 1)[1].split("\n", 1)[0])

    def test_gecerli_id_satir_sonu(self):
        self.assertTrue(c.gecerli_id("ayla-ornek"))
        self.assertFalse(c.gecerli_id("ayla-ornek\n"))
        self.assertFalse(c.gecerli_id("../x"))


class FotoTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.veri = os.path.join(self.d.name, "veri")
        os.makedirs(os.path.join(self.veri, "foto"))
        self.p = [mock.patch.object(c, "VERI", self.veri), mock.patch.object(c, "FOTO", os.path.join(self.veri, "foto"))]
        for x in self.p:
            x.start()
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
        for yol in (("veri", "foto", "a.png"), ("veri", "gizli.png"), ("disarda.png",)):
            with open(os.path.join(self.d.name, *yol), "wb") as f:
                f.write(png)
        with open(os.path.join(self.veri, "foto", "not.txt"), "w") as f:
            f.write("sahte not")

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.d.cleanup()

    def test_gecerli_foto(self):
        self.assertTrue(c.foto_veri("foto/a.png").startswith("data:image/png;base64,"))

    def test_yol_asimi_ve_mutlak_yol(self):
        mutlak = os.path.join(self.d.name, "disarda.png")
        for y in ("../disarda.png", "foto/../../disarda.png", "foto/../gizli.png", mutlak, "gizli.png", "foto", "foto/not.txt",
                  "foto/yok.png", "", None, "foto/a.png\x00.txt"):
            self.assertEqual(c.foto_veri(y), "", repr(y))

    def test_boyut_siniri(self):
        with mock.patch.object(c, "FOTO_AZAMI", 10):
            self.assertEqual(c.foto_veri("foto/a.png"), "")


class HaricTest(unittest.TestCase):
    def test_turkce_buyuk_harf_atlatmaz(self):
        with tempfile.TemporaryDirectory() as k:
            kok = os.path.realpath(k)
            for yol in ("Notes/DÜŞÜNCELER/x.md", "notes/Dusunceler/x.md", "Notes/KİŞİSEL/x.md", "NOTES/Kisisel/x.md",
                        "Journal.md", "JOURNAL.MD", "Receipts/r.md"):
                self.assertIsNone(v._izinli(kok, os.path.join(kok, *yol.split("/"))), yol)
            nfd = unicodedata.normalize("NFD", "notes/düşünceler/x.md")
            self.assertIsNone(v._izinli(kok, os.path.join(kok, *nfd.split("/"))))
            self.assertIsNotNone(v._izinli(kok, os.path.join(kok, "tasks", "a.md")))


class ZipTest(unittest.TestCase):
    def zip(self, dosyalar):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            for ad, ham in dosyalar.items():
                z.writestr(ad, ham)
        return b.getvalue()

    def test_zip_bombasi_reddedilir(self):
        bomba = self.zip({"_chat.txt": b"0" * 40_000_000})
        self.assertLess(len(bomba), 200_000)
        with self.assertRaises(ValueError):
            list(ia._txt_metinleri("x.zip", bomba))

    def test_toplam_ve_guvensiz_ad(self):
        with mock.patch.object(ia, "ZIP_TOPLAM_AZAMI", 1000):
            with self.assertRaises(ValueError):
                list(ia._txt_metinleri("x.zip", self.zip({"a.txt": os.urandom(800), "b.txt": os.urandom(800)})))
        with self.assertRaises(ValueError):
            list(ia._txt_metinleri("x.zip", self.zip({"../x.txt": b"a"})))

    def test_normal_zip(self):
        sonuc = list(ia._txt_metinleri("x.zip", self.zip({"_chat.txt": "merhaba\n".encode() * 50})))
        self.assertEqual(sonuc[0][0], "x.zip")
        self.assertIn("merhaba", sonuc[0][1])


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SunucuTest(unittest.TestCase):
    """Geçici LOCALAPPDATA ve AGIM_VERI ile ayrı süreçte sunucu (otomatik doldurma/tarayıcı yok)."""
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.TemporaryDirectory()
        cls.port = bos_port()
        env = {**os.environ, "LOCALAPPDATA": os.path.join(cls.d.name, "la"), "AGIM_VERI": os.path.join(cls.d.name, "veri"),
               "PYTHONIOENCODING": "utf-8"}
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
        h.putrequest(yontem, yol)
        for k, d in (basliklar or {}).items():
            h.putheader(k, d)
        if govde is not None:
            h.putheader("Content-Length", str(len(govde)))
        h.endheaders(govde)
        y = h.getresponse()
        veri = y.read()
        r = (y.status, dict((k.lower(), d) for k, d in y.getheaders()), veri)
        h.close()
        return r

    def test_guvenlik_basliklari(self):
        for yontem, yol in (("GET", "/"), ("GET", "/api/nabiz"), ("GET", "/yok-boyle-bir-uc"), ("POST", "/api/kilit/ac")):
            kod, b, _ = self.istek(yontem, yol, b"{}" if yontem == "POST" else None, {"Content-Type": "application/json"})
            self.assertIn("frame-ancestors 'none'", b.get("content-security-policy", ""), (yol, kod))
            self.assertIn("default-src 'self'", b["content-security-policy"])
            self.assertEqual(b.get("x-frame-options"), "DENY")
            self.assertEqual(b.get("x-content-type-options"), "nosniff")
            self.assertEqual(b.get("referrer-policy"), "no-referrer")

    def test_negatif_ve_gecersiz_content_length(self):
        for cl, beklenen in (("-5", 400), ("abc", 400), ("99999", 413)):
            for yol in ("/api/kilit/ac", "/api/kilit/kur"):
                h = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
                h.putrequest("POST", yol)
                h.putheader("Content-Length", cl)
                h.endheaders()
                self.assertEqual(h.getresponse().status, beklenen, (yol, cl))
                h.close()

    def test_pin_sonrasi_arayuz_ve_csp(self):
        kod, b, _ = self.istek("POST", "/api/kilit/kur", json.dumps({"pin": "4321", "pin2": "4321"}).encode(),
                               {"Content-Type": "application/json"})
        self.assertEqual(kod, 200)
        cerez = b["set-cookie"].split(";")[0]
        kod, b, govde = self.istek("GET", "/", None, {"Cookie": cerez})
        self.assertEqual(kod, 200)
        self.assertIn("frame-ancestors 'none'", b["content-security-policy"])
        self.assertIn(b'"acik": true', govde)


class GunlukTest(unittest.TestCase):
    def test_sohbet_icerigi_gunluge_yazilmaz(self):
        import ag_sunucu as s
        with tempfile.TemporaryDirectory() as d:
            eski = c.VERI
            try:
                c.veri_klasoru(os.path.join(d, "veri"))
                kayit = os.path.join(d, "sunucu.log")
                gizli = "COK-GIZLI-NOT-ICERIGI"
                with mock.patch.object(s, "GUNLUK", kayit), mock.patch.object(ia, "DEPO", d), mock.patch.object(s, "statik_yenile"):
                    k, a = s.kayitlari_uygula([{"islem": "beyan", "yeni": {"ad": "Deneme Kisi"}, "metin": gizli},
                                               {"islem": "beyan", "yeni": {"ad": "Baska Kisi"}, "metin": gizli}])
                    self.assertTrue(k, (k, a))
                    try:
                        raise ValueError(gizli)
                    except ValueError:
                        s.gunluk("x: " + s.hata_izi())
                log = open(kayit, encoding="utf-8").read()
                self.assertIn("kut sohbeti kayıt", log)
                self.assertNotIn(gizli, log)
                self.assertNotIn("Deneme", log)
            finally:
                c.veri_klasoru(eski)


if __name__ == "__main__":
    unittest.main()
