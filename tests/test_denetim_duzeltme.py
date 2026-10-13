"""Denetçi bulgularının regresyon testleri: robots.txt kararları, ag_model yol denetimi, ders onay ucu ve girdi tipi denetimleri. Gerçek ağ yok."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

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
from unittest import mock

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
sys.path.insert(0, KOK)
import ag_ice_aktar as ia  # noqa: E402
import ag_kesif as ks  # noqa: E402
import ag_model as mdl  # noqa: E402


def http_hata(kod):
    return urllib.error.HTTPError("https://ornek.example/robots.txt", kod, "x", {}, None)


class RobotsTest(unittest.TestCase):
    def setUp(self):
        ks._robots.clear()
        self.addCleanup(ks._robots.clear)

    def izin(self, istek, url="https://ornek.example/etkinlik"):
        with mock.patch.object(ks, "_istek", istek):
            return ks.robots_izin(url)

    def test_yalniz_404_ve_410_serbest(self):
        for kod in (404, 410):
            ks._robots.clear()
            self.assertTrue(self.izin(mock.Mock(side_effect=http_hata(kod))), kod)

    def test_401_403_yasak(self):
        for kod in (401, 403):
            ks._robots.clear()
            self.assertFalse(self.izin(mock.Mock(side_effect=http_hata(kod))), kod)

    def test_gecici_hatalar_yasak(self):
        for hata in (http_hata(500), http_hata(503), http_hata(429), TimeoutError("zaman aşımı"), OSError("adres reddedildi: özel ağ"),
                     urllib.error.URLError("bağlantı")):
            ks._robots.clear()
            self.assertFalse(self.izin(mock.Mock(side_effect=hata)), repr(hata))

    def test_gecici_yasak_kisa_surede_yeniden_denenir(self):
        ist = mock.Mock(side_effect=http_hata(503))
        self.assertFalse(self.izin(ist))
        self.assertFalse(self.izin(ist))
        self.assertEqual(ist.call_count, 1)   # süre dolmadan yeniden sorulmaz
        kok = "https://ornek.example"
        karar, bitis = ks._robots[kok]
        self.assertAlmostEqual(bitis - time.time(), ks.ROBOTS_KISA_DAKIKA * 60, delta=5)
        ks._robots[kok] = (karar, time.time() - 1)   # TTL doldu
        ist2 = mock.Mock(return_value=b"User-agent: *\nDisallow: /gizli\n")
        self.assertTrue(self.izin(ist2))
        self.assertEqual(ist2.call_count, 1)
        self.assertFalse(self.izin(ist2, "https://ornek.example/gizli/x"))
        self.assertEqual(ist2.call_count, 1)   # uzun TTL: önbellekte
        self.assertAlmostEqual(ks._robots[kok][1] - time.time(), ks.ROBOTS_UZUN_SAAT * 3600, delta=5)

    def test_ajan_adi_user_agent_ile_tutarli(self):
        self.assertIn(ks.ROBOT_AJANI + "/", ks.TARAYICI)   # robots'ta sorulan ürün adı, isteklerde de ürün belirteci
        kural = b"User-agent: Kut\nDisallow: /\n\nUser-agent: *\nDisallow:\n"
        self.assertFalse(self.izin(mock.Mock(return_value=kural)))   # "Kut" için özel yasak uygulanır
        ks._robots.clear()
        self.assertTrue(self.izin(mock.Mock(return_value=b"User-agent: Baska\nDisallow: /\n")))


class ModelYolTest(unittest.TestCase):
    def test_yol_yoksa_anlasilir_hata(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        eski = ia.AYARLAR
        ia.AYARLAR = os.path.join(t.name, "ayarlar.json")
        self.addCleanup(setattr, ia, "AYARLAR", eski)
        with mock.patch.object(mdl, "yol_bul", return_value=None), mock.patch.object(mdl, "_calistir", side_effect=AssertionError("çalıştırılmamalı")):
            for sag, ad in (("claude", "Claude Code"), ("codex", "Codex"), ("gemini", "Gemini")):
                ia.ayar_yaz({"saglayici": sag})
                with self.assertRaises(RuntimeError) as e:
                    mdl.cagir("analiz", "x", cwd=os.path.join(t.name, "c"))
                self.assertIn(ad, str(e.exception))
                self.assertIn("bulunamadı", str(e.exception))


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class UcDenetimiTest(unittest.TestCase):
    """Ayrı süreçte sunucu: 400 tip denetimleri, ders onay ucunun kilit/anahtar/Origin kapıları."""
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.TemporaryDirectory()
        la = os.path.join(cls.d.name, "la")
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
        h = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        b = json.dumps(govde).encode() if govde is not None else None
        h.request(yontem, yol, b, {"Content-Type": "application/json", **(basliklar or {})})
        y = h.getresponse()
        veri = y.read()
        r = (y.status, y.getheader("Set-Cookie"), veri)
        h.close()
        return r

    def test_kapilar_ve_tip_denetimi(self):
        self.assertEqual(self.istek("POST", "/api/ders/onayla", {"kodlar": ["ISE 424"]})[0], 403)   # kilitli, anahtarsız
        kod, cerez, _ = self.istek("POST", "/api/kilit/kur", {"pin": "4321", "pin2": "4321"})
        self.assertEqual(kod, 200)
        cerez = {"Cookie": cerez.split(";")[0]}
        anahtar = re.search(r'"anahtar":\s*"([^"]+)"', self.istek("GET", "/", None, cerez)[2].decode("utf-8")).group(1)
        a = {**cerez, "X-Ag-Anahtar": anahtar}
        # ders onay ucu: anahtar + oturum + yerel Origin
        self.assertEqual(self.istek("POST", "/api/ders/onayla", {"kodlar": ["ISE 424"]}, cerez)[0], 403)                                 # anahtar yok
        self.assertEqual(self.istek("POST", "/api/ders/onayla", {"kodlar": ["ISE 424"]}, {"X-Ag-Anahtar": anahtar})[0], 401)            # oturum yok
        self.assertEqual(self.istek("POST", "/api/ders/onayla", {"kodlar": ["ISE 424"]}, {**a, "Origin": "http://evil.example"})[0], 403)  # yabancı kaynak
        # KOKEN_DENETIMLI'ye eklenen uçlar
        for yol, g in (("/api/saglayici", {"saglayici": "claude"}), ("/api/ses/kurulum/ayar", {"cevap": "sorma"})):
            self.assertEqual(self.istek("POST", yol, g, {**a, "Origin": "http://evil.example"})[0], 403, yol)
        # geçersiz kodlar 400
        for kotu in ({"kodlar": ["MART 2026"]}, {"kodlar": "ISE 424"}, {"kodlar": []}):
            self.assertEqual(self.istek("POST", "/api/ders/onayla", kotu, a)[0], 400, kotu)
        # geçerli onay yazar (okul seçili değil: ağ yok) ve okulu sorar
        kod, _, v = self.istek("POST", "/api/ders/onayla", {"kodlar": ["ISE 424", "MATH 101"]}, {**a, "Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(kod, 200, v)
        self.assertTrue(json.loads(v)["okul_sor"])
        # tip denetimleri: 500 değil 400
        self.assertEqual(self.istek("GET", "/api/ses/kurulum?plan=1&parca=zzz", None, a)[0], 400)
        self.assertEqual(self.istek("GET", "/api/ses/kurulum?plan=1&model=zzz", None, a)[0], 400)
        self.assertEqual(self.istek("GET", "/api/ses/kurulum?plan=1&parca=yaz", None, a)[0], 200)
        for g in ({"soru": "selam", "oturum": ["a"]}, {"soru": ["a"]}, {"soru": "selam", "kisi": {"x": 1}}):
            self.assertEqual(self.istek("POST", "/api/sor", g, a)[0], 400, g)


if __name__ == "__main__":
    unittest.main()
