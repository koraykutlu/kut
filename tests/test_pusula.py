import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_cekirdek as c  # noqa: E402
import ag_hedef as hd  # noqa: E402
import ag_kesif as ks  # noqa: E402
import ag_strateji as st  # noqa: E402


class HedefTest(unittest.TestCase):
    def setUp(self):
        self.eski = c.VERI
        self.d = tempfile.TemporaryDirectory()
        c.veri_klasoru(self.d.name)

    def tearDown(self):
        c.veri_klasoru(self.eski)
        self.d.cleanup()

    def test_kaydet_oku_ilerleme(self):
        hid = hd.kaydet({"baslik": "Staj: 3 fintech görüşmesi", "tur": "kariyer", "son_tarih": "2027-03-01", "anahtar": "fintech, staj"})
        h = hd.oku(hid)
        self.assertEqual(h["durum"], "aktif")
        self.assertEqual(h["anahtar"], ["fintech", "staj"])
        hd.ilerleme_ekle(hid, "İlk başvuru gönderildi", "2026-10-12")
        self.assertEqual(hd.oku(hid)["ilerleme"], ["12.10.2026 · İlk başvuru gönderildi"])
        hd.kaydet({**hd.oku(hid), "durum": "tamam"})
        h = hd.oku(hid)
        self.assertEqual(h["durum"], "tamam")
        self.assertEqual(len(h["ilerleme"]), 1)   # düzenleme ilerlemeyi silmez

    def test_gecersiz(self):
        with self.assertRaises(ValueError):
            hd.kaydet({"baslik": ""})
        with self.assertRaises(ValueError):
            hd.kaydet({"baslik": "x", "son_tarih": "31.12.2026"})
        with self.assertRaises(ValueError):
            hd.oku("../ben")


class KesifTest(unittest.TestCase):
    def esles(self, anahtar, metin):
        return bool(ks._anahtar_kalip([anahtar]).search(" " + " ".join(ks.kelimeler(metin)) + " "))

    def test_turkce_ekler(self):
        self.assertTrue(self.esles("su", "İçme suyu kaynaklarında kirlilik"))
        self.assertTrue(self.esles("su", "sular yükseldi"))
        self.assertFalse(self.esles("su", "işlenen suçlara ilişkin"))
        self.assertTrue(self.esles("kuraklık", "kuraklığı önlemek için"))
        self.assertTrue(self.esles("yapay zeka", "Yapay zekâ ile üretilen içerik"))
        self.assertFalse(self.esles("yatırımcı", "karayolu yatırımlarına ilişkin"))

    def test_ld_etkinlik(self):
        sayfa = """<script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"item":{"@type":"Event","name":"AI &amp; Fintech Meetup",
        "startDate":"2099-01-05T18:00","location":{"@type":"Place","name":"Kadıköy","address":{"addressLocality":"İstanbul"}},"url":"https://x.test/e/1"}}]}</script>"""
        e = ks._ld_etkinlikler(sayfa, "deneme")
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["ad"], "AI & Fintech Meetup")
        self.assertIn("İstanbul", e[0]["yer"])
        self.assertFalse(e[0]["cevrimici"])


class StratejiTest(unittest.TestCase):
    def test_kanitsiz_hamle_elenir(self):
        j = st._denetle({"ozet": "x", "hamleler": [
            {"hedef": "a", "baslik": "kanıtlı", "kanit": ["kisiler/ayla.md"]},
            {"hedef": "a", "baslik": "kanıtsız", "kanit": []},
            {"hedef": "yok", "baslik": "bilinmeyen hedef", "kanit": ["x"]}]}, {"a"})
        self.assertEqual([h["baslik"] for h in j["hamleler"]], ["kanıtlı"])


if __name__ == "__main__":
    unittest.main()
