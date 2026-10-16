"""Aynı WhatsApp dışa aktarmasını yeniden bırakmak: değişiklik yoksa hiçbir şey olmaz ve bu açıkça söylenir; daha yeni dışa aktarma
ağdaki kişiyi onay listesine geri getirir. Yalnız kurgusal veri; ağ ve model yok."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_ice_aktar as ia  # noqa: E402


def sohbet(son_gun, ek=0):
    satir = ["[01.08.2026, 10:00:00] Kovan: ‎You created group “Kovan”"]
    for g in range(1, son_gun + 1):
        satir += [f"[{g:02d}.08.2026, 12:00:00] Deniz: merhaba {g}", f"[{g:02d}.08.2026, 12:05:00] Selin: selam {g}",
                  f"[{g:02d}.08.2026, 12:06:00] Ben Kişi: naber {g}"]
    for i in range(ek):
        satir.append(f"[{son_gun:02d}.08.2026, 13:{i:02d}:00] Deniz: ek {i}")
    return ("\n".join(satir) + "\n").encode("utf-8")


class YenidenIceAktarma(unittest.TestCase):
    def setUp(self):
        ia.adaylar_yaz({})
        self.p = mock.patch.object(ia, "ben_adlari_al", return_value=["Ben Kişi"])
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def ekle(self, kisi_ids):
        h = ia.adaylar()
        for a in h.values():
            a["durum"], a["kisi"] = "eklendi", kisi_ids[a["ad"]]
        ia.adaylar_yaz(h)

    def test_ayni_dosya_ikinci_kez_degisiklik_yok_der(self):
        r1 = ia.ice_aktar("_chat.txt", sohbet(10), [])
        self.assertEqual(r1["yeni"], 2)
        self.ekle({"Deniz": "deniz", "Selin": "selin"})
        mevcut = [{"id": "deniz", "ad": "Deniz"}, {"id": "selin", "ad": "Selin"}]
        r2 = ia.ice_aktar("_chat 3.txt", sohbet(10), mevcut)
        self.assertEqual((r2["yeni"], r2["guncellenen"], r2["agda_guncellenecek"]), (0, 0, []))
        self.assertEqual(r2["degismeyen"], ["Kovan"])
        self.assertEqual(r2["agda_olan"], ["Deniz", "Selin"])
        self.assertTrue(all(a["durum"] == "eklendi" for a in ia.adaylar().values()))

    def test_eski_dosya_yeni_kaydi_ezmez(self):
        ia.ice_aktar("_chat.txt", sohbet(20), [])
        self.ekle({"Deniz": "deniz", "Selin": "selin"})
        r = ia.ice_aktar("_chat 2.txt", sohbet(5), [{"id": "deniz", "ad": "Deniz"}, {"id": "selin", "ad": "Selin"}])
        self.assertEqual(r["degismeyen"], ["Kovan"])
        son = {a["ad"]: a["kaynaklar"][0]["son"] for a in ia.adaylar().values()}
        self.assertEqual(son, {"Deniz": "2026-08-20", "Selin": "2026-08-20"})

    def test_daha_yeni_disa_aktarma_agdaki_kisiyi_onaya_getirir(self):
        ia.ice_aktar("_chat.txt", sohbet(10), [])
        self.ekle({"Deniz": "deniz", "Selin": "selin"})
        r = ia.ice_aktar("_chat.txt", sohbet(25), [{"id": "deniz", "ad": "Deniz"}, {"id": "selin", "ad": "Selin"}])
        self.assertEqual(r["agda_guncellenecek"], ["Deniz", "Selin"])
        h = {a["ad"]: a for a in ia.adaylar().values()}
        self.assertEqual(h["Deniz"]["durum"], "yeni")
        self.assertEqual(h["Deniz"]["eslesen"], "deniz")   # aynı kişiye bağlı kalır, yeni kişi açılmaz
        self.assertEqual(h["Deniz"]["kaynaklar"][0]["son"], "2026-08-25")

    def test_ayni_tarih_daha_cok_mesaj_da_yenidir(self):
        ia.ice_aktar("_chat.txt", sohbet(10), [])
        self.ekle({"Deniz": "deniz", "Selin": "selin"})
        r = ia.ice_aktar("_chat.txt", sohbet(10, ek=5), [{"id": "deniz", "ad": "Deniz"}, {"id": "selin", "ad": "Selin"}])
        self.assertEqual(r["agda_guncellenecek"], ["Deniz"])
        self.assertEqual(r["degismeyen"], [])


if __name__ == "__main__":
    unittest.main()
