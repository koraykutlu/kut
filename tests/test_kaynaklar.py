"""Kaynaklar paneli: etkinlik kapısı (taze kurulum ağa çıkmaz), /api/kaynaklar kilit + CSRF, kalıcılık. Gerçek ağ yok."""
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
from unittest import mock

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
sys.path.insert(0, KOK)
import ag_ice_aktar as ia  # noqa: E402
import ag_kesif as ks  # noqa: E402
import ag_kaynak as kn  # noqa: E402


class EtkinlikKapisiTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.kl = os.path.join(self.d.name, "kesif")
        self.ayar = os.path.join(self.d.name, "ayarlar.json")
        for p in (mock.patch.object(ks, "KLASOR", self.kl), mock.patch.object(ia, "AYARLAR", self.ayar), mock.patch.object(ia, "DEPO", self.d.name)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.d.cleanup()

    def _onbellek(self):
        os.makedirs(self.kl, exist_ok=True)
        with open(os.path.join(self.kl, "etkinlikler.json"), "w", encoding="utf-8") as f:
            json.dump({"tarih": "2026-01-01T00:00", "etkinlikler": [], "hatalar": []}, f)

    def _ayar(self, deger):
        with open(self.ayar, "w", encoding="utf-8") as f:
            json.dump({"kesif": {"etkinlik": deger}}, f)

    def _ag(self, zorla=True):
        with mock.patch.object(ks, "_istek", side_effect=AssertionError("ağ çağrıldı")) as m, mock.patch.object(ks, "robots_izin", return_value=True):
            try:
                ks.etkinlikleri_cek(zorla)
            except AssertionError:
                return True
            return m.called

    def test_taze_kurulum_kapali_ve_ag_yok(self):
        self.assertFalse(ks.etkinlik_acik())
        self.assertFalse(self._ag())
        self.assertTrue(ks.etkinlikleri_cek(True)["kapali"])
        o = ks.etkinlik_onerileri([])
        self.assertTrue(o["veri_yok"] and o["kapali"])

    def test_yenile_kapaliyken_ag_yok(self):
        with mock.patch.object(ks, "_istek", side_effect=AssertionError("ağ çağrıldı")), mock.patch.object(ks, "vekil_verisi_yenile", return_value=False), \
                mock.patch.object(ks, "_vekil_kayitlari"):
            ks.yenile(True)
            for _ in range(50):
                if not ks.durum()["calisiyor"]:
                    break
                time.sleep(0.05)
        self.assertEqual(ks.durum()["hata"], "")
        self.assertIn("kapalı", ks.durum()["mesaj"])

    def test_vekilpedia_kapaliyken_durum_hazirlaniyor_kalmaz(self):
        # Vekilpedia kapalı ve CSV yokken dizin kurulmaya çalışılmaz; Pusula alt başlığı "hazırlanıyor"da takılı kalmaz.
        with mock.patch.object(ks, "_istek", side_effect=AssertionError("ağ çağrıldı")),                 mock.patch.object(ks, "_vekil_kayitlari", side_effect=AssertionError("dizin kuruldu")) as dizin:
            ks.yenile(True)
            for _ in range(100):
                if not ks.durum()["calisiyor"]:
                    break
                time.sleep(0.05)
        self.assertFalse(dizin.called)
        self.assertEqual(ks.durum()["hata"], "")
        self.assertNotIn("hazırlanıyor", ks.durum()["mesaj"])
        self.assertIn("vekil verisi kapalı", ks.durum()["mesaj"])
        self.assertIn("etkinlik taraması kapalı", ks.durum()["mesaj"])

    def test_onbellek_varsa_acik(self):
        self._onbellek()
        self.assertTrue(ks.etkinlik_acik())
        self.assertTrue(self._ag())

    def test_acik_false_onbellek_olsa_da_kapali(self):
        self._onbellek()
        self._ayar(False)
        self.assertFalse(ks.etkinlik_acik())
        self.assertFalse(self._ag())

    def test_acik_true_taze_kurulumda_acik(self):
        self._ayar(True)
        self.assertTrue(ks.etkinlik_acik())
        self.assertTrue(self._ag())

    def test_ayarla_kalici_ve_bilinmeyen_kaynak(self):
        ks.kaynak_ayarla("etkinlik", True)
        self.assertTrue(ks.etkinlik_acik())
        ks.kaynak_ayarla("etkinlik", False)
        self.assertFalse(ks.etkinlik_acik())
        with self.assertRaises(ValueError):
            ks.kaynak_ayarla("rastgele", True)

    def test_durum_okullari_OKULLAR_dan_listeler(self):
        with mock.patch.dict(kn.OKULLAR, {"deneme": {"ad": "Deneme Üni", "ders_kaynak": "x.example"}}):
            d = ks.kaynaklar_durum()
        self.assertEqual({k["id"] for k in d["kaynaklar"]}, {"vekilpedia", "etkinlik", "akademik"})
        self.assertIn("deneme", {o["anahtar"] for o in d["okullar"]})


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class KaynaklarApiTest(unittest.TestCase):
    """Ayrı süreçte sunucu; geçici LOCALAPPDATA'da etkinlik önbelleği var (eski kurulum → açık)."""
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.TemporaryDirectory()
        la = os.path.join(cls.d.name, "la")
        os.makedirs(os.path.join(la, "agim", "kesif"))
        with open(os.path.join(la, "agim", "kesif", "etkinlikler.json"), "w", encoding="utf-8") as f:
            json.dump({"tarih": "2026-01-01T00:00", "etkinlikler": [], "hatalar": []}, f)
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

    def test_kilit_csrf_ve_kalicilik(self):
        self.assertEqual(self.istek("GET", "/api/kaynaklar")[0], 401)   # kilitli
        self.assertEqual(self.istek("POST", "/api/kaynaklar", {"id": "etkinlik", "acik": False})[0], 403)   # CSRF başlığı yok
        kod, cerez, _ = self.istek("POST", "/api/kilit/kur", {"pin": "4321", "pin2": "4321"})
        self.assertEqual(kod, 200)
        cerez = {"Cookie": cerez.split(";")[0]}
        sayfa = self.istek("GET", "/", None, cerez)[2].decode("utf-8")
        anahtar = re.search(r'"anahtar":\s*"([^"]+)"', sayfa).group(1)
        a = {**cerez, "X-Ag-Anahtar": anahtar}
        self.assertEqual(self.istek("GET", "/api/kaynaklar", None, cerez)[0], 403)   # oturum var, anahtar yok
        self.assertEqual(self.istek("POST", "/api/kaynaklar", {"id": "etkinlik", "acik": False}, cerez)[0], 403)
        kod, _, g = self.istek("GET", "/api/kaynaklar", None, a)
        self.assertEqual(kod, 200)
        k = {x["id"]: x for x in json.loads(g)["kaynaklar"]}
        self.assertTrue(k["etkinlik"]["acik"] and not k["vekilpedia"]["acik"])   # eski kurulum: önbellek -> açık; vekil: taze -> kapalı
        self.assertEqual(self.istek("POST", "/api/kaynaklar", {"id": "etkinlik", "acik": False}, a)[0], 200)
        k = {x["id"]: x for x in json.loads(self.istek("GET", "/api/kaynaklar", None, a)[2])["kaynaklar"]}
        self.assertFalse(k["etkinlik"]["acik"])
        self.assertIs(json.load(open(self.ayar, encoding="utf-8"))["kesif"]["etkinlik"], False)   # diske yazıldı
        self.assertEqual(self.istek("POST", "/api/kaynaklar", {"id": "rastgele", "acik": True}, a)[0], 400)
        self.assertEqual(self.istek("POST", "/api/kaynaklar", {"id": "okul", "okul": "yok-boyle-okul"}, a)[0], 400)
        kod, _, g = self.istek("POST", "/api/kaynaklar", {"id": "okul", "okul": "yeditepe"}, a)
        self.assertEqual(kod, 200)
        self.assertEqual(json.loads(g)["okul"], "yeditepe")
        kod, _, g = self.istek("POST", "/api/kaynaklar", {"id": "okul", "okul": ""}, a)
        self.assertEqual(json.loads(g)["okul"], "")


if __name__ == "__main__":
    unittest.main()
