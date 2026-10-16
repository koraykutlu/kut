"""Tanıştırma yolu (ag_yol): sıralama, engeller, kenar durumları, gerekçe/uyarı/taslak metinleri, ara() ve performans. Kurgusal adlar; dosya sistemi yok."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import copy
import json
import os
import random
import sys
import time
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_cekirdek as c  # noqa: E402
import ag_yol as yol  # noqa: E402

BUGUN = date(2026, 10, 15)
BEN = c.ben_id()


def K(kid, ad, yak=0, sic=None, son=None, **ek):
    """Bir kişi kaydı (veri_hazirla biçiminde, gerekli alanlar)."""
    k = {"id": kid, "ad": ad, "tur": "cevre", "kurum": "", "rol": "", "alan": [], "etiketler": [], "nereden": [], "yakinlik": yak,
         "son_temas": "", "etkin_son_temas": son or "", "haric": False, "puan": {"sicaklik": sic}}
    k.update(ek)
    return k


def R(a, b, tip, **ek):
    return {"a": a, "b": b, "tip": tip, "not": "", "kaynak": "", "tarih": "", **ek}


def VERI(kisiler, iliskiler=(), dikkatler=None):
    kisiler = list(kisiler)
    return {"kisiler": [{"id": BEN, "ad": "Umut", "tur": "cevre", "yakinlik": 0, "haric": False}] + kisiler,
            "iliskiler": list(iliskiler),
            "dikkatler": c.dikkatler(kisiler, list(iliskiler)) if dikkatler is None else dikkatler,
            "uretildi": BUGUN.isoformat()}


def gun(n):
    return (BUGUN - timedelta(days=n)).isoformat()


def idler(y):
    return [d["id"] for d in y["dugumler"]]


class CizgeTemel(unittest.TestCase):
    def setUp(self):
        # Ben ─ elif(3, sıcak) ─ selin-hoca ; Ben ─ baran(1) ─ selin-hoca (tanışıyor)
        self.veri = VERI([K("elif", "Elif Demir", 3, 100, gun(3)), K("baran", "Baran Kaya", 1, 40, gun(40)), K("selin-hoca", "Selin Hoca")],
                         [R("elif", "selin-hoca", "birlikte-calisiyor"), R("baran", "selin-hoca", "tanisiyor")])

    def test_en_sicak_yol_once(self):
        s = yol.yollar(self.veri, "selin-hoca")
        self.assertFalse(s["dogrudan"])
        self.assertEqual(s["yok_nedeni"], "")
        self.assertEqual(s["hedef"]["id"], "selin-hoca")
        self.assertEqual([idler(y) for y in s["yollar"]], [[BEN, "elif", "selin-hoca"], [BEN, "baran", "selin-hoca"]])
        self.assertGreater(s["yollar"][0]["skor"], s["yollar"][1]["skor"])
        self.assertEqual(s["yollar"][0]["ilk_adim"], {"id": "elif", "ad": "Elif Demir"})

    def test_skor_formulu(self):
        y = yol.yollar(self.veri, "selin-hoca")["yollar"]
        self.assertEqual(y[0]["skor"], round(100 * 0.92 * 1.0 * 0.7))             # yakınlık 3, sıcaklık 100, birlikte-çalışıyor
        self.assertEqual(y[1]["skor"], round(100 * 0.45 * (0.55 + 0.45 * 0.40) * 0.4))   # yakınlık 1, sıcaklık 40, tanışıyor
        self.assertEqual([e["guc"] for e in y[0]["kenarlar"]], [92, 70])

    def test_sicaklik_yoksa_0_7(self):
        v = VERI([K("a", "Ayşe", 2, None), K("t", "Tolga")], [R("a", "t", "arkadas")])
        (y,) = yol.yollar(v, "t")["yollar"]
        self.assertEqual(y["skor"], round(100 * 0.75 * 0.7 * 0.8))
        v = VERI([K("a", "Ayşe", 2, 0), K("t", "Tolga")], [R("a", "t", "arkadas")])
        self.assertEqual(yol.yollar(v, "t")["yollar"][0]["skor"], round(100 * 0.75 * 0.55 * 0.8))

    def test_sicak_bag_soguktan_once(self):
        v = VERI([K("sicak", "Sıla", 2, 100), K("soguk", "Soner", 2, 0), K("t", "Tolga")],
                 [R("soguk", "t", "arkadas"), R("sicak", "t", "arkadas")])   # satır sırası sonucu değiştirmez
        s = yol.yollar(v, "t")["yollar"]
        self.assertEqual([y["ilk_adim"]["id"] for y in s], ["sicak", "soguk"])
        self.assertEqual([y["skor"] for y in s], [60, 33])

    def test_guclu_kenar_zayif_kisayoldan_iyi(self):
        # doğrudan zayıf bağ yerine iki güçlü halka; ama yakınlık 0 hedefe tek kenarlı yol yoktur
        v = VERI([K("a", "Ayşe", 3, 100), K("b", "Bora", 1, 100), K("t", "Tolga")], [R("a", "t", "arkadas"), R("b", "t", "arkadas")])
        s = yol.yollar(v, "t")["yollar"]
        self.assertEqual(s[0]["ilk_adim"]["id"], "a")

    def test_atlama_cezasi(self):
        def v(zincir):
            kisiler = [K("a", "Ayşe", 3, 100)] + [K(x, x.upper()) for x in zincir]
            ids = ["a"] + zincir
            return VERI(kisiler, [R(ids[i], ids[i + 1], "arkadas") for i in range(len(ids) - 1)])
        self.assertEqual(yol.yollar(v(["t"]), "t")["yollar"][0]["skor"], round(100 * 0.92 * 0.8))                 # 2 kenar
        self.assertEqual(yol.yollar(v(["b", "t"]), "t")["yollar"][0]["skor"], round(100 * 0.92 * 0.8 ** 2 * 0.9))      # 3 kenar
        self.assertEqual(yol.yollar(v(["b", "d", "t"]), "t")["yollar"][0]["skor"], round(100 * 0.92 * 0.8 ** 3 * 0.81))   # 4 kenar

    def test_en_cok_dort_kenar(self):
        def zincir(n):   # BEN → a → x1 … → t, toplam n kenar
            ids = ["a"] + [f"x{i}" for i in range(n - 2)] + ["t"]
            return VERI([K("a", "Ayşe", 3, 100)] + [K(x, x.upper()) for x in ids[1:]], [R(ids[i], ids[i + 1], "arkadas") for i in range(len(ids) - 1)])
        s4 = yol.yollar(zincir(4), "t")
        self.assertEqual(len(s4["yollar"][0]["kenarlar"]), 4)
        self.assertIn("Zincir uzun", " ".join(s4["yollar"][0]["uyarilar"]))
        s5 = yol.yollar(zincir(5), "t")
        self.assertEqual((s5["yollar"], s5["yok_nedeni"]), ([], yol.YOK_NEDENI))

    def test_ilk_adimlar_farkli_yollar_one(self):
        v = VERI([K("a", "Ayşe", 3, 100), K("d", "Deniz", 1, 100), K("b", "Bora"), K("e", "Ece"), K("t", "Tolga")],
                 [R("a", "b", "arkadas"), R("b", "t", "arkadas"), R("a", "e", "arkadas"), R("e", "t", "arkadas"), R("d", "t", "arkadas")])
        s = yol.yollar(v, "t", k=3)["yollar"]
        self.assertEqual([y["ilk_adim"]["id"] for y in s], ["a", "d", "a"])   # ikinci "a" yolu sona itildi
        self.assertEqual(idler(s[0]), [BEN, "a", "b", "t"])                    # eşit skorda sıra id ile deterministik
        self.assertEqual(len({tuple(idler(y)) for y in s}), 3)

    def test_cok_zayif_farkli_ilk_adim_one_gecmez(self):
        v = VERI([K("a", "Ayşe", 3, 100), K("b", "Bora"), K("e", "Ece"), K("z", "Zeki", 1, 0), K("t", "Tolga")],
                 [R("a", "b", "arkadas"), R("b", "t", "arkadas"), R("a", "e", "arkadas"), R("e", "t", "arkadas"), R("z", "t", "tanisiyor")])
        s = yol.yollar(v, "t", k=3)["yollar"]
        self.assertEqual([y["ilk_adim"]["id"] for y in s], ["a", "a", "z"])   # z skoru en iyinin yarısından düşük: sıra skora göre
        self.assertGreaterEqual(s[0]["skor"], s[1]["skor"])

    def test_k_siniri(self):
        v = self.veri
        self.assertEqual(len(yol.yollar(v, "selin-hoca", k=1)["yollar"]), 1)
        self.assertEqual(len(yol.yollar(v, "selin-hoca", k=99)["yollar"]), 2)
        self.assertEqual(len(yol.yollar(v, "selin-hoca", k=0)["yollar"]), 1)
        self.assertEqual(len(yol.yollar(v, "selin-hoca", k="x")["yollar"]), 2)   # geçersiz k varsayılan 3

    def test_yollar_basit_ve_dongusuz(self):
        # üçgen ve çevrim: hiçbir yolda aynı kişi iki kez geçmez
        v = VERI([K("a", "Ayşe", 3, 100), K("b", "Bora", 2, 80), K("e", "Ece", 2, 70), K("t", "Tolga")],
                 [R("a", "b", "arkadas"), R("b", "e", "arkadas"), R("e", "a", "arkadas"), R("e", "t", "arkadas"), R("b", "t", "tanisiyor")])
        for y in yol.yollar(v, "t", k=5)["yollar"]:
            self.assertEqual(len(idler(y)), len(set(idler(y))))
            self.assertEqual(idler(y)[0], BEN)
            self.assertEqual(idler(y)[-1], "t")


class Engeller(unittest.TestCase):
    def test_rakip_cift_yan_yana_olamaz(self):
        # a ─ t arkadaş ama aynı zamanda rakip: bu kenar yok; yol c üzerinden gider
        v = VERI([K("a", "Ayşe", 3, 100), K("cem", "Cem", 2, 60), K("t", "Tolga")],
                 [R("a", "t", "arkadas"), R("a", "t", "rakip"), R("cem", "t", "tanisiyor")])
        s = yol.yollar(v, "t", k=5)["yollar"]
        self.assertEqual([idler(y) for y in s], [[BEN, "cem", "t"]])

    def test_rakip_satiri_tek_basina_kenar_degil(self):
        v = VERI([K("a", "Ayşe", 3, 100), K("t", "Tolga")], [R("a", "t", "rakip")])
        s = yol.yollar(v, "t")
        self.assertEqual((s["yollar"], s["yok_nedeni"]), ([], yol.YOK_NEDENI))

    def test_gerginlik_de_engeller_ve_yol_uzar(self):
        v = VERI([K("a", "Ayşe", 3, 100), K("b", "Bora", 2, 80), K("t", "Tolga")],
                 [R("a", "t", "arkadas"), R("a", "t", "gerginlik"), R("a", "b", "arkadas"), R("b", "t", "arkadas")])
        for y in yol.yollar(v, "t", k=5)["yollar"]:
            ids = idler(y)
            self.assertFalse("a" in ids and ids[ids.index("a") + 1:ids.index("a") + 2] == ["t"])
        self.assertEqual(idler(yol.yollar(v, "t")["yollar"][0]), [BEN, "b", "t"])

    def test_merkez_ile_gerginlik_kisi_ilk_adim_olmaz(self):
        v = VERI([K("a", "Ayşe", 3, 100), K("b", "Bora", 2, 60), K("t", "Tolga")],
                 [R(BEN, "a", "gerginlik"), R("a", "t", "arkadas"), R("b", "t", "arkadas")])
        s = yol.yollar(v, "t", k=5)["yollar"]
        self.assertEqual([y["ilk_adim"]["id"] for y in s], ["b"])

    def test_gerginlik_olsa_da_dogrudan_bag_gercektir(self):
        v = VERI([K("a", "Ayşe", 3, 100)], [R(BEN, "a", "gerginlik")])
        s = yol.yollar(v, "a")
        self.assertTrue(s["dogrudan"])
        self.assertEqual(idler(s["yollar"][0]), [BEN, "a"])
        self.assertTrue(any("gerginlik" in u for u in s["yollar"][0]["uyarilar"]))   # c.dikkatler uyarısı yola taşınır

    def test_haric_kisi_dugum_olmaz(self):
        v = VERI([K("a", "Ayşe", 3, 100, haric=True), K("b", "Bora", 1, 50), K("t", "Tolga")],
                 [R("a", "t", "partner"), R("b", "t", "tanisiyor")])
        s = yol.yollar(v, "t", k=5)["yollar"]
        self.assertEqual([idler(y) for y in s], [[BEN, "b", "t"]])
        self.assertNotIn("Ayşe", json.dumps(yol.yollar(v, "t", k=5), ensure_ascii=False))

    def test_yalniz_haric_koprusu_olan_hedef_yok(self):
        v = VERI([K("a", "Ayşe", 3, 100, haric=True), K("t", "Tolga")], [R("a", "t", "arkadas")])
        s = yol.yollar(v, "t")
        self.assertEqual((s["yollar"], s["yok_nedeni"]), ([], yol.YOK_NEDENI))

    def test_haric_hedef_hata(self):
        v = VERI([K("h", "Hasan", 2, haric=True)])
        with self.assertRaises(ValueError) as e:
            yol.yollar(v, "h")
        self.assertEqual(str(e.exception), "Bu kişi hariç listende; öneri üretilmez.")

    def test_haric_ara_sonucunda_yok(self):
        v = VERI([K("h", "Hasan Şişecam", 2, haric=True, kurum="Şişecam"), K("o", "Orhan", 0, kurum="Şişecam"), K("a", "Ayşe", 3, 90)],
                 [R("a", "o", "arkadas"), R("a", "h", "arkadas")])
        s = yol.ara(v, "şişecam")
        self.assertEqual(s["tanidiklarin"], [])
        self.assertEqual([h["hedef"]["id"] for h in s["hedefler"]], ["o"])
        self.assertNotIn("Hasan", json.dumps(s, ensure_ascii=False))


class KenarDurumlari(unittest.TestCase):
    def test_hedef_yok(self):
        v = VERI([K("a", "Ayşe", 3)])
        for hedef in ("yok-kisi", "", None, "../x", "Ayşe Demir", 42):
            with self.assertRaises(ValueError) as e:
                yol.yollar(v, hedef)
            self.assertEqual(str(e.exception), "kişi bulunamadı")

    def test_hedef_merkez(self):
        with self.assertRaises(ValueError) as e:
            yol.yollar(VERI([K("a", "Ayşe", 3)]), BEN)
        self.assertIn("Bu sensin", str(e.exception))

    def test_bos_ag(self):
        with self.assertRaises(ValueError):
            yol.yollar({"kisiler": [], "iliskiler": []}, "a")
        with self.assertRaises(ValueError):
            yol.yollar({}, "a")

    def test_gecersiz_id_kisi_grafa_girmez(self):
        v = VERI([K("a", "Ayşe", 3, 100), K("Kotu Id", "Kötü", 3, 100), K("t", "Tolga")],
                 [R("a", "t", "arkadas"), R("Kotu Id", "t", "partner")])
        s = yol.yollar(v, "t", k=5)
        self.assertEqual([idler(y) for y in s["yollar"]], [[BEN, "a", "t"]])
        with self.assertRaises(ValueError):
            yol.yollar(v, "Kotu Id")

    def test_izole_hedef_ve_izole_merkez(self):
        v = VERI([K("a", "Ayşe", 3, 100), K("t", "Tolga")])
        self.assertEqual(yol.yollar(v, "t")["yok_nedeni"], yol.YOK_NEDENI)
        v = VERI([K("a", "Ayşe", 0), K("t", "Tolga")], [R("a", "t", "arkadas")])   # merkezin hiç bağı yok
        s = yol.yollar(v, "t")
        self.assertEqual((s["dogrudan"], s["yollar"], s["yok_nedeni"]), (False, [], yol.YOK_NEDENI))

    def test_dogrudan_durum(self):
        v = VERI([K("e", "Elif Demir", 2, 70, gun(10)), K("a", "Ayşe", 3, 100)], [R("e", "a", "arkadas")])
        s = yol.yollar(v, "e")
        self.assertTrue(s["dogrudan"])
        self.assertEqual(len(s["yollar"]), 1)
        (y,) = s["yollar"]
        self.assertEqual(idler(y), [BEN, "e"])
        self.assertEqual(y["ilk_adim"]["id"], "e")
        self.assertEqual(y["skor"], round(100 * 0.75 * (0.55 + 0.45 * 0.7)))
        self.assertTrue(y["taslak"].startswith("Selam Elif,"))
        self.assertNotIn("tanıştırabilir", y["taslak"])
        self.assertEqual(y["gerekce"], ["Elif ile yakınsın; son temas 10 gün önce."])

    def test_yakinlik_0_kisi_dogrudan_kenar_degil(self):
        # merkezle ilişki satırı olsa bile yakınlık 0 "tanımıyorum"dur; hedef olabilir ama bağ sayılmaz
        v = VERI([K("h", "Hatice Hoca", 0), K("a", "Ayşe", 3, 100)], [R("h", BEN, "hocasi")])
        s = yol.yollar(v, "h")
        self.assertFalse(s["dogrudan"])
        self.assertEqual(s["yollar"], [])
        v = VERI([K("a", "Ayşe", 0), K("b", "Bora", 3, 100), K("t", "Tolga")], [R("a", "t", "arkadas"), R("b", "a", "arkadas")])
        self.assertEqual([idler(y) for y in yol.yollar(v, "t", k=5)["yollar"]], [[BEN, "b", "a", "t"]])   # a yakınlık 0 ara kişi olabilir

    def test_coklu_bag_satiri_en_gucluyu_alir(self):
        for sira in (("tanisiyor", "arkadas"), ("arkadas", "tanisiyor")):
            v = VERI([K("a", "Ayşe", 3, 100), K("t", "Tolga")], [R("a", "t", sira[0]), R("t", "a", sira[1])])
            (y,) = yol.yollar(v, "t")["yollar"]
            self.assertEqual(y["kenarlar"][1]["tip"], "arkadas")
            self.assertEqual(y["kenarlar"][1]["guc"], 80)
            self.assertEqual(y["uyarilar"], [])   # tanışıyor uyarısı yok: kullanılan kenar arkadaş

    def test_merkezi_iceren_iliski_satiri_guclu_ise_gecer(self):
        v = VERI([K("h", "Selin Hoca", 1, None, gun(20)), K("t", "Tolga")], [R("h", BEN, "hocasi"), R("h", "t", "arkadas")])
        (y,) = yol.yollar(v, "t")["yollar"]
        k0 = y["kenarlar"][0]
        self.assertEqual((k0["tip"], k0["guc"], k0["a"], k0["b"]), ("hocasi", 65, BEN, "h"))
        self.assertEqual(y["gerekce"][0], "Selin Hoca senin hocan; son temas 20 gün önce.")
        self.assertEqual(y["skor"], round(100 * 0.65 * 0.8))
        # yakınlık kenarı daha güçlüyse o kalır
        v = VERI([K("h", "Selin Hoca", 3, 100), K("t", "Tolga")], [R(BEN, "h", "tanisiyor"), R("h", "t", "arkadas")])
        self.assertEqual(yol.yollar(v, "t")["yollar"][0]["kenarlar"][0]["tip"], "yakinlik")

    def test_sicaklik_none_ve_bozuk_alanlar(self):
        v = VERI([K("a", "Ayşe", "3", None, puan=None), K("b", "Bora", None, "x"), K("t", "Tolga", None, puan={"sicaklik": True})],
                 [R("a", "t", "arkadas"), {"a": "b", "b": "t"}, {"a": "a", "b": "a", "tip": "arkadas"}, R("a", "yok", "arkadas")], dikkatler=[])
        s = yol.yollar(v, "t")
        self.assertEqual([idler(y) for y in s["yollar"]], [[BEN, "a", "t"]])

    def test_merkez_satiri_yoksa_gerekce_temas_kaydi_yok(self):
        v = VERI([K("a", "Ayşe", 2, None), K("t", "Tolga")], [R("a", "t", "arkadas")])
        self.assertEqual(yol.yollar(v, "t")["yollar"][0]["gerekce"][0], "Ayşe ile yakınsın; temas kaydı yok.")

    def test_girdi_degismez_ve_deterministik(self):
        v = VERI([K("e", "Elif Demir", 3, 90, gun(5)), K("b", "Baran", 2, 40), K("m", "Mert", 1, 10), K("t", "Tolga Aksoy")],
                 [R("e", "t", "arkadas"), R("b", "t", "tanisiyor"), R("m", "t", "mentor"), R("e", "b", "akraba")])
        once = copy.deepcopy(v)
        a = json.dumps(yol.yollar(v, "t", k=5), ensure_ascii=False, sort_keys=True)
        self.assertEqual(v, once)
        self.assertEqual(a, json.dumps(yol.yollar(copy.deepcopy(v), "t", k=5), ensure_ascii=False, sort_keys=True))
        # satır sırası farklı olsa da aynı sonuç
        w = copy.deepcopy(v)
        w["iliskiler"].reverse()
        w["kisiler"][1:] = reversed(w["kisiler"][1:])
        self.assertEqual(a, json.dumps(yol.yollar(w, "t", k=5), ensure_ascii=False, sort_keys=True))

    def test_bugun_yoksa_uretildi_kullanilir(self):
        v = VERI([K("a", "Ayşe", 2, 50, "2026-10-12"), K("t", "Tolga")], [R("a", "t", "arkadas")])
        self.assertEqual(yol.yollar(v, "t")["yollar"][0]["gerekce"][0], "Ayşe ile yakınsın; son temas 3 gün önce.")
        self.assertEqual(yol.yollar(v, "t", bugun=date(2026, 10, 13))["yollar"][0]["gerekce"][0], "Ayşe ile yakınsın; son temas dün.")


class Metinler(unittest.TestCase):
    def yolda(self, tip, a, b, bag_ad="Baran Kaya", hedef_ad="Selin Hoca"):
        """BEN ─ baran ─ hedef; baran–hedef arası tek ilişki satırı (a, b yönüyle)."""
        v = VERI([K("baran", bag_ad, 3, 80, gun(3)), K("selin-hoca", hedef_ad)], [R(a, b, tip)])
        return yol.yollar(v, "selin-hoca")["yollar"][0]

    def test_yonlu_gerekceler(self):
        self.assertEqual(self.yolda("hocasi", "selin-hoca", "baran")["gerekce"][1], "Selin Hoca, Baran'ın hocası.")
        self.assertEqual(self.yolda("hocasi", "baran", "selin-hoca")["gerekce"][1], "Baran, Selin Hoca'nın hocası.")
        self.assertEqual(self.yolda("mentor", "selin-hoca", "baran")["gerekce"][1], "Selin Hoca, Baran'ın mentoru.")
        self.assertEqual(self.yolda("yonetici", "baran", "selin-hoca")["gerekce"][1], "Baran, Selin Hoca'nın yöneticisi.")
        self.assertEqual(self.yolda("asistan", "baran", "selin-hoca")["gerekce"][1], "Baran, Selin Hoca'nın asistanı.")
        self.assertEqual(self.yolda("asistan", "selin-hoca", "baran")["gerekce"][1], "Selin Hoca, Baran'ın asistanı.")

    def test_yon_alani(self):
        k = self.yolda("hocasi", "selin-hoca", "baran")["kenarlar"][1]   # yol baran → selin-hoca, satır selin-hoca → baran
        self.assertEqual((k["yonlu"], k["ters"], k["etiket"]), (True, True, "Hocası"))
        k = self.yolda("hocasi", "baran", "selin-hoca")["kenarlar"][1]
        self.assertEqual((k["yonlu"], k["ters"]), (True, False))
        k = self.yolda("arkadas", "baran", "selin-hoca")["kenarlar"][1]
        self.assertEqual((k["yonlu"], k["ters"], k["etiket"]), (False, False, "Arkadaş"))

    def test_simetrik_gerekceler(self):
        self.assertEqual(self.yolda("birlikte-calisiyor", "baran", "selin-hoca")["gerekce"][1], "Baran ve Selin Hoca birlikte çalışıyor.")
        self.assertEqual(self.yolda("arkadas", "baran", "selin-hoca")["gerekce"][1], "Baran ve Selin Hoca arkadaş.")
        self.assertEqual(self.yolda("is-ortagi", "baran", "selin-hoca")["gerekce"][1], "Baran ve Selin Hoca iş ortağı.")
        self.assertEqual(self.yolda("akraba", "baran", "selin-hoca")["gerekce"][1], "Baran ve Selin Hoca akraba.")
        self.assertEqual(self.yolda("tanisiyor", "baran", "selin-hoca")["gerekce"][1], "Baran ile Selin Hoca tanışıyor.")

    def test_merkez_yonlu_gerekce(self):
        def g(tip, a, b):
            v = VERI([K("h", "Selin Hoca", 1, None, gun(2)), K("t", "Tolga")], [R(a, b, tip), R("h", "t", "arkadas")])
            return yol.yollar(v, "t")["yollar"][0]["gerekce"][0]
        self.assertEqual(g("mentor", "h", BEN), "Selin Hoca senin mentorun; son temas 2 gün önce.")
        self.assertEqual(g("yonetici", BEN, "h"), "Selin Hoca'nın yöneticisisin; son temas 2 gün önce.")
        self.assertEqual(g("asistan", "h", BEN), "Selin Hoca senin asistanın; son temas 2 gün önce.")
        self.assertEqual(g("hocasi", BEN, "h"), "Selin Hoca'nın hocasısın; son temas 2 gün önce.")
        self.assertEqual(g("arkadas", BEN, "h"), "Selin Hoca senin arkadaşın; son temas 2 gün önce.")

    def test_gerekce_ilk_ad_ve_unvan(self):
        g = self.yolda("arkadas", "baran", "selin-hoca", bag_ad="Dr. Ayşe Yılmaz", hedef_ad="Mehmet Ali Kaya")["gerekce"]
        self.assertEqual(g[0], "Dr. Ayşe Yılmaz ile çok yakınsın; son temas 3 gün önce.")
        self.assertEqual(g[1], "Dr. Ayşe Yılmaz ve Mehmet arkadaş.")

    def test_son_temas_ifadeleri(self):
        def g(n):
            v = VERI([K("a", "Ayşe", 2, 50, gun(n) if n is not None else ""), K("t", "Tolga")], [R("a", "t", "arkadas")])
            return yol.yollar(v, "t")["yollar"][0]["gerekce"][0]
        self.assertEqual(g(0), "Ayşe ile yakınsın; son temas bugün.")
        self.assertEqual(g(1), "Ayşe ile yakınsın; son temas dün.")
        self.assertEqual(g(45), "Ayşe ile yakınsın; son temas 45 gün önce.")
        self.assertEqual(g(90), "Ayşe ile yakınsın; son temas yaklaşık 3 ay önce.")
        self.assertEqual(g(800), "Ayşe ile yakınsın; son temas 2 yıl önce.")
        self.assertEqual(g(None), "Ayşe ile yakınsın; temas kaydı yok.")

    def test_turkce_ek(self):
        self.assertEqual(yol._ek("Baran", "ilgi"), "Baran'ın")
        self.assertEqual(yol._ek("Elif", "ilgi"), "Elif'in")
        self.assertEqual(yol._ek("Umut", "ilgi"), "Umut'un")
        self.assertEqual(yol._ek("Özgür", "ilgi"), "Özgür'ün")
        self.assertEqual(yol._ek("Ayşe", "ilgi"), "Ayşe'nin")
        self.assertEqual(yol._ek("Selin Hoca", "ilgi"), "Selin Hoca'nın")
        self.assertEqual(yol._ek("Ayşe", "yonelme"), "Ayşe'ye")
        self.assertEqual(yol._ek("Mert", "yonelme"), "Mert'e")
        self.assertEqual(yol._ek("Baran", "yonelme"), "Baran'a")
        self.assertEqual(yol._ek("Elif", "belirtme"), "Elif'i")
        self.assertEqual(yol._ek("Deniz", "belirtme"), "Deniz'i")
        self.assertEqual(yol._ek("Ali", "belirtme"), "Ali'yi")
        self.assertEqual(yol._ek("Mert", "ayrilma"), "Mert'ten")
        self.assertEqual(yol._ek("Baran", "ayrilma"), "Baran'dan")
        self.assertEqual(yol._ek("", "ilgi"), "")

    def test_kisa_ad(self):
        self.assertEqual(yol._kisa("Ayşe Yılmaz"), "Ayşe")
        self.assertEqual(yol._kisa("Mehmet Ali Kaya"), "Mehmet")
        self.assertEqual(yol._kisa("Selin Hoca"), "Selin Hoca")
        self.assertEqual(yol._kisa("Prof. Dr. Ali Veli"), "Prof. Dr. Ali Veli")
        self.assertEqual(yol._kisa("Doç. Ece Su"), "Doç. Ece Su")
        self.assertEqual(yol._kisa("  Deniz\nDemo "), "Deniz")
        self.assertEqual(yol._kisa("", "kid"), "kid")

    def test_uyari_soguk_ilk_adim(self):
        v = VERI([K("e", "Elif Demir", 3, 5, gun(90)), K("t", "Tolga")], [R("e", "t", "arkadas")])
        (y,) = yol.yollar(v, "t")["yollar"]
        self.assertEqual(y["uyarilar"], ["Elif ile 90 gündür konuşmadın; tanıştırma istemeden önce bağı ısıt."])
        v = VERI([K("e", "Elif Demir", 3, 5, gun(89)), K("t", "Tolga")], [R("e", "t", "arkadas")])
        self.assertEqual(yol.yollar(v, "t")["yollar"][0]["uyarilar"], [])
        v = VERI([K("e", "Elif Demir", 3, 5, gun(400)), K("t", "Tolga")], [R("e", "t", "arkadas")])
        self.assertIn("13 aydır konuşmadın", yol.yollar(v, "t")["yollar"][0]["uyarilar"][0])

    def test_uyari_tanisiyor_zayif(self):
        v = VERI([K("baran", "Baran Kaya", 3, 80, gun(3)), K("selin", "Selin Hoca")], [R("baran", "selin", "tanisiyor")])
        (y,) = yol.yollar(v, "selin")["yollar"]
        self.assertEqual(y["uyarilar"], ["Baran ile Selin Hoca yalnız tanışıyor; tanıştırma zayıf kalabilir."])
        # ilk halka (merkez–kişi) yakınlıktır; "tanışıyor" uyarısı yalnız kişi–kişi kenarında
        v = VERI([K("baran", "Baran Kaya", 3, 80, gun(3)), K("selin", "Selin Hoca")], [R("baran", "selin", "arkadas")])
        self.assertEqual(yol.yollar(v, "selin")["yollar"][0]["uyarilar"], [])

    def test_uyari_yalniz_yoldaki_kisilerin_dikkati(self):
        dik = [{"kisiler": ["baran"], "seviye": "orta", "metin": "Baran için bir not."},
               {"kisiler": ["selin"], "seviye": "yuksek", "metin": "Selin için yüksek not."},
               {"kisiler": ["baran", "selin"], "seviye": "orta", "metin": "Baran – Selin: orta not."},
               {"kisiler": ["baran", "digeri"], "seviye": "orta", "metin": "Baran – Diğeri: yoldaki herkes değil."},
               {"kisiler": ["digeri"], "seviye": "yuksek", "metin": "Alakasız."},
               {"kisiler": ["baran", "selin"], "seviye": "dusuk", "metin": "Düşük seviye: referans bağımsız sayılmaz."},
               {"kisiler": [], "seviye": "yuksek", "metin": "Kişisiz."}]
        v = VERI([K("baran", "Baran Kaya", 3, 80, gun(3)), K("selin", "Selin Hoca"), K("digeri", "Diğeri", 2)], [R("baran", "selin", "arkadas")], dikkatler=dik)
        (y,) = yol.yollar(v, "selin")["yollar"]
        self.assertEqual(y["uyarilar"], ["Baran için bir not.", "Selin için yüksek not.", "Baran – Selin: orta not."])

    def test_uyari_gercek_dikkatler_ile(self):
        # c.dikkatler: Sen ile hedef arasında gerginlik → yüksek seviye uyarı hedef yolunda görünür; alakasız kişinin uyarısı görünmez
        v = VERI([K("a", "Ayşe", 3, 90, gun(2)), K("t", "Tolga"), K("z", "Zeynep", 2), K("y", "Yılmaz", 2)],
                 [R("a", "t", "arkadas"), R(BEN, "t", "gerginlik"), R(BEN, "z", "rakip")])
        (y,) = yol.yollar(v, "t")["yollar"]
        self.assertEqual(len(y["uyarilar"]), 2)   # Sen–Tolga gerginliği ve Ayşe–Tolga–Sen üçgeni; ikisi de yoldaki kişileri anlatır
        self.assertIn("Tolga ile aranda: gerginlik", y["uyarilar"][0])
        self.assertIn("Ayşe – Tolga", y["uyarilar"][1])
        self.assertNotIn("Zeynep", " ".join(y["uyarilar"]))

    def test_taslak_iki_kisilik_yol(self):
        v = VERI([K("elif", "Elif Demir", 3, 90, gun(2)), K("selin", "Selin Hoca")], [R("elif", "selin", "arkadas")])
        (y,) = yol.yollar(v, "selin")["yollar"]
        self.assertEqual(y["taslak"], "Selam Elif, nasılsın? Bir ricam olacak: Selin Hoca ile tanışmak istiyorum. Sen onu tanıyorsun diye düşündüm; "
                                      "uygun görürsen bizi tanıştırabilir misin? İstersen kısa bir tanıtım metni de hazırlayayım.")
        self.assertEqual(yol.taslak(y, v), y["taslak"])

    def test_taslak_uzun_yol(self):
        v = VERI([K("elif", "Elif Demir", 3, 90, gun(2)), K("baran", "Baran Kaya"), K("selin", "Selin Hoca")],
                 [R("elif", "baran", "arkadas"), R("baran", "selin", "hocasi")])
        (y,) = yol.yollar(v, "selin")["yollar"]
        t = y["taslak"]
        self.assertTrue(t.startswith("Selam Elif, nasılsın?"))
        self.assertIn("Selin Hoca ile tanışmak istiyorum", t)
        self.assertIn("Baran üzerinden ulaşmaya çalışıyorum", t)
        self.assertIn("beni tanıştırabilir misin", t)
        self.assertNotIn("Demir", t)
        self.assertNotIn("Kaya", t)

    def test_taslak_amac(self):
        v = VERI([K("elif", "Elif Demir", 3, 90, gun(2)), K("selin", "Selin Hoca")], [R("elif", "selin", "arkadas")])
        (y,) = yol.yollar(v, "selin", amac="  açık veri\nçağrısı hakkında konuşmak. ")["yollar"]
        self.assertIn("Selin Hoca ile tanışmak istiyorum. Konu: açık veri çağrısı hakkında konuşmak. Sen onu", y["taslak"])
        self.assertNotIn("\n", y["taslak"])
        # taslak() başka bir amaçla yeniden üretir; boş amaç doğal kalır
        self.assertNotIn("Konu:", yol.taslak(y, v))
        self.assertIn("Konu: yeni proje.", yol.taslak(y, v, amac="yeni proje"))
        uzun = yol.yollar(v, "selin", amac="x" * 500)["yollar"][0]["taslak"]
        self.assertLess(len(uzun), 600)

    def test_taslak_unvan_korunur(self):
        v = VERI([K("a", "Dr. Ayşe Yılmaz", 3, 90, gun(2)), K("t", "Prof. Dr. Ali Veli")], [R("a", "t", "arkadas")])
        t = yol.yollar(v, "t")["yollar"][0]["taslak"]
        self.assertTrue(t.startswith("Merhaba Dr. Ayşe Yılmaz, nasılsınız?"))      # unvanlı ad -> siz
        self.assertIn("Prof. Dr. Ali Veli ile tanışmak istiyorum", t)

    def test_hitap_kurali(self):
        self.assertEqual(yol._hitap({"tur": "akademi", "ad": "Ayşe Kara"}), "siz")
        self.assertEqual(yol._hitap({"tur": "cevre", "ad": "Selin Hoca"}), "siz")
        self.assertEqual(yol._hitap({"tur": "cevre", "ad": "Doç. Ece Su"}), "siz")
        self.assertEqual(yol._hitap({"tur": "cevre", "ad": "Prof. Ali"}), "siz")
        self.assertEqual(yol._hitap({"tur": "cevre", "ad": "Dr. Ali"}), "siz")
        self.assertEqual(yol._hitap({"tur": "siyaset", "ad": "Ali Kaya", "yakinlik": 1}), "siz")
        self.assertEqual(yol._hitap({"tur": "is", "ad": "Ali Kaya", "yakinlik": 0}), "siz")
        self.assertEqual(yol._hitap({"tur": "is", "ad": "Ali Kaya", "yakinlik": 2}), "sen")
        self.assertEqual(yol._hitap({"tur": "siyaset", "ad": "Ali Kaya", "yakinlik": 3}), "sen")
        self.assertEqual(yol._hitap({"tur": "yakin", "ad": "Ali Kaya", "yakinlik": 1}), "sen")
        self.assertEqual(yol._hitap({"tur": "cevre", "ad": "Ali Kaya", "yakinlik": 0}), "sen")
        self.assertEqual(yol._hitap({}), "sen")
        self.assertEqual(yol._hitap(None), "sen")

    def test_taslak_siz_hocam_iki_kisilik(self):
        v = VERI([K("selin", "Selin Hoca", 3, 90, gun(2), tur="akademi"), K("t", "Tolga Aksoy")], [R("selin", "t", "mentor")])
        t = yol.yollar(v, "t")["yollar"][0]["taslak"]
        self.assertEqual(t, "Merhaba Selin Hocam, nasılsınız? Bir ricam olacak: Tolga ile tanışmak istiyorum. Siz onu tanıyorsunuz diye düşündüm; "
                            "uygun görürseniz bizi tanıştırabilir misiniz? İsterseniz kısa bir tanıtım metni de hazırlayayım.")
        self.assertNotIn("nasılsın?", t)

    def test_taslak_hocam_yalniz_hitapta(self):
        # hedef "Selin Hoca" üçüncü kişi olarak anılırken "Hoca" kalır; ilk adım (akademi) siz ile karşılanır
        v = VERI([K("elif", "Elif Demir", 3, 90, gun(2), tur="akademi"), K("selin", "Selin Hoca")], [R("elif", "selin", "arkadas")])
        t = yol.yollar(v, "selin")["yollar"][0]["taslak"]
        self.assertTrue(t.startswith("Merhaba Elif, nasılsınız?"))
        self.assertIn("Selin Hoca ile tanışmak istiyorum", t)
        self.assertNotIn("Hocam", t)

    def test_taslak_siz_uzun_yol(self):
        v = VERI([K("hoca", "Selin Hoca", 3, 90, gun(2)), K("baran", "Baran Kaya"), K("t", "Tolga")],
                 [R("hoca", "baran", "arkadas"), R("baran", "t", "arkadas")])
        t = yol.yollar(v, "t")["yollar"][0]["taslak"]
        self.assertTrue(t.startswith("Merhaba Selin Hocam, nasılsınız?"))
        self.assertIn("Baran üzerinden ulaşmaya çalışıyorum; siz Baran ile tanışıyorsunuz diye düşündüm, uygun görürseniz beni tanıştırabilir misiniz?", t)
        self.assertIn("İsterseniz", t)

    def test_taslak_sen_siz_ayrimi(self):
        def t(**ek):
            v = VERI([K("a", "Ayşe Yılmaz", 3, 90, gun(2), **ek), K("t", "Tolga")], [R("a", "t", "arkadas")])
            return yol.yollar(v, "t")["yollar"][0]["taslak"]
        self.assertTrue(t(tur="cevre").startswith("Selam Ayşe, nasılsın?"))
        self.assertTrue(t(tur="yakin").startswith("Selam Ayşe, nasılsın?"))
        self.assertTrue(t(tur="is").startswith("Selam Ayşe, nasılsın?"))           # yakınlık 3: sen
        self.assertTrue(t(tur="akademi").startswith("Merhaba Ayşe, nasılsınız?"))
        # siyaset/iş + yakınlık ≤ 1 -> siz (bağ yakınlık 1 kişi üzerinden)
        v = VERI([K("a", "Ayşe Yılmaz", 1, 90, gun(2), tur="siyaset"), K("t", "Tolga")], [R("a", "t", "arkadas")])
        self.assertTrue(yol.yollar(v, "t")["yollar"][0]["taslak"].startswith("Merhaba Ayşe, nasılsınız?"))
        v = VERI([K("a", "Ayşe Yılmaz", 2, 90, gun(2), tur="is"), K("t", "Tolga")], [R("a", "t", "arkadas")])
        self.assertTrue(yol.yollar(v, "t")["yollar"][0]["taslak"].startswith("Selam Ayşe, nasılsın?"))

    def test_taslak_hitap_ilk_adima_gore_hedefe_degil(self):
        # hedef akademik/Hoca olsa da mesajı alan ilk adım yakın arkadaşsa "sen" kalır
        v = VERI([K("a", "Ayşe Yılmaz", 3, 90, gun(2)), K("t", "Selin Hoca", tur="akademi")], [R("a", "t", "arkadas")])
        self.assertTrue(yol.yollar(v, "t")["yollar"][0]["taslak"].startswith("Selam Ayşe, nasılsın?"))

    def test_taslak_dogrudan_siz(self):
        v = VERI([K("s", "Selin Hoca", 2, 10, gun(200), tur="akademi")])
        t = yol.yollar(v, "s")["yollar"][0]["taslak"]
        self.assertEqual(t, "Merhaba Selin Hocam, nasılsınız? Uzun zamandır konuşmadık; müsait olduğunuzda kısa bir görüşme yapabilir miyiz?")
        v = VERI([K("s", "Selin Hoca", 2, 10, gun(5), tur="akademi")])
        t = yol.yollar(v, "s", amac="staj")["yollar"][0]["taslak"]
        self.assertEqual(t, "Merhaba Selin Hocam, nasılsınız? Size bir şey danışmak istiyordum; sizinle şu konuda konuşmak isterim: staj. "
                            "Müsait olduğunuzda kısa bir görüşme yapabilir miyiz?")
        v = VERI([K("m", "Mehmet Kaya", 1, 10, gun(5), tur="siyaset")])
        self.assertTrue(yol.yollar(v, "m")["yollar"][0]["taslak"].startswith("Merhaba Mehmet, nasılsınız?"))

    def test_taslak_fonksiyonu_hitabi_korur(self):
        v = VERI([K("selin", "Selin Hoca", 3, 90, gun(2), tur="akademi"), K("t", "Tolga Aksoy")], [R("selin", "t", "mentor")])
        y = yol.yollar(v, "t")["yollar"][0]
        self.assertEqual(yol.taslak(y, v), y["taslak"])
        self.assertIn("Konu: proje.", yol.taslak(y, v, amac="proje"))
        self.assertTrue(yol.taslak(y, v, amac="proje").startswith("Merhaba Selin Hocam"))

    def test_taslak_dogrudan(self):
        v = VERI([K("e", "Elif Demir", 2, 10, gun(200))])
        t = yol.yollar(v, "e")["yollar"][0]["taslak"]
        self.assertEqual(t, "Selam Elif, nasılsın? Uzun zamandır konuşmadık; müsait olduğunda kısa bir sohbet edebilir miyiz?")
        v = VERI([K("e", "Elif Demir", 2, 10, gun(5))])
        t = yol.yollar(v, "e", amac="staj")["yollar"][0]["taslak"]
        self.assertEqual(t, "Selam Elif, nasılsın? Sana bir şey danışmak istiyordum; seninle şu konuda konuşmak isterim: staj. Müsait olduğunda kısa bir sohbet edebilir miyiz?")
        uy = yol.yollar(VERI([K("e", "Elif Demir", 2, 10, gun(200))]), "e")["yollar"][0]["uyarilar"]
        self.assertEqual(uy, ["Elif ile 7 aydır konuşmadın; yeniden bir temas kur."])

    def test_taslak_hata(self):
        with self.assertRaises(ValueError):
            yol.taslak({"dugumler": [{"id": BEN}]}, VERI([]))
        with self.assertRaises(ValueError):
            yol.taslak({}, VERI([]))


class AramaTesti(unittest.TestCase):
    def setUp(self):
        self.veri = VERI([
            K("a", "Ayşe Yılmaz", 3, 90, gun(2), kurum="Koç Holding"),
            K("e", "Emre Şahin", 2, 40, gun(30), kurum="Şişecam", rol="Finans Müdürü"),
            K("o", "Orhan Çelik", 0, kurum="Şişecam", rol="Genel Müdür", alan=["finans"]),
            K("p", "Pınar Ak", 0, kurum="Enerjisa", alan=["Yapay Zekâ"], etiketler=["veri-bilimi", "makine-ogrenmesi"]),
            K("r", "Rana Su", 0, kurum="Şişecam", rol="Satın Alma"),
            K("u", "Uzak Kişi", 0, kurum="Şişecam", rol="Danışman"),
            K("h", "Hakan Gizli", 1, haric=True, kurum="Şişecam"),
        ], [R("a", "o", "arkadas"), R("e", "r", "arkadas"), R("a", "p", "birlikte-calisiyor"), R("a", "e", "tanisiyor")])

    def test_gruplar(self):
        s = self.veri
        r = yol.ara(s, "Şişecam")
        self.assertEqual(r["sorgu"], "Şişecam")
        self.assertEqual([t["id"] for t in r["tanidiklarin"]], ["e"])
        self.assertEqual(r["tanidiklarin"][0], {"id": "e", "ad": "Emre Şahin", "kurum": "Şişecam", "rol": "Finans Müdürü", "yakinlik": 2, "sicaklik": 40})
        self.assertEqual([h["hedef"]["id"] for h in r["hedefler"]], ["o", "r", "u"])      # skora göre; yolu olmayan "u" sonda
        self.assertEqual([h["skor"] > 0 for h in r["hedefler"]], [True, True, False])
        self.assertIsNone(r["hedefler"][2]["en_iyi"])
        self.assertEqual(r["hedefler"][2]["yok_nedeni"], yol.YOK_NEDENI)
        self.assertGreaterEqual(r["hedefler"][0]["skor"], r["hedefler"][1]["skor"])
        h0 = r["hedefler"][0]
        self.assertEqual(h0["en_iyi"]["skor"], h0["skor"])
        self.assertEqual(idler(h0["en_iyi"]), [BEN, "a", "o"])
        self.assertEqual(h0["hedef"], {"id": "o", "ad": "Orhan Çelik", "tur": "cevre", "kurum": "Şişecam", "rol": "Genel Müdür"})

    def test_turkce_karakter_duyarsiz(self):
        for q in ("SISECAM", "şişecam", "Sisecam", "ŞİŞECAM", " sisecam  "):
            self.assertEqual([h["hedef"]["id"] for h in yol.ara(self.veri, q)["hedefler"]][:2], ["o", "r"], q)

    def test_alanlar_ve_jetonlar(self):
        self.assertEqual([h["hedef"]["id"] for h in yol.ara(self.veri, "yapay zeka")["hedefler"]], ["p"])        # alan, â → a
        self.assertEqual([h["hedef"]["id"] for h in yol.ara(self.veri, "veri bilimi")["hedefler"]], ["p"])       # tireli etiket
        self.assertEqual([h["hedef"]["id"] for h in yol.ara(self.veri, "finans")["hedefler"]], ["o"])           # alan; e ise tanıdık
        self.assertEqual([t["id"] for t in yol.ara(self.veri, "finans")["tanidiklarin"]], ["e"])               # rol
        self.assertEqual([h["hedef"]["id"] for h in yol.ara(self.veri, "orhan")["hedefler"]], ["o"])            # ad
        self.assertEqual([h["hedef"]["id"] for h in yol.ara(self.veri, "müdür şişecam")["hedefler"]], ["o"])    # tüm jetonlar eşleşmeli
        self.assertEqual([h["hedef"]["id"] for h in yol.ara(self.veri, "fin")["hedefler"]], ["o"])              # 3+ harf önek
        self.assertEqual(yol.ara(self.veri, "zzz")["hedefler"], [])
        self.assertEqual(yol.ara(self.veri, "zzz")["tanidiklarin"], [])

    def test_kisa_jeton_tam_eslesir(self):
        v = VERI([K("a", "Ayşe", 3, 90), K("x", "Xavier", 0, alan=["AI"]), K("y", "Yaren", 0, alan=["Aile hukuku"])], [R("a", "x", "arkadas"), R("a", "y", "arkadas")])
        self.assertEqual([h["hedef"]["id"] for h in yol.ara(v, "ai")["hedefler"]], ["x"])

    def test_hedef_siniri_8_ve_skora_gore(self):
        kisiler = [K("a", "Ayşe", 3, 100), K("z", "Zeki", 1, 10)]
        rel = []
        for i in range(12):
            kisiler.append(K(f"f{i:02d}", f"Finans {i:02d}", 0, kurum="Banka"))
            rel.append(R("a" if i % 2 == 0 else "z", f"f{i:02d}", "arkadas" if i % 3 else "tanisiyor"))
        r = yol.ara(VERI(kisiler, rel), "banka")
        self.assertEqual(len(r["hedefler"]), 8)
        skorlar = [h["skor"] for h in r["hedefler"]]
        self.assertEqual(skorlar, sorted(skorlar, reverse=True))
        self.assertTrue(all(h["en_iyi"] for h in r["hedefler"]))

    def test_tanidik_sirasi(self):
        v = VERI([K("a", "Ayşe", 1, 90, kurum="X"), K("b", "Bora", 3, 20, kurum="X"), K("c", "Cem", 3, 80, kurum="X"), K("d", "Dilek", 3, None, kurum="X")])
        self.assertEqual([t["id"] for t in yol.ara(v, "x")["tanidiklarin"]], ["c", "b", "d", "a"])
        self.assertIsNone(yol.ara(v, "x")["tanidiklarin"][2]["sicaklik"])

    def test_sorgu_dogrulama(self):
        for kotu in ("", "   ", "\n\t", "!!!", "?", None, 42, ["a"], "x" * 81):
            with self.assertRaises(ValueError, msg=repr(kotu)):
                yol.ara(self.veri, kotu)
        self.assertEqual(yol.ara(self.veri, "yapay\n zeka\t ")["sorgu"], "yapay zeka")     # tek satıra indirgenir
        self.assertEqual(yol.ara(self.veri, "a" * 80)["sorgu"], "a" * 80)
        self.assertEqual(yol.ara(self.veri, "x" * 40 + "\n" * 50 + "y" * 39)["sorgu"], "x" * 40 + " " + "y" * 39)   # indirgeme sonrası uzunluk sayılır
        with self.assertRaises(ValueError) as e:
            yol.ara(self.veri, "x" * 81)
        self.assertIn("80", str(e.exception))

    def test_merkez_ve_girdi_korunur(self):
        once = copy.deepcopy(self.veri)
        r = yol.ara(self.veri, "umut")
        self.assertEqual((r["tanidiklarin"], r["hedefler"]), ([], []))    # merkez aranamaz
        yol.ara(self.veri, "şişecam")
        self.assertEqual(self.veri, once)


class Performans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rnd = random.Random(7)
        n = 1000
        kisiler = [K(f"k{i:04d}", f"Kişi {i}", rnd.choice((0, 0, 0, 1, 1, 2, 3)), rnd.choice((None, rnd.randint(0, 100))),
                     gun(rnd.randint(0, 200)), kurum=rnd.choice(("Alfa", "Beta", "Gama", "Delta")), alan=[rnd.choice(("finans", "veri", "hukuk"))]) for i in range(n)]
        tipler = list(yol.AGIRLIK_TIP) * 3 + ["rakip", "gerginlik"]
        rel = []
        for _ in range(4000):
            a, b = rnd.sample(range(n), 2)
            rel.append(R(f"k{a:04d}", f"k{b:04d}", rnd.choice(tipler)))
        cls.veri = VERI(kisiler, rel, dikkatler=[])
        cls.hedefler = [k["id"] for k in kisiler if k["yakinlik"] == 0][:12]

    def en_iyi(self, f, tekrar=3):
        en = []
        for _ in range(tekrar):
            t = time.perf_counter()
            f()
            en.append(time.perf_counter() - t)
        return min(en)

    def test_yollar_200ms_altinda(self):
        for hedef in self.hedefler[:6]:
            sure = self.en_iyi(lambda: yol.yollar(self.veri, hedef))
            self.assertLess(sure, 0.2, f"{hedef}: {sure * 1000:.0f} ms")

    def test_buyuk_agda_sonuc_gecerli(self):
        bos = 0
        for hedef in self.hedefler:
            s = yol.yollar(self.veri, hedef, k=3)
            bos += not s["yollar"]
            for y in s["yollar"]:
                ids = idler(y)
                self.assertEqual((ids[0], ids[-1]), (BEN, hedef))
                self.assertEqual(len(ids), len(set(ids)))
                self.assertLessEqual(len(y["kenarlar"]), yol.AZAMI_KENAR)
                self.assertTrue(1 <= y["skor"] <= 100)
        self.assertLess(bos, len(self.hedefler))   # rastgele ağda çoğunun yolu var

    def test_ara_buyuk_agda_hizli(self):
        sure = self.en_iyi(lambda: yol.ara(self.veri, "finans"), tekrar=2)
        self.assertLess(sure, 1.0, f"{sure * 1000:.0f} ms")
        r = yol.ara(self.veri, "finans")
        self.assertLessEqual(len(r["hedefler"]), yol.HEDEF_AZAMI)


if __name__ == "__main__":
    unittest.main()
