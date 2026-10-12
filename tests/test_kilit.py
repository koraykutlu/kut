import importlib
import io
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_ice_aktar as ia  # noqa: E402
import ag_kilit as kl  # noqa: E402


class KilitTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.y = mock.patch.object(ia, "AYARLAR", os.path.join(self.d.name, "ayarlar.json"))
        self.y.start()
        kl.kapat()

    def tearDown(self):
        self.y.stop()
        self.d.cleanup()

    def test_pin_ozet_olarak_saklanir(self):
        kl.pin_yaz("2468")
        a = ia.ayarlar()["kilit"]
        self.assertNotIn("2468", str(a))
        self.assertTrue(kl.pin_dogru("2468"))
        self.assertFalse(kl.pin_dogru("2469"))

    def test_kisa_pin_reddedilir(self):
        with self.assertRaises(ValueError):
            kl.pin_yaz("12")

    def test_yanlis_denemede_bekleme(self):
        kl.pin_yaz("2468")
        for _ in range(5):
            with self.assertRaises(ValueError):
                kl.ac("0000")
        with self.assertRaises(PermissionError):
            kl.ac("2468")   # doğru PIN bile bekleme bitmeden açmaz

    def test_oturum_suresi_dolar(self):
        kl.pin_yaz("2468", sure=5)
        t = kl.ac("2468")
        self.assertTrue(kl.gecerli(t))
        kl._oturumlar[t] = time.time() - 6 * 60
        self.assertFalse(kl.gecerli(t))
        self.assertFalse(kl.gecerli(t))

    def test_sure_sifir_ise_dolmaz_ve_kapat_kilitler(self):
        kl.pin_yaz("2468", sure=0)
        t = kl.ac("2468")
        kl._oturumlar[t] = time.time() - 10 * 3600
        self.assertTrue(kl.gecerli(t))
        kl.kapat(t)
        self.assertFalse(kl.gecerli(t))

    def test_kilitli_veride_kisi_yok(self):
        v = kl.bos_veri()
        self.assertEqual(len(v["kisiler"]), 1)
        self.assertEqual(v["iliskiler"], [])
        self.assertEqual(v["kisiler"][0]["foto"], "")

    def test_cerez(self):
        self.assertEqual(kl.cerez_oku("a=1; kut_oturum=xyz; b=2"), "xyz")
        self.assertIn("HttpOnly", kl.cerez_yaz("xyz"))

    def test_paralel_yanlis_denemeler_sayilir(self):
        kl.pin_yaz("2468")
        sayac, lk = [0], threading.Lock()
        gercek = kl._ozet

        def sayan(*a):
            with lk:
                sayac[0] += 1
            return gercek(*a)
        sonuc = []

        def dene():
            try:
                kl.ac("0000")
                sonuc.append("acildi")
            except ValueError:
                sonuc.append(400)
            except PermissionError:
                sonuc.append(429)
        with mock.patch.object(kl, "_ozet", sayan):
            t = [threading.Thread(target=dene) for _ in range(20)]
            [x.start() for x in t]
            [x.join() for x in t]
        self.assertEqual(sonuc.count(400), 5)
        self.assertEqual(sonuc.count(429), 15)
        self.assertEqual(sayac[0], 5)

    def test_sayac_yeniden_baslatmada_kalir(self):
        kl.pin_yaz("2468")
        for _ in range(5):
            with self.assertRaises(ValueError):
                kl.ac("0000")
        importlib.reload(kl)   # sunucu yeniden başladı
        with self.assertRaises(PermissionError):
            kl.ac("2468")
        k = ia.ayarlar()["kilit"]
        self.assertEqual(k["hata"], 5)
        self.assertGreater(k["bekle"], time.time())

    def test_bekleme_ussel_artar_ve_basari_sifirlar(self):
        kl.pin_yaz("2468")
        for _ in range(5):
            with self.assertRaises(ValueError):
                kl.ac("0000")
        a = ia.ayarlar()
        self.assertAlmostEqual(a["kilit"]["bekle"] - time.time(), 30, delta=3)
        a["kilit"]["bekle"] = 0   # bekleme bitti
        ia.ayar_yaz(a)
        with self.assertRaises(ValueError):
            kl.ac("0000")
        self.assertAlmostEqual(ia.ayarlar()["kilit"]["bekle"] - time.time(), 60, delta=3)
        a = ia.ayarlar()
        a["kilit"]["bekle"] = 0
        ia.ayar_yaz(a)
        self.assertTrue(kl.ac("2468"))
        self.assertNotIn("hata", ia.ayarlar()["kilit"])

    def test_dogrula_sayaclidir_degistirme_icin(self):
        kl.pin_yaz("2468")
        self.assertFalse(kl.dogrula("1111"))
        self.assertEqual(ia.ayarlar()["kilit"]["hata"], 1)
        self.assertTrue(kl.dogrula("2468"))
        self.assertNotIn("hata", ia.ayarlar()["kilit"])

    def test_eski_ozet_calisir_ve_acilinca_yenilenir(self):
        tuz = "ab" * 16
        a = ia.ayarlar()
        a["kilit"] = {"tuz": tuz, "ozet": kl._ozet("2468", tuz, 1000), "n": 1000, "sure_dk": 15}
        ia.ayar_yaz(a)
        self.assertTrue(kl.pin_dogru("2468"))
        self.assertTrue(kl.ac("2468"))
        k = ia.ayarlar()["kilit"]
        self.assertEqual(k["n"], kl.N)
        self.assertEqual(kl.N, 600_000)
        self.assertTrue(kl.pin_dogru("2468"))
        self.assertFalse(kl.pin_dogru("1111"))

    def test_kur_mevcut_pin_eskiyi_ister(self):
        import ag_sunucu as sv
        kl.pin_yaz("2468")
        h = sv.Isleyici.__new__(sv.Isleyici)
        sonuc = []
        h._gonder = lambda kod, g, **kw: sonuc.append((kod, g))
        h._acik = lambda dokun=True: True
        h.headers = {"Content-Length": "0"}
        h.rfile = io.BytesIO(b'{"pin": "9999", "pin2": "9999"}')
        h.headers = {"Content-Length": str(len(h.rfile.getvalue()))}
        h._kilit_islem("/api/kilit/kur")
        self.assertEqual(sonuc[-1][0], 400)
        self.assertTrue(kl.pin_dogru("2468"))


class UretKilitTest(unittest.TestCase):
    def test_pin_kuruluysa_ag_html_uretilmez_ve_eskisi_silinir(self):
        import ag_cekirdek as c
        import ag_uret
        with tempfile.TemporaryDirectory() as d:
            html = os.path.join(d, "ag.html")
            open(html, "w").write("eski")
            with mock.patch.object(ia, "AYARLAR", os.path.join(d, "ayarlar.json")),                     mock.patch.object(c, "VERI", d), mock.patch.object(sys, "argv", ["ag_uret.py"]),                     mock.patch.object(sys, "stderr", io.StringIO()), mock.patch.object(sys, "stdout", mock.Mock()):
                kl.pin_yaz("2468")
                self.assertEqual(ag_uret.main(), 1)
            self.assertFalse(os.path.exists(html))


if __name__ == "__main__":
    unittest.main()
