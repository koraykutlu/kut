"""Haftalık özet (ag_ozet): seçim mantığı (saf `hazirla`), taslak metinleri, `olustur` idempotentliği, eski özet temizliği, `goruldu`.
Kurgusal adlar; geçici veri klasörü ve geçici ayar klasörü, gerçek veriye dokunulmaz."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_cekirdek as c  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_ozet as oz  # noqa: E402
import ag_soz as sz  # noqa: E402
import ag_sonuc as sn  # noqa: E402

BUGUN = date(2026, 10, 19)   # pazartesi, 2026-W43


def kisi(kid, ad, **ek):
    return {"id": kid, "ad": ad, "tur": "cevre", "yakinlik": 2, "haric": False, "govde": "", "sozler": [], "telefon": [], "eposta": "", **ek}


def veri(kisiler, bu_hafta, iliskiler=None, ben_ad="Umut"):
    merkez = {"id": "ben", "ad": ben_ad, "tur": "ben", "yakinlik": 3, "govde": ""}
    return {"kisiler": [merkez] + kisiler, "bu_hafta": bu_hafta, "iliskiler": iliskiler or [], "ben": {"ad": ben_ad}}


def ihmal(kid, gun=30, oncelik=0):
    return {"id": kid, "neden": f"{gun} gündür temas yok", "oncelik": oncelik}


def adim(kid, metin="Raporu gönder", g=0, oncelik=None):
    return {"id": kid, "neden": f"{metin} ({'bugün' if g == 0 else f'{g} gün kaldı'})", "oncelik": g if oncelik is None else oncelik}


def soz(kid, oncelik, sira=0, yon="ben"):
    return {"id": kid, "neden": f"verdiğin söz: x · y", "oncelik": oncelik, "tur": "soz", "yon": yon, "sira": sira}


def soz_kaydi(yon="ben", metin="kitabı göndermek", son="2026-10-17", sira=0):
    return {"durum": "acik", "tarih": "2026-10-01", "yon": yon, "metin": metin, "son": son, "kapanis": "", "sira": sira}


def kayit(no, kisi_id, sonuc, gun_once=0, kapanis_gun_once=None, kaynak="ozet", oneri="Selam yaz"):
    t = BUGUN - timedelta(days=gun_once)
    kap = "" if sonuc == "bekliyor" else (BUGUN - timedelta(days=gun_once if kapanis_gun_once is None else kapanis_gun_once)).isoformat()
    return {"no": no, "tarih": t.isoformat(), "kaynak": kaynak, "kisi": kisi_id, "oneri": oneri, "sonuc": sonuc, "not": "", "kapanis": kap}


def ids(maddeler):
    return [m["id"] for m in maddeler]


class HaftaTest(unittest.TestCase):
    def test_hafta_anahtari(self):
        self.assertEqual(oz.hafta_anahtari(BUGUN), "2026-W43")
        self.assertEqual(oz.hafta_anahtari(date(2026, 10, 25)), "2026-W43")    # pazar
        self.assertEqual(oz.hafta_anahtari(date(2026, 10, 26)), "2026-W44")
        self.assertEqual(oz.hafta_anahtari(date(2027, 1, 1)), "2026-W53")      # ISO yılı takvim yılından farklı olabilir
        self.assertEqual(oz.hafta_anahtari(date(2026, 1, 5)), "2026-W02")
        self.assertRegex(oz.hafta_anahtari(), r"^\d{4}-W\d{2}$")


class SecimTest(unittest.TestCase):
    def setUp(self):
        yama = mock.patch.object(oz, "_saat", return_value=9)   # selam saate duyarlı: sabah
        yama.start()
        self.addCleanup(yama.stop)

    def test_oncelik_sirasi_ve_en_cok_uc_kisi(self):
        kisiler = [kisi(f"k{i}", f"Kişi {i}") for i in range(1, 7)]
        bh = [ihmal("k1", 20, oncelik=9), ihmal("k2", 40, oncelik=-5), adim("k3", g=-2), ihmal("k4", 25, oncelik=3), adim("k5", g=2), ihmal("k6", 90, oncelik=-20)]
        o = oz.hazirla(veri(kisiler, bh), BUGUN, [])
        self.assertEqual(ids(o["maddeler"]), ["k6", "k2", "k3"])        # en acil üç
        self.assertEqual(o["sozler"], [])
        self.assertFalse(o["bos"])
        self.assertEqual((o["hafta"], o["tarih"]), ("2026-W43", "2026-10-19"))

    def test_madde_alanlari(self):
        o = oz.hazirla(veri([kisi("ayse-yilmaz", "Ayşe Yılmaz", tur="yakin", telefon=["0555"])], [ihmal("ayse-yilmaz")]), BUGUN, [])
        (m,) = o["maddeler"]
        self.assertEqual(set(m) >= {"id", "ad", "tur", "neden", "adim", "taslak", "kanal_onerisi", "no", "not"}, True)
        self.assertEqual((m["id"], m["ad"], m["tur"], m["neden"], m["no"], m["not"]), ("ayse-yilmaz", "Ayşe Yılmaz", "yakin", "30 gündür temas yok", None, ""))
        self.assertEqual(m["kanal_onerisi"], "mesaj")

    def test_haric_unknown_ve_merkez_dusur(self):
        kisiler = [kisi("a", "Ayşe"), kisi("h", "Hariç Kişi", haric=True)]
        bh = [ihmal("h", 90, oncelik=-30), ihmal("yok", 90, oncelik=-30), ihmal("ben", 90, oncelik=-30), ihmal("a")]
        bh += [soz("h", -3)]
        kisiler[1]["sozler"] = [soz_kaydi()]
        o = oz.hazirla(veri(kisiler, bh), BUGUN, [])
        self.assertEqual(ids(o["maddeler"]), ["a"])
        self.assertEqual(o["sozler"], [])
        self.assertNotIn("Hariç Kişi", json.dumps(o, ensure_ascii=False))

    def test_haric_kisi_sonuc_bekleyende_de_yok(self):
        kisiler = [kisi("a", "Ayşe"), kisi("h", "Hariç Kişi", haric=True)]
        k = [kayit(1, "a", "bekliyor", 4), kayit(2, "h", "bekliyor", 4), kayit(3, "yok", "bekliyor", 4)]
        o = oz.hazirla(veri(kisiler, []), BUGUN, k)
        self.assertEqual([r["kisi"] for r in o["sonuc_bekleyen"]], ["a"])

    def test_ayni_kisi_iki_kez_olmaz(self):
        o = oz.hazirla(veri([kisi("a", "Ayşe")], [ihmal("a", 30, 1), adim("a", g=-1)]), BUGUN, [])
        self.assertEqual(ids(o["maddeler"]), ["a"])

    def test_bekleme_suresi_dolmamis_kisi_dusar(self):
        kisiler = [kisi("a", "Ayşe"), kisi("b", "Mehmet")]
        bh = [ihmal("a", 40, oncelik=-10), ihmal("b", 20, oncelik=5)]
        k = [kayit(1, "a", "atlandi", 10), kayit(2, "a", "atlandi", 3)]       # 28 gün dinlenme: 25 gün kaldı
        self.assertEqual(ids(oz.hazirla(veri(kisiler, bh), BUGUN, k)["maddeler"]), ["b"])
        k_bitti = [kayit(1, "a", "atlandi", 40), kayit(2, "a", "atlandi", 30)]   # 30 gün önce kapandı: süre doldu
        self.assertEqual(ids(oz.hazirla(veri(kisiler, bh), BUGUN, k_bitti)["maddeler"]), ["a", "b"])

    def test_tek_ertelendi_bir_hafta_dusurur(self):
        kisiler = [kisi("a", "Ayşe")]
        o = oz.hazirla(veri(kisiler, [ihmal("a")]), BUGUN, [kayit(1, "a", "ertelendi", 2)])
        self.assertEqual(o["maddeler"], [])
        self.assertTrue(o["bos"])
        self.assertEqual(ids(oz.hazirla(veri(kisiler, [ihmal("a")]), BUGUN + timedelta(days=6), [kayit(1, "a", "ertelendi", 2)])["maddeler"]), ["a"])

    def test_carpan_yeniden_siralar(self):
        kisiler = [kisi("a", "Ayşe"), kisi("b", "Mehmet"), kisi("c", "Deniz")]
        bh = [ihmal("a", 40, oncelik=0), ihmal("b", 38, oncelik=2), ihmal("c", 36, oncelik=4)]
        temel = oz.hazirla(veri(kisiler, bh), BUGUN, [])
        self.assertEqual(ids(temel["maddeler"]), ["a", "b", "c"])
        kotu = [kayit(1, "a", "ise_yaramadi", 30), kayit(2, "a", "ise_yaramadi", 10)]   # a: çarpan 0,5 → sona
        o = oz.hazirla(veri(kisiler, bh), BUGUN, kotu)
        self.assertEqual(ids(o["maddeler"]), ["b", "c", "a"])
        self.assertIn("farklı bir yol dene", o["maddeler"][2]["not"])
        iyi = [kayit(1, "c", "ise_yaradi", 5)]                                         # c: çarpan 1,15 → öne
        o = oz.hazirla(veri(kisiler, bh), BUGUN, iyi)
        self.assertEqual(ids(o["maddeler"]), ["c", "a", "b"])
        self.assertEqual(o["maddeler"][0]["not"], "Son deneme işe yaradı; ritmi koru.")

    def test_carpan_gecikmis_adimda_da_dogru_yonde(self):
        kisiler = [kisi("a", "Ayşe"), kisi("b", "Mehmet")]
        bh = [adim("a", g=-9, oncelik=-9), adim("b", g=-8, oncelik=-8)]
        self.assertEqual(ids(oz.hazirla(veri(kisiler, bh), BUGUN, [])["maddeler"]), ["a", "b"])
        kotu = [kayit(1, "a", "ise_yaramadi", 30), kayit(2, "a", "ise_yaramadi", 10)]
        self.assertEqual(ids(oz.hazirla(veri(kisiler, bh), BUGUN, kotu)["maddeler"]), ["b", "a"])

    def test_partner_akraba_gunluk_icin_ihmal_maddesi_yok_adim_var(self):
        kisiler = [kisi("es", "Eş Kişi"), kisi("kuzen", "Kuzen Kişi"), kisi("ev", "Ev Arkadaşı", temas_sikligi="gunluk"),
                   kisi("tur-partner", "Tur Partner", tur="partner"), kisi("a", "Ayşe")]
        iliskiler = [{"a": "ben", "b": "es", "tip": "partner"}, {"a": "kuzen", "b": "ben", "tip": "akraba"}, {"a": "ben", "b": "a", "tip": "arkadas"}]
        bh = [ihmal(k, 60, oncelik=-30) for k in ("es", "kuzen", "ev", "tur-partner")] + [ihmal("a", 20, 5)]
        self.assertEqual(ids(oz.hazirla(veri(kisiler, bh, iliskiler), BUGUN, [])["maddeler"]), ["a"])
        bh = [adim("es", "Doğum günü hediyesi al", g=1)]
        o = oz.hazirla(veri(kisiler, bh, iliskiler), BUGUN, [])
        self.assertEqual(ids(o["maddeler"]), ["es"])        # sonraki adım yine gösterilir
        self.assertNotIn("Kısa bir selam", o["maddeler"][0]["adim"])

    def test_sozler_ayri_liste_gecikmis_once_en_cok_uc(self):
        kisiler = [kisi(f"k{i}", f"Kişi {i}", sozler=[soz_kaydi(metin=f"söz {i}")]) for i in range(1, 6)]
        bh = [soz("k1", 3), soz("k2", -1), soz("k3", 0), soz("k4", -6), soz("k5", 8)]
        o = oz.hazirla(veri(kisiler, bh), BUGUN, [])
        self.assertEqual(ids(o["sozler"]), ["k4", "k2", "k3"])   # gecikmiş (en çok gecikmiş önce), sonra bugün
        self.assertEqual(o["maddeler"], [])
        self.assertEqual([m["gecikme"] for m in o["sozler"]], [6, 1, 0])
        self.assertFalse(o["bos"])

    def test_soz_maddesi_bekleme_ve_carpandan_etkilenmez(self):
        k = [kayit(1, "a", "atlandi", 5), kayit(2, "a", "atlandi", 2)]
        kisiler = [kisi("a", "Ayşe", sozler=[soz_kaydi()])]
        o = oz.hazirla(veri(kisiler, [ihmal("a", 30, 1), soz("a", -2)]), BUGUN, k)
        self.assertEqual(ids(o["maddeler"]), [])      # kişi dinleniyor
        self.assertEqual(ids(o["sozler"]), ["a"])     # ama verdiği söz hâlâ görünür

    def test_ayni_kisi_hem_kisi_hem_soz_maddesi_olabilir(self):
        kisiler = [kisi("a", "Ayşe", sozler=[soz_kaydi()])]
        o = oz.hazirla(veri(kisiler, [ihmal("a"), soz("a", -1)]), BUGUN, [])
        self.assertEqual((ids(o["maddeler"]), ids(o["sozler"])), (["a"], ["a"]))

    def test_bos_hafta(self):
        o = oz.hazirla(veri([kisi("a", "Ayşe")], []), BUGUN, [])
        self.assertTrue(o["bos"])
        self.assertEqual((o["maddeler"], o["sozler"]), ([], []))
        self.assertEqual(o["selam"], "Günaydın Umut. Bu hafta acil bir şey yok. Ağın sakin.")

    def test_selam_sayilari(self):
        kisiler = [kisi(f"k{i}", f"Kişi {i}", sozler=[soz_kaydi()]) for i in range(1, 6)]
        h = lambda bh: oz.hazirla(veri(kisiler, bh), BUGUN, [])["selam"]
        self.assertEqual(h([ihmal("k1"), ihmal("k2"), ihmal("k3"), soz("k4", -1)]), "Günaydın Umut. Bu hafta 3 kişi ve 1 söz seni bekliyor.")
        self.assertEqual(h([ihmal("k1")]), "Günaydın Umut. Bu hafta 1 kişi seni bekliyor.")
        self.assertEqual(h([soz("k1", -1), soz("k2", 0)]), "Günaydın Umut. Bu hafta 2 söz seni bekliyor.")
        self.assertEqual(h([ihmal(f"k{i}") for i in range(1, 6)]), "Günaydın Umut. Bu hafta 3 kişi seni bekliyor.")   # gösterilen kadar
        self.assertEqual(oz.hazirla(veri(kisiler, [ihmal("k1")], ben_ad="Ben"), BUGUN, [])["selam"], "Günaydın. Bu hafta 1 kişi seni bekliyor.")
        self.assertEqual(oz.hazirla(veri(kisiler, [ihmal("k1")], ben_ad="Umut Koray"), BUGUN, [])["selam"], "Günaydın Umut. Bu hafta 1 kişi seni bekliyor.")

    def test_sonuc_bekleyen_ve_istatistik(self):
        kisiler = [kisi("selin-hoca", "Selin Hoca"), kisi("mehmet-kaya", "Mehmet Kaya")]
        k = [kayit(1, "selin-hoca", "bekliyor", 4, oneri="Selam yaz"), kayit(2, "mehmet-kaya", "yaptim", 9, kapanis_gun_once=6),
             kayit(3, "mehmet-kaya", "bekliyor", 1), kayit(4, "selin-hoca", "ise_yaradi", 12)]
        o = oz.hazirla(veri(kisiler, []), BUGUN, k)
        self.assertEqual([(r["no"], r["sonuc"]) for r in o["sonuc_bekleyen"]], [(2, "yaptim"), (1, "bekliyor")])
        self.assertEqual(o["sonuc_bekleyen"][0]["soru"], "Mehmet Kaya ile nasıl geçti? İşe yaradı mı?")
        self.assertEqual(o["sonuc_bekleyen"][1]["soru"], "Selin Hoca için önerdiğim adımı attın mı?")
        self.assertEqual(o["istatistik"]["son_8_hafta"]["toplam"], 4)
        self.assertTrue(o["bos"])   # bekleyen sonuç sorusu "acil iş" sayılmaz

    def test_hazirla_girdiyi_degistirmez_ve_dosya_yazmaz(self):
        with tempfile.TemporaryDirectory() as t:
            eski = c.VERI
            c.veri_klasoru(os.path.join(t, "veri"))
            try:
                v = veri([kisi("a", "Ayşe")], [ihmal("a")])
                once = json.dumps(v, ensure_ascii=False, sort_keys=True)
                oz.hazirla(v, BUGUN, [])
                self.assertEqual(json.dumps(v, ensure_ascii=False, sort_keys=True), once)
                self.assertFalse(os.path.exists(os.path.join(c.VERI, "ozet")))
                self.assertFalse(os.path.exists(os.path.join(c.VERI, "sonuclar.md")))
                oz.hazirla(v, BUGUN)   # kayitlar verilmezse defter okunur (yoksa boş), yine yazılmaz
                self.assertFalse(os.path.exists(os.path.join(c.VERI, "sonuclar.md")))
            finally:
                c.veri_klasoru(eski)


class MetinTest(unittest.TestCase):
    def madde(self, k, bh):
        return oz.hazirla(veri([k], [bh]), BUGUN, [])["maddeler"][0]

    def test_ihmal_son_temas_konusunu_anar(self):
        k = kisi("ayse-yilmaz", "Ayşe Yılmaz", govde="# Ayşe\n\n## Temas\n- 01.09.2026 · whatsapp · Eski konu\n- 12.10.2026 · whatsapp · Staj ilanını sordu\n")
        m = self.madde(k, ihmal("ayse-yilmaz"))
        self.assertEqual(m["adim"], "Kısa bir selam yaz: son konuştuğunuz “Staj ilanını sordu” hakkında sor")
        self.assertEqual(m["taslak"], "Selam Ayşe, nasılsın? Epeydir konuşmadık, aklıma geldin. Müsait olduğunda kısa bir sohbet edelim mi?")
        self.assertNotIn("Staj", m["taslak"])      # temas notu kullanıcının kendine yazdığı nottur: karşı tarafa giden taslakta geçmez
        self.assertEqual(m["kanal_onerisi"], "whatsapp")

    def test_temas_notu_taslaga_girmez(self):
        not_ = "Staj başvurusu için referans rica ettim, hemen kabul etti"
        k = kisi("selin-hoca", "Selin Hoca", govde="## Temas\n- 12.10.2026 · whatsapp · " + not_ + "\n")
        m = self.madde(k, ihmal("selin-hoca"))
        for parca in ("Staj", "referans", "rica ettim", "kabul"):
            self.assertNotIn(parca, m["taslak"])
        self.assertNotIn("“", m["taslak"])
        self.assertIn("Staj başvurusu için referans", m["adim"])    # not yalnız kullanıcıya görünen adım satırında kalır
        self.assertEqual(m["taslak"], "Merhaba Selin Hocam, nasılsınız? Epeydir görüşemedik, aklıma geldiniz. Uygun olduğunuzda kısa bir sohbet edelim mi?")

    def test_en_yeni_temas_tarihe_gore_secilir_siraya_gore_degil(self):
        k = kisi("a", "Ayşe", govde="## Temas\n- 12.10.2026 · mail · Yeni konu\n- 01.09.2026 · whatsapp · Eski konu\n")
        self.assertIn("Yeni konu", self.madde(k, ihmal("a"))["adim"])
        self.assertNotIn("Yeni konu", self.madde(k, ihmal("a"))["taslak"])

    def test_konu_60_karakteri_asmaz(self):
        uzun = "Açık veri çağrısı için başvuru taslağını birlikte gözden geçirmeyi konuştuk ve tarih verdik"
        k = kisi("a", "Ayşe", govde=f"## Temas\n- 12.10.2026 · whatsapp · {uzun}\n")
        konu = oz._konu(k)
        self.assertLessEqual(len(konu), 60)
        self.assertTrue(konu.endswith("…"))
        self.assertTrue(uzun.startswith(konu[:-1]))
        self.assertIn(konu, self.madde(k, ihmal("a"))["adim"])      # kesilmiş not kullanıcıya görünen adımda
        self.assertNotIn(konu[:20], self.madde(k, ihmal("a"))["taslak"])

    def test_konu_yoksa_genel_sicak_selam(self):
        for govde in ("", "## Temas\n- (henüz yok)\n", "## Temas\n- 12.10.2026 · whatsapp · toplantı\n", "## Temas\n- 12.10.2026 · whatsapp\n",
                      "## Temas\n- 12.10.2026 · diğer · Kut önerisi: Kısa bir selam yaz\n"):
            m = self.madde(kisi("a", "Ayşe Yılmaz", govde=govde), ihmal("a"))
            self.assertEqual(m["adim"], "Kısa bir selam yaz: nasıl olduğunu sor", govde)
            self.assertEqual(m["taslak"], "Selam Ayşe, nasılsın? Epeydir konuşmadık, aklıma geldin. Müsait olduğunda kısa bir sohbet edelim mi?", govde)

    def test_ilk_ad_ve_unvanlar(self):
        self.assertEqual(oz._ilk_ad("Ayşe Yılmaz"), "Ayşe")
        self.assertEqual(oz._ilk_ad("Selin Hoca"), "Selin Hoca")
        self.assertEqual(oz._ilk_ad("Dr. Mehmet Kaya"), "Mehmet")
        self.assertEqual(oz._ilk_ad("Prof. Dr. Deniz Demo"), "Deniz")
        self.assertEqual(oz._ilk_ad("Kerem Bey"), "Kerem Bey")
        self.assertEqual(oz._ilk_ad("Mert"), "Mert")
        self.assertEqual(oz._ilk_ad(""), "")
        m = self.madde(kisi("selin-hoca", "Selin Hoca Demir"), ihmal("selin-hoca"))
        self.assertTrue(m["taslak"].startswith("Merhaba Selin Hocam, nasılsınız?"))

    def test_sonraki_adim_metni(self):
        k = kisi("mehmet-kaya", "Mehmet Kaya", sonraki_adim="Raporu gönder", sonraki_tarih="2026-10-20")
        m = self.madde(k, {"id": "mehmet-kaya", "neden": "Raporu gönder (1 gün kaldı)", "oncelik": 1})
        self.assertEqual(m["adim"], "Raporu gönder")
        self.assertEqual(m["taslak"], "Selam Mehmet, nasılsın? Sana bir konuda dönecektim; uygun olduğunda kısa konuşalım mı?")
        self.assertNotIn("rapor", m["taslak"].lower())      # adım kullanıcının kendi işi (emir kipi): karşı tarafa gidecek taslakta geçmez
        # sonraki_adim alanı yoksa neden satırından
        m = self.madde(kisi("mehmet-kaya", "Mehmet Kaya"), {"id": "mehmet-kaya", "neden": "Raporu gönder (2 gün gecikti)", "oncelik": -2})
        self.assertEqual(m["adim"], "Raporu gönder")

    def test_sonraki_adim_taslaga_girmez_siz_ve_sen(self):
        for ad, tur, bas in (("Baran Aksoy", "cevre", "Selam Baran, nasılsın?"), ("Selin Hoca", "akademi", "Merhaba Selin Hocam, nasılsınız?")):
            k = kisi("x", ad, tur=tur, sonraki_adim="makale taslağına yorum yaz")
            m = self.madde(k, {"id": "x", "neden": "makale taslağına yorum yaz (bugün)", "oncelik": 0})
            self.assertEqual(m["adim"], "makale taslağına yorum yaz")
            self.assertTrue(m["taslak"].startswith(bas), m["taslak"])
            for parca in ("makale", "yorum", "taslağ"):
                self.assertNotIn(parca, m["taslak"])
        self.assertIn("Size bir konuda dönecektim; uygun olduğunuzda kısa görüşebilir miyiz?", m["taslak"])

    def test_taslaklar_kisa(self):
        for govde in ("", "## Temas\n- 12.10.2026 · whatsapp · " + "x" * 300 + "\n"):
            m = self.madde(kisi("a", "Ayşe", govde=govde, sonraki_adim="y" * 300), ihmal("a"))
            self.assertLessEqual(len(m["taslak"]), oz.TASLAK_AZAMI)
            self.assertLessEqual(len(m["taslak"].split(". ")), 4)

    def test_kanal_onerisi(self):
        self.assertEqual(self.madde(kisi("a", "A", govde="## Temas\n- 12.10.2026 · linkedin · selam\n"), ihmal("a"))["kanal_onerisi"], "linkedin")
        self.assertEqual(self.madde(kisi("a", "A", eposta="a@ornek.test"), ihmal("a"))["kanal_onerisi"], "e-posta")
        self.assertEqual(self.madde(kisi("a", "A", telefon=["05550000000"]), ihmal("a"))["kanal_onerisi"], "mesaj")
        self.assertEqual(self.madde(kisi("a", "A"), ihmal("a"))["kanal_onerisi"], "")

    def test_soz_maddesi_metinleri(self):
        k = kisi("a", "Ayşe Yılmaz", sozler=[soz_kaydi("ben", "kitabı göndermek", "2026-10-17"), soz_kaydi("o", "staj ilanını yollamak", "2026-10-30", sira=1)])
        o = oz.hazirla(veri([k], [soz("a", -2, 0, "ben"), soz("a", 11, 1, "o")]), BUGUN, [])
        ben, o_ = o["sozler"]
        self.assertEqual(ben["adim"], "Sözünü yerine getir ya da yeni bir tarih ver: kitabı göndermek")
        self.assertEqual(ben["taslak"], "Selam Ayşe, nasılsın? Sana söz verdiğim konuda dönmek istedim; kısa bir güncelleme vereyim mi?")
        self.assertNotIn("kitab", ben["taslak"])
        self.assertEqual((ben["yon"], ben["gecikme"], ben["son"]), ("ben", 2, "2026-10-17"))
        self.assertEqual(o_["adim"], "Nazikçe hatırlat: staj ilanını yollamak")
        self.assertEqual(o_["taslak"], "Selam Ayşe, nasılsın? Konuştuğumuz konuyu nazikçe hatırlatmak istedim; uygun olduğunda bakabilir misin?")
        self.assertNotIn("staj", o_["taslak"])
        self.assertEqual(o_["yon"], "o")
        self.assertNotIn("sonuc", ben)

    def test_soz_satiri_kisi_sozlerinden_okunur_yoksa_govdeden(self):
        govde = sz.ekle("# A\n", "ben", "kitabı göndermek", "2026-10-17", date(2026, 10, 1))
        k = kisi("a", "Ayşe", govde=govde, sozler=[])
        o = oz.hazirla(veri([k], [soz("a", -2)]), BUGUN, [])
        self.assertEqual(o["sozler"][0]["metin"], "kitabı göndermek")


class HitapTest(unittest.TestCase):
    """`hitap`: sen/siz kaydı (ag_yol da kullanır)."""

    def h(self, ad, tur="cevre", yakinlik=2):
        return oz.hitap({"ad": ad, "tur": tur, "yakinlik": yakinlik})

    def test_sen_varsayilan(self):
        self.assertEqual(self.h("Ayşe Yılmaz"), {"selam": "Selam", "ad": "Ayşe", "siz_mi": False})
        self.assertEqual(self.h("Mert", "yakin", 3), {"selam": "Selam", "ad": "Mert", "siz_mi": False})
        self.assertEqual(self.h("Deniz Demo", "is", 2)["siz_mi"], False)           # iş/siyaset: yakınlık 2+ ise sen
        self.assertEqual(self.h("Deniz Demo", "siyaset", 3)["siz_mi"], False)
        self.assertEqual(self.h("Deniz Demo", "finans", 0)["siz_mi"], False)

    def test_akademi_siz(self):
        self.assertEqual(self.h("Mehmet Kaya", "akademi", 3), {"selam": "Merhaba", "ad": "Mehmet", "siz_mi": True})

    def test_unvanli_ad_siz(self):
        self.assertEqual(self.h("Selin Hoca"), {"selam": "Merhaba", "ad": "Selin Hocam", "siz_mi": True})
        self.assertEqual(self.h("Selin Hoca Demir", "akademi"), {"selam": "Merhaba", "ad": "Selin Hocam", "siz_mi": True})
        # ag_yol ile aynı biçim: unvanlı adlar olduğu gibi
        self.assertEqual(self.h("Dr. Mehmet Kaya"), {"selam": "Merhaba", "ad": "Dr. Mehmet Kaya", "siz_mi": True})
        self.assertEqual(self.h("Dr. Ayşe Kaya")["ad"], "Dr. Ayşe Kaya")
        self.assertEqual(self.h("Prof. Dr. Deniz Demo")["ad"], "Prof. Dr. Deniz Demo")
        self.assertEqual(self.h("Doç. Elif Demir")["ad"], "Doç. Elif Demir")
        self.assertEqual(self.h("Kerem Bey Aksoy", "akademi")["ad"], "Kerem Bey Aksoy")
        self.assertEqual(self.h("Kerem Bey Aksoy", "cevre", 3), {"selam": "Selam", "ad": "Kerem Bey Aksoy", "siz_mi": False})   # Bey tek başına siz yapmaz

    def test_is_ve_siyaset_yakinlik_en_cok_1_siz(self):
        for tur in ("is", "siyaset"):
            for y in (0, 1):
                self.assertEqual(self.h("Baran Aksoy", tur, y), {"selam": "Merhaba", "ad": "Baran", "siz_mi": True}, (tur, y))
        self.assertTrue(oz.hitap({"ad": "Baran Aksoy", "tur": "is"})["siz_mi"])             # yakınlık yoksa 0 sayılır
        self.assertTrue(oz.hitap({"ad": "Baran Aksoy", "tur": "is", "yakinlik": "bozuk"})["siz_mi"])

    def test_bos_girdi_cokmez(self):
        self.assertEqual(oz.hitap({}), {"selam": "Selam", "ad": "", "siz_mi": False})
        self.assertEqual(oz.hitap(None)["siz_mi"], False)

    def test_ihmal_taslagi_siz_ve_sen(self):
        siz = oz.hazirla(veri([kisi("b", "Baran Aksoy", tur="siyaset", yakinlik=1)], [ihmal("b")]), BUGUN, [])["maddeler"][0]["taslak"]
        self.assertEqual(siz, "Merhaba Baran, nasılsınız? Epeydir görüşemedik, aklıma geldiniz. Uygun olduğunuzda kısa bir sohbet edelim mi?")
        sen = oz.hazirla(veri([kisi("b", "Baran Aksoy", tur="siyaset", yakinlik=2)], [ihmal("b")]), BUGUN, [])["maddeler"][0]["taslak"]
        self.assertEqual(sen, "Selam Baran, nasılsın? Epeydir konuşmadık, aklıma geldin. Müsait olduğunda kısa bir sohbet edelim mi?")

    def test_soz_taslagi_siz(self):
        k = kisi("selin-hoca", "Selin Hoca", tur="akademi", sozler=[soz_kaydi("ben", "kitabı göndermek"), soz_kaydi("o", "makaleyi yollamak", sira=1)])
        ben, o_ = oz.hazirla(veri([k], [soz("selin-hoca", -2, 0, "ben"), soz("selin-hoca", -1, 1, "o")]), BUGUN, [])["sozler"]
        self.assertEqual(ben["taslak"], "Merhaba Selin Hocam, nasılsınız? Size söz verdiğim konuda dönmek istedim; kısa bir güncelleme vermemi ister misiniz?")
        self.assertEqual(o_["taslak"], "Merhaba Selin Hocam, nasılsınız? Konuştuğumuz konuyu nazikçe hatırlatmak istedim; uygun olduğunuzda bakabilir misiniz?")
        self.assertNotIn("nasılsın?", ben["taslak"] + o_["taslak"])

    def test_soz_metni_karsi_tarafa_giden_taslaga_girmez(self):
        metin = "Ayşe bana referans mektubu yazacak, ona çok güvenmiyorum {ad} {0}"
        for yon in ("ben", "o"):
            k = kisi("a", "Ayşe", sozler=[soz_kaydi(yon, metin)])
            (m,) = oz.hazirla(veri([k], [soz("a", -1, 0, yon)]), BUGUN, [])["sozler"]
            for parca in ("referans", "mektup", "güven", "{", metin[:12]):
                self.assertNotIn(parca, m["taslak"])
            self.assertIn(metin, m["adim"])      # söz metni yalnız kullanıcıya görünen alanda
            self.assertEqual(m["metin"], metin)


class SirTest(unittest.TestCase):
    def test_sir_ic_metinleri_suzer(self):
        o = oz._sir_ic({"a": ["api_key=sk-abcdef1234567890ABCDEF12 ile bağlan", {"b": "parola: hunter2hunter2"}], "n": 3, "x": None})
        self.assertNotIn("sk-abcdef", json.dumps(o))
        self.assertNotIn("hunter2", json.dumps(o))
        self.assertEqual(o["n"], 3)


class OlusturTest(unittest.TestCase):
    """Gerçek geçici veri klasörüyle: dosya, defter kaydı, idempotentlik, temizlik, ayar."""

    def setUp(self):
        yama = mock.patch.object(oz, "_saat", return_value=9)
        yama.start()
        self.addCleanup(yama.stop)
        self.eski = (c.VERI, ia.DEPO, ia.AYARLAR, ia.ADAYLAR)
        self.t = tempfile.TemporaryDirectory()
        self.veri_yol, self.depo = os.path.join(self.t.name, "veri"), os.path.join(self.t.name, "depo")
        os.makedirs(self.depo)
        ia.DEPO, ia.AYARLAR, ia.ADAYLAR = self.depo, os.path.join(self.depo, "ayarlar.json"), os.path.join(self.depo, "adaylar.json")
        c.veri_klasoru(self.veri_yol)
        c.ben_yaz({"ad": "Umut"})
        self.kisi("ayse-yilmaz", "Ayşe Yılmaz", "# Ayşe\n\n## Temas\n- 20.09.2026 · whatsapp · Staj ilanını sordu\n", yakinlik="3", son_temas="2026-09-20")
        self.kisi("mehmet-kaya", "Mehmet Kaya", yakinlik="2", sonraki_adim="Raporu gönder", sonraki_tarih="2026-10-20", son_temas="2026-10-10")
        govde = sz.ekle("# Elif\n\n## Temas\n- 10.10.2026 · mail · selam\n", "ben", "kitabı göndermek", "2026-10-17", date(2026, 10, 1))
        self.kisi("elif-demir", "Elif Demir", govde, yakinlik="2", son_temas="2026-10-10")
        with open(c.HARIC, "a", encoding="utf-8") as f:
            f.write("- Örnek Parti\n")
        self.kisi("deniz-demo", "Deniz Demo", yakinlik="3", son_temas="2026-06-01", kurum="Örnek Parti")

    def tearDown(self):
        c.veri_klasoru(self.eski[0])
        ia.DEPO, ia.AYARLAR, ia.ADAYLAR = self.eski[1:]
        self.t.cleanup()

    def kisi(self, kid, ad, govde=None, **alan):
        c.kisi_yaz(kid, {"ad": ad, "tur": "cevre", **alan}, govde if govde is not None else f"# {ad}\n\n## Temas\n- (henüz yok)\n")

    def ozet_yolu(self, hafta="2026-W43"):
        return os.path.join(c.VERI, "ozet", hafta + ".md")

    def test_olustur_dosya_ve_defter_kaydi(self):
        o = oz.olustur(BUGUN)
        self.assertEqual(o["hafta"], "2026-W43")
        self.assertEqual(sorted(ids(o["maddeler"])), ["ayse-yilmaz", "mehmet-kaya"])      # hariç Deniz yok; Elif'in yalnız sözü var
        self.assertEqual(ids(o["sozler"]), ["elif-demir"])
        self.assertNotIn("Deniz", json.dumps(o, ensure_ascii=False))
        defter = sn.oku()
        self.assertEqual(sorted(r["kisi"] for r in defter), ["ayse-yilmaz", "mehmet-kaya"])
        self.assertTrue(all(r["kaynak"] == "ozet" and r["sonuc"] == "bekliyor" and r["tarih"] == "2026-10-19" for r in defter))
        for m in o["maddeler"]:
            self.assertEqual(next(r for r in defter if r["no"] == m["no"])["oneri"], m["adim"])
        md = open(self.ozet_yolu(), encoding="utf-8").read()
        self.assertTrue(md.startswith("---\nvisibility: private\n---\n\n# Haftalık özet · 2026-W43\n\nGünaydın Umut. Bu hafta 2 kişi ve 1 söz seni bekliyor.\n"))
        self.assertIn("### 1. ", md)
        self.assertIn("```json kut\n", md)
        self.assertIn("> Selam Ayşe, nasılsın?", md)
        self.assertEqual(json.loads(md.split("```json kut\n")[1].split("\n```")[0])["hafta"], "2026-W43")

    def test_ikinci_cagri_dosyayi_okur_kayitlari_cogaltmaz(self):
        a = oz.olustur(BUGUN)
        once = open(self.ozet_yolu(), encoding="utf-8").read()
        b = oz.olustur(BUGUN)
        self.assertEqual(a["maddeler"], b["maddeler"])
        self.assertEqual(a["uretildi"], b["uretildi"])      # yeniden üretilmedi
        self.assertEqual(len(sn.oku()), 2)
        self.assertEqual(open(self.ozet_yolu(), encoding="utf-8").read(), once)

    def test_yenile_yeniden_uretir_ama_defteri_cogaltmaz(self):
        a = oz.olustur(BUGUN)
        b = oz.olustur(BUGUN, yenile=True)
        self.assertEqual([m["no"] for m in a["maddeler"]], [m["no"] for m in b["maddeler"]])
        self.assertEqual(len(sn.oku()), 2)
        oz.olustur(BUGUN, yenile=True)
        self.assertEqual(len(sn.oku()), 2)

    def test_yenile_sonucu_isaretlenmis_kaydi_korur(self):
        a = oz.olustur(BUGUN)
        no = a["maddeler"][0]["no"]
        sn.isaretle(no, "yaptim", bugun=BUGUN)
        b = oz.olustur(BUGUN, yenile=True)
        self.assertEqual(next(m for m in b["maddeler"] if m["no"] == no)["sonuc"], "yaptim")
        self.assertEqual(len(sn.oku()), 2)

    def test_okurken_sonuc_istatistik_bekleyen_taze(self):
        a = oz.olustur(BUGUN)
        self.assertTrue(all(m["sonuc"] == "bekliyor" for m in a["maddeler"]))
        no = a["maddeler"][0]["no"]
        sn.isaretle(no, "ise_yaradi", bugun=BUGUN)
        b = oz.olustur(BUGUN)
        self.assertEqual(next(m for m in b["maddeler"] if m["no"] == no)["sonuc"], "ise_yaradi")
        self.assertEqual(b["istatistik"]["son_8_hafta"]["ise_yarayan"], 1)
        c_ = oz.olustur(BUGUN + timedelta(days=4))     # aynı hafta, 4 gün sonra: kalan "bekliyor" kaydın sonucu sorulur
        self.assertEqual([(r["kisi"], r["sonuc"]) for r in c_["sonuc_bekleyen"]], [(a["maddeler"][1]["id"], "bekliyor")])

    def test_ayni_oneri_ertesi_hafta_yeni_kayit(self):
        oz.olustur(BUGUN)
        oz.olustur(BUGUN + timedelta(days=7))
        self.assertEqual(len(sn.oku()), 4)
        self.assertTrue(os.path.exists(self.ozet_yolu("2026-W44")))

    def test_bozuk_ozet_dosyasi_yeniden_uretilir(self):
        os.makedirs(os.path.dirname(self.ozet_yolu()))
        for icerik in ("", "# bozuk", "```json kut\n{bozuk\n```", "```json kut\n[1]\n```", '```json kut\n{"hafta": "2026-W01"}\n```'):
            with open(self.ozet_yolu(), "w", encoding="utf-8") as f:
                f.write(icerik)
            self.assertEqual(oz.olustur(BUGUN)["hafta"], "2026-W43", icerik)
            self.assertEqual(len(sn.oku()), 2)

    def test_son_bu_haftanin_ozeti_ya_da_none(self):
        self.assertIsNone(oz.son())
        o = oz.olustur()    # gerçek bugün
        s = oz.son()
        self.assertEqual(s["hafta"], o["hafta"])
        self.assertEqual(s["hafta"], oz.hafta_anahtari())
        self.assertEqual(ids(s["maddeler"]), ids(o["maddeler"]))

    def test_son_gecen_haftanin_ozetini_vermez(self):
        os.makedirs(os.path.dirname(self.ozet_yolu()), exist_ok=True)
        oz.olustur(BUGUN - timedelta(days=60))
        self.assertIsNone(oz.son())

    def test_eski_ozetler_12_haftadan_sonra_silinir(self):
        klasor = os.path.dirname(self.ozet_yolu())
        os.makedirs(klasor)
        for ad in ("2026-W43", "2026-W31", "2026-W30", "2026-W20", "2025-W40", "2026-W99"):
            with open(os.path.join(klasor, ad + ".md"), "w", encoding="utf-8") as f:
                f.write("eski")
        with open(os.path.join(klasor, "notum.md"), "w", encoding="utf-8") as f:
            f.write("benim notum")
        oz.olustur(BUGUN)
        kalan = sorted(os.listdir(klasor))
        # W43 pazartesi 19 Ekim; 12 hafta öncesi 27 Temmuz = W31 pazartesi: ondan eskisi (W30 ve öncesi) silinir
        self.assertEqual(kalan, ["2026-W31.md", "2026-W43.md", "2026-W99.md", "notum.md"])

    def test_eski_ozet_temizligi_okuma_yolunda_da_calisir(self):
        oz.olustur(BUGUN)
        klasor = os.path.dirname(self.ozet_yolu())
        with open(os.path.join(klasor, "2025-W10.md"), "w", encoding="utf-8") as f:
            f.write("eski")
        oz.olustur(BUGUN)     # dosya var → okunur; bakım yine yapılır
        self.assertFalse(os.path.exists(os.path.join(klasor, "2025-W10.md")))

    def test_bekleyen_kisi_olustur_icinde_dusurulur(self):
        n1 = sn.kaydet("ozet", "ayse-yilmaz", "Eski öneri", BUGUN - timedelta(days=14))
        n2 = sn.kaydet("ozet", "ayse-yilmaz", "Eski öneri 2", BUGUN - timedelta(days=7))
        sn.isaretle(n1, "atlandi", bugun=BUGUN - timedelta(days=13))
        sn.isaretle(n2, "atlandi", bugun=BUGUN - timedelta(days=6))
        o = oz.olustur(BUGUN)
        self.assertEqual(ids(o["maddeler"]), ["mehmet-kaya"])

    def haric_yap(self, kid, kurum="Sonradan Parti"):
        k = c.kisi_oku(os.path.join(c.KISILER, kid + ".md"))
        govde = k.pop("govde")
        k["kurum"] = kurum
        c.kisi_yaz(kid, k, govde)
        with open(c.HARIC, "a", encoding="utf-8") as f:
            f.write(f"- {kurum}\n")

    def test_sonradan_haric_olan_kisi_okumada_dusurulur(self):
        a = oz.olustur(BUGUN)
        self.assertIn("ayse-yilmaz", ids(a["maddeler"]))
        self.haric_yap("ayse-yilmaz")
        self.haric_yap("elif-demir", "Sonradan Parti")
        b = oz.olustur(BUGUN)       # dosya var → okunur, ama hariç süzülür
        self.assertEqual(ids(b["maddeler"]), ["mehmet-kaya"])
        self.assertEqual(b["sozler"], [])
        self.assertEqual(b["selam"], "Günaydın Umut. Bu hafta 1 kişi seni bekliyor.")
        self.assertFalse(b["bos"])
        md = open(self.ozet_yolu(), encoding="utf-8").read()      # kayıtlı dosyadan da çıktı
        for ad in ("Ayşe", "Elif"):
            self.assertNotIn(ad, md)
        self.assertEqual(ids(oz._dosya_oku("2026-W43")["maddeler"]), ["mehmet-kaya"])

    def test_sonradan_haric_son_icinde_de_dusurulur(self):
        oz.olustur()          # gerçek bugün
        for kid in ("ayse-yilmaz", "mehmet-kaya", "elif-demir"):
            self.haric_yap(kid)
        s = oz.son()
        self.assertEqual((s["maddeler"], s["sozler"], s["bos"]), ([], [], True))
        self.assertEqual(s["selam"], "Günaydın Umut. Bu hafta acil bir şey yok. Ağın sakin.")

    def test_sonradan_haric_sonuc_bekleyende_de_dusurulur(self):
        sn.kaydet("ozet", "ayse-yilmaz", "Eski öneri", BUGUN - timedelta(days=5))
        sn.kaydet("ozet", "mehmet-kaya", "Eski öneri", BUGUN - timedelta(days=5))
        self.assertEqual(sorted(r["kisi"] for r in oz.olustur(BUGUN)["sonuc_bekleyen"]), ["ayse-yilmaz", "mehmet-kaya"])
        self.haric_yap("ayse-yilmaz")
        self.assertEqual([r["kisi"] for r in oz.olustur(BUGUN)["sonuc_bekleyen"]], ["mehmet-kaya"])

    def test_kisi_dosyasi_silinince_madde_duser(self):
        oz.olustur(BUGUN)
        os.remove(os.path.join(c.KISILER, "mehmet-kaya.md"))
        self.assertEqual(ids(oz.olustur(BUGUN)["maddeler"]), ["ayse-yilmaz"])

    def test_selam_okuma_aninda_saate_gore_uretilir(self):
        oz.olustur(BUGUN)
        for saat, soz_ in ((4, "İyi geceler"), (5, "Günaydın"), (10, "Günaydın"), (11, "Merhaba"), (16, "Merhaba"), (17, "İyi akşamlar"),
                           (21, "İyi akşamlar"), (22, "İyi geceler"), (0, "İyi geceler")):
            with mock.patch.object(oz, "_saat", return_value=saat):
                self.assertEqual(oz.olustur(BUGUN)["selam"], f"{soz_} Umut. Bu hafta 2 kişi ve 1 söz seni bekliyor.", saat)

    def test_madde_tarih_alani(self):
        o = oz.olustur(BUGUN)
        m = {x["id"]: x for x in o["maddeler"]}
        self.assertEqual(m["mehmet-kaya"]["tarih"], "2026-10-20")      # sonraki adım: sonraki_tarih
        self.assertEqual(m["ayse-yilmaz"]["tarih"], "")                # ihmal: boş
        self.assertEqual(o["sozler"][0]["tarih"], "2026-10-17")        # söz: son tarih
        self.assertEqual(m["mehmet-kaya"]["sonuc"], "bekliyor")
        self.assertIn("sonuc", m["ayse-yilmaz"])

    def test_tarih_alani_hazirla_ve_bozuk_tarih(self):
        k = [kisi("a", "Ayşe", sonraki_adim="Ara", sonraki_tarih="2026-10-20"), kisi("b", "Mert", sonraki_adim="Ara", sonraki_tarih="yarın"),
             kisi("c", "Can", sozler=[soz_kaydi(son="")])]
        o = oz.hazirla(veri(k, [adim("a", "Ara", 1), adim("b", "Ara", 2), soz("c", 9)]), BUGUN, [])
        self.assertEqual({m["id"]: m["tarih"] for m in o["maddeler"]}, {"a": "2026-10-20", "b": ""})
        self.assertEqual(o["sozler"][0]["tarih"], "")

    def test_ozet_dosyasi_ozel_gorunurluk(self):
        oz.olustur(BUGUN)
        self.assertTrue(open(self.ozet_yolu(), encoding="utf-8").read().startswith("---\nvisibility: private\n---\n"))
        self.assertTrue(open(sn.yol(), encoding="utf-8").read().startswith("---\nvisibility: private\n---\n"))

    def test_frontmattersiz_eski_ozet_okunur(self):
        a = oz.olustur(BUGUN)
        md = open(self.ozet_yolu(), encoding="utf-8").read()
        with open(self.ozet_yolu(), "w", encoding="utf-8", newline="\n") as f:
            f.write(md.split("---\n\n", 1)[1])        # eski biçim: frontmatter yok
        b = oz.olustur(BUGUN)
        self.assertEqual(b["uretildi"], a["uretildi"])    # yeniden üretilmedi, dosyadan okundu
        self.assertEqual(ids(b["maddeler"]), ids(a["maddeler"]))

    def test_kullanici_metni_json_blogunu_taklit_edemez(self):
        self.kisi("kotu-ad", "Kötü ```json kut", yakinlik="3", sonraki_adim="Teklif | gönder ```json kut\n{}\n```", sonraki_tarih="2026-10-18",
                  son_temas="2026-10-01")
        a = oz.olustur(BUGUN)
        self.assertIn("kotu-ad", ids(a["maddeler"]))
        md = open(self.ozet_yolu(), encoding="utf-8").read()
        okunur = md.rpartition("\n```json kut\n")[0]
        self.assertNotIn("```", okunur)                   # okunur kısımda ham fence yok (kaçırıldı)
        self.assertIn("\\`\\`\\`json kut", okunur)
        b = oz.olustur(BUGUN)                             # dosya yeniden okunabilir
        self.assertEqual(b["uretildi"], a["uretildi"])
        self.assertEqual(ids(b["maddeler"]), ids(a["maddeler"]))
        self.assertEqual(oz._dosya_oku("2026-W43")["maddeler"][0]["ad"] in {m["ad"] for m in a["maddeler"]}, True)

    def test_satir_basi_markdown_kacirilir(self):
        self.assertEqual(oz._kac("# Başlık"), "\\# Başlık")
        self.assertEqual(oz._kac("- madde"), "\\- madde")
        self.assertEqual(oz._kac("1. adım"), "1\\. adım")
        self.assertEqual(oz._kac("a\nb | c *d*"), "a b \\| c \\*d\\*")

    def test_gecici_dosya_benzersiz_ve_hata_temiz_birakir(self):
        oz.olustur(BUGUN)
        self.assertEqual([f for f in os.listdir(os.path.dirname(self.ozet_yolu())) if not f.endswith(".md")], [])
        with mock.patch("ag_ozet.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                oz.olustur(BUGUN + timedelta(days=7), yenile=True)
        klasor = os.listdir(os.path.dirname(self.ozet_yolu()))
        self.assertEqual([f for f in klasor if f.endswith(".tmp") or f.endswith(".yeni")], [])
        self.assertEqual(klasor, ["2026-W43.md"])

    def test_eszamanli_yazanlar_dosyayi_bozmaz(self):
        import threading
        o = oz.olustur(BUGUN)
        hatalar = []

        def calis():
            try:
                for _ in range(8):
                    oz._dosya_yaz(o)
            except Exception as e:   # noqa: BLE001
                hatalar.append(e)
        isler = [threading.Thread(target=calis) for _ in range(4)]
        for t in isler:
            t.start()
        for t in isler:
            t.join()
        self.assertEqual(hatalar, [])
        self.assertIsNotNone(oz._dosya_oku("2026-W43"))
        self.assertEqual([f for f in os.listdir(os.path.dirname(self.ozet_yolu())) if f.endswith(".tmp")], [])

    def test_goruldu_ayari_yazar_ve_digerlerini_korur(self):
        ia.ayar_yaz({"ben_adlari": ["umut"], "vault": {"yol": "x"}, "ozet": {"baska": 1}})
        oz.goruldu("2026-W43")
        a = ia.ayarlar()
        self.assertEqual(a["ozet"], {"baska": 1, "goruldu": "2026-W43"})
        self.assertEqual(a["ben_adlari"], ["umut"])
        self.assertEqual(a["vault"], {"yol": "x"})
        self.assertEqual(oz.gorulen(), "2026-W43")
        oz.goruldu("2026-W44")
        self.assertEqual(ia.ayarlar()["ozet"]["goruldu"], "2026-W44")

    def test_goruldu_ayar_yoksa_olusturur(self):
        self.assertEqual(oz.gorulen(), "")
        oz.goruldu("2026-W43")
        self.assertEqual(ia.ayarlar()["ozet"], {"goruldu": "2026-W43"})

    def test_goruldu_bozuk_ozet_anahtari_ve_gecersiz_hafta(self):
        ia.ayar_yaz({"ozet": "bozuk"})
        oz.goruldu("2026-W43")
        self.assertEqual(ia.ayarlar()["ozet"], {"goruldu": "2026-W43"})
        for kotu in ("", "2026-43", "2026-W4", "../x", None, "2026-W43\n"):
            with self.assertRaises(ValueError, msg=repr(kotu)):
                oz.goruldu(kotu)

    def test_ozet_dosyasinda_gizli_metin_yok(self):
        # kişi notundaki sır kisi_yaz'da süzülür; özet verisi ek olarak kendi süzgecinden geçer
        o = oz._sir_ic({"taslak": "token: abcDEF1234567890abcDEF12 yaz"})
        self.assertNotIn("abcDEF1234567890", o["taslak"])


if __name__ == "__main__":
    unittest.main()


class OtomatikNotTest(unittest.TestCase):
    """İçe aktarmadan gelen üçüncü şahıs notları ("Grup sohbetinde ... yazışan bir...") "son konuştuğunuz" kalıbına girmez (16 Ekim 2026)."""
    def test_otomatik_not_konu_sayilmaz(self):
        for t in ("Grup sohbetinde ders, sinav ve staj konularinda yazisan bir arkadas", "Grup sohbetinde Minecraft ve sunucu konularinda Deniz ile",
                  "WhatsApp grubu üyesi"):
            k = {"ad": "Can Örnek", "govde": f"# Can\n\n## Temas\n- 01.09.2026 · whatsapp · {t}\n"}
            self.assertEqual(oz._konu(k), "", t)
        k = {"ad": "Barış", "govde": "# Barış\n\n## Temas\n- 01.09.2026 · whatsapp · Sorgu performansı için ipucu verdi\n"}
        self.assertEqual(oz._konu(k), "Sorgu performansı için ipucu verdi")
