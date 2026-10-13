"""Söz takibi (ag_soz), onay ucu, 'yapay zekâya gitmesin' anahtarı ve kapıya etkisi. Gerçek model çağrılmaz; sahte isimler kullanılır."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_analiz as an  # noqa: E402
import ag_cekirdek as c  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_kapi as kapi  # noqa: E402
import ag_model as mdl  # noqa: E402
import ag_soz as sz  # noqa: E402
import ag_sunucu as sunucu  # noqa: E402

BUGUN = date(2026, 10, 13)   # salı


def kisi(kid, ad, govde=None, **alan):
    c.kisi_yaz(kid, {"ad": ad, "tur": "cevre", "yakinlik": "2", **alan}, govde if govde is not None else f"# {ad}\n\n## Temas\n- (henüz yok)\n")


class SozBicimTest(unittest.TestCase):
    """Saf biçim işlevleri: dosya sistemi gerekmez."""

    def test_ekle_ve_oku(self):
        g = sz.ekle("# Ada\n\n## Temas\n- (henüz yok)\n", "ben", "kitabı göndermek", "2026-10-17", BUGUN)
        self.assertIn("## Sözler\n- [ ] 2026-10-13 · ben → o · kitabı göndermek (son: 2026-10-17)", g)
        g = sz.ekle(g, "o", "staj ilanı", "", BUGUN)
        s = sz.oku(g)
        self.assertEqual([(x["yon"], x["metin"], x["son"], x["durum"], x["sira"]) for x in s],
                         [("ben", "kitabı göndermek", "2026-10-17", "acik", 0), ("o", "staj ilanı", "", "acik", 1)])
        self.assertTrue(g.rstrip().endswith("(son: 2026-10-17)") is False)   # ikincisi sona eklendi
        self.assertIn("- [ ] 2026-10-13 · o → ben · staj ilanı\n", g + "\n")

    def test_metin_bicimi_bozamaz(self):
        g = sz.ekle("# A\n", "ben", "iki · parça (son: 2020-01-01)\nyeni satır", "", BUGUN)
        (s,) = sz.oku(g)
        self.assertEqual(s["son"], "")                      # metinden gelen "(son: ...)" gerçek son tarih olamaz
        self.assertNotIn("·", s["metin"])
        self.assertEqual(len([l for l in g.splitlines() if l.strip()]), 3)    # başlık satırı, "## Sözler", tek madde
        self.assertEqual(len(sz.metin_temizle("x" * 500)), sz.METIN_AZAMI)

    def test_gecersiz_girdiler(self):
        for yon, metin, son in (("x", "a", ""), ("ben", "  ", ""), ("ben", "kitap", "yarın"), ("o", "kitap", "2026-13-40")):
            with self.assertRaises(ValueError):
                sz.ekle("# A\n", yon, metin, son, BUGUN)

    def test_ayni_acik_soz_iki_kez_eklenmez(self):
        g = sz.ekle("# A\n", "ben", "Kitabı göndermek", "", BUGUN)
        with self.assertRaises(ValueError):
            sz.ekle(g, "ben", "kitabi gondermek", "", BUGUN)
        sz.ekle(g, "o", "kitabı göndermek", "", BUGUN)       # yön farklıysa ayrı söz

    def test_tamamla_ve_iptal_satir_silmez(self):
        g = sz.ekle(sz.ekle("# A\n", "ben", "birinci", "2026-10-17", BUGUN), "o", "ikinci", "", BUGUN)
        g = sz.kapat(g, 0, "tamam", bugun=date(2026, 10, 15))
        g = sz.kapat(g, 1, "iptal", "ikinci", date(2026, 10, 16))
        self.assertIn("- [x] 2026-10-13 · ben → o · birinci (son: 2026-10-17) (tamam: 2026-10-15)", g)
        self.assertIn("- [-] 2026-10-13 · o → ben · ikinci (iptal: 2026-10-16)", g)
        s = sz.oku(g)
        self.assertEqual([(x["durum"], x["kapanis"]) for x in s], [("tamam", "2026-10-15"), ("iptal", "2026-10-16")])
        self.assertEqual(sz.acik_sozler(g), [])
        with self.assertRaises(ValueError):
            sz.kapat(g, 0, "iptal")                            # zaten kapanmış
        with self.assertRaises(ValueError):
            sz.kapat(g, 7, "tamam")
        with self.assertRaises(ValueError):
            sz.kapat(sz.ekle("# A\n", "ben", "x yapmak", "", BUGUN), 0, "bitti")

    def test_metin_degismisse_kapatilmaz(self):
        g = sz.ekle("# A\n", "ben", "kitabı göndermek", "", BUGUN)
        with self.assertRaises(ValueError):
            sz.kapat(g, 0, "tamam", metin="başka bir söz")
        self.assertIn("[x]", sz.kapat(g, 0, "tamam", metin="Kitabı göndermek"))

    def test_taninmayan_satir_atlanir_ve_siradaki_dogru_satiri_kapatir(self):
        g = ("# A\n\n## Sözler\n- elle yazılmış serbest not\n- [ ] 2026-10-01 · ben → o · bir\n\n- [ ] 2026-10-02 · o → ben · iki\n\n## Temas\n- x\n")
        self.assertEqual([x["metin"] for x in sz.oku(g)], ["bir", "iki"])
        y = sz.kapat(g, 1, "tamam", bugun=BUGUN)
        self.assertIn("- [ ] 2026-10-01 · ben → o · bir", y)
        self.assertIn("- [x] 2026-10-02 · o → ben · iki (tamam: 2026-10-13)", y)
        self.assertIn("elle yazılmış serbest not", y)
        self.assertIn("## Temas\n- x", y)

    def test_gecikme_hesabi(self):
        s = lambda son, durum="acik": {"durum": durum, "son": son, "tarih": "2026-10-01"}
        self.assertEqual(sz.gecikme(s("2026-10-11"), BUGUN), 2)
        self.assertEqual(sz.gecikme(s("2026-10-13"), BUGUN), 0)
        self.assertEqual(sz.gecikme(s("2026-10-16"), BUGUN), -3)
        self.assertIsNone(sz.gecikme(s(""), BUGUN))
        self.assertIsNone(sz.gecikme(s("2026-10-11", "tamam"), BUGUN))
        self.assertEqual(sz.durum_yazisi(s("2026-10-11"), BUGUN), "2 gün gecikti")
        self.assertEqual(sz.durum_yazisi(s("2026-10-13"), BUGUN), "bugün")
        self.assertEqual(sz.durum_yazisi(s("2026-10-16"), BUGUN), "3 gün kaldı")
        self.assertEqual(sz.durum_yazisi(s(""), BUGUN), "12 gündür açık")


class SozVeriTest(unittest.TestCase):
    """Kişi dosyası, 'Bu hafta', onay akışı ve kapı: geçici veri klasörü."""

    def setUp(self):
        self.eski = (c.VERI, ia.DEPO, ia.AYARLAR, ia.ADAYLAR, an.SOHBET_KLASOR)
        self.t = tempfile.TemporaryDirectory()
        self.veri, self.depo = os.path.join(self.t.name, "veri"), os.path.join(self.t.name, "depo")
        os.makedirs(self.depo)
        ia.DEPO, ia.AYARLAR, ia.ADAYLAR = self.depo, os.path.join(self.depo, "ayarlar.json"), os.path.join(self.depo, "adaylar.json")
        an.SOHBET_KLASOR = os.path.join(self.depo, "sohbet")
        c.veri_klasoru(self.veri)
        c.ben_yaz({"ad": "Kerem"})
        kisi("ayse-yilmaz", "Ayşe Yılmaz")
        kisi("mehmet-kaya", "Mehmet Kaya")
        mdl.gecmis_temizle()

    def tearDown(self):
        c.veri_klasoru(self.eski[0])
        ia.DEPO, ia.AYARLAR, ia.ADAYLAR, an.SOHBET_KLASOR = self.eski[1:]
        mdl.gecmis_temizle()
        self.t.cleanup()

    def govde(self, kid):
        return c.kisi_oku(os.path.join(c.KISILER, kid + ".md"))["govde"]

    def kisiler(self):
        return c.kisileri_oku()

    # ---- kişi dosyası ----
    def test_kisi_ekle_surum_kopyalar_ve_alanlari_korur(self):
        c.kisi_yaz("ayse-yilmaz", {"ad": "Ayşe Yılmaz", "tur": "akademi", "yakinlik": "3", "kurum": "Örnek Üni", "remote_allowed": "false"}, "# Ayşe Yılmaz\n\n## Temas\n- 01.10.2026 · kahve\n")
        sz.kisi_ekle("ayse-yilmaz", "ben", "kitabı göndermek", "2026-10-17", BUGUN)
        k = c.kisi_oku(os.path.join(c.KISILER, "ayse-yilmaz.md"))
        self.assertEqual((k["tur"], k["yakinlik"], k["kurum"], k["remote_allowed"]), ("akademi", "3", "Örnek Üni", "false"))
        self.assertIn("kahve", k["govde"])
        self.assertEqual(len(sz.acik_sozler(k["govde"])), 1)
        surum = [f for f in os.listdir(os.path.join(c.ARSIV, "surum")) if f.startswith("ayse-yilmaz-")]
        self.assertEqual(len(surum), 1)
        self.assertNotIn("Sözler", open(os.path.join(c.ARSIV, "surum", surum[0]), encoding="utf-8").read())   # kopya yazım ÖNCESİ hâl
        with self.assertRaises(ValueError):
            sz.kisi_ekle("yok-boyle-biri", "ben", "x yapmak")
        with self.assertRaises(ValueError):
            sz.kisi_ekle("../x", "ben", "x yapmak")

    def test_kisi_kapat(self):
        sz.kisi_ekle("ayse-yilmaz", "o", "ilanı yollamak", "")
        sz.kisi_kapat("ayse-yilmaz", 0, "tamam", "ilanı yollamak", BUGUN)
        (s,) = sz.oku(self.govde("ayse-yilmaz"))
        self.assertEqual((s["durum"], s["kapanis"]), ("tamam", "2026-10-13"))

    # ---- Bu hafta ----
    def test_bu_hafta_soz_hatirlatmasi(self):
        g = ""
        for yon, metin, son in (("ben", "gecikmiş iş", "2026-10-11"), ("o", "yaklaşan iş", "2026-10-16"), ("ben", "uzak iş", "2026-11-30"), ("ben", "bugünkü", "2026-10-13")):
            g = sz.ekle(g, yon, metin, son, BUGUN)
        k = {"id": "ayse-yilmaz", "ad": "Ayşe", "govde": g, "yakinlik": 1}
        liste = c.bu_hafta([k], BUGUN)
        nedenler = [b["neden"] for b in liste]
        self.assertEqual(len(liste), 3)                                       # uzak iş görünmez
        self.assertTrue(all(b["tur"] == "soz" for b in liste))
        self.assertTrue(nedenler[0].startswith("verdiğin söz: 2 gün gecikti"), nedenler)   # en çok geciken başta
        self.assertTrue(nedenler[1].startswith("verdiğin söz: bugün"))
        self.assertTrue(nedenler[2].startswith("aldığın söz: 3 gün kaldı"))
        self.assertEqual([b["oncelik"] for b in liste], [-2, 0, 3])

    def test_bu_hafta_kapanan_haric_ve_tarihsiz(self):
        g = sz.ekle(sz.ekle("", "ben", "tamamlanan", "2026-10-01", BUGUN), "ben", "iptal edilen", "2026-10-01", BUGUN)
        g = sz.kapat(sz.kapat(g, 0, "tamam", bugun=BUGUN), 1, "iptal", bugun=BUGUN)
        g = sz.ekle(g, "ben", "tarihsiz yeni", "", BUGUN)                    # bugün açıldı: henüz hatırlatılmaz
        k = {"id": "ayse-yilmaz", "ad": "Ayşe", "govde": g, "yakinlik": 0}
        self.assertEqual(c.bu_hafta([k], BUGUN), [])
        eski = sz.ekle("", "o", "eski tarihsiz", "", date(2026, 9, 1))        # 42 gündür açık
        self.assertIn("42 gündür açık", c.bu_hafta([{**k, "govde": eski}], BUGUN)[0]["neden"])
        self.assertEqual(c.bu_hafta([{**k, "govde": eski, "haric": True}], BUGUN), [])
        self.assertEqual(c.bu_hafta([{**k, "govde": sz.ekle("", "ben", "geç", "2026-10-01", BUGUN), "haric": True}], BUGUN), [])

    def test_soz_pusula_ve_diger_hatirlatmalarla_karismaz(self):
        g = sz.ekle("", "ben", "rapor", "2026-10-12", BUGUN)
        k = {"id": "a", "ad": "A", "govde": g, "yakinlik": 3, "son_temas": "2026-01-01", "sonraki_adim": "ara", "sonraki_tarih": "2026-10-14"}
        liste = c.bu_hafta([k], BUGUN)
        self.assertEqual(sorted(b.get("tur", "kisi") for b in liste), ["kisi", "soz"])   # sonraki adım ayrı satır, söz ayrı satır (tur: soz)
        self.assertTrue(any("1 gün gecikti" in b["neden"] and b["tur"] == "soz" for b in liste))

    def test_veri_hazirla_sozleri_ve_kapali_isareti_tasir(self):
        gecen = (date.today() - timedelta(days=2)).isoformat()
        sz.kisi_ekle("ayse-yilmaz", "ben", "kitabı göndermek", gecen)
        sunucu.kisi_uzak({"id": "mehmet-kaya", "kapali": True})
        v = c.veri_hazirla(foto_gom=False)
        ayse = next(k for k in v["kisiler"] if k["id"] == "ayse-yilmaz")
        mehmet = next(k for k in v["kisiler"] if k["id"] == "mehmet-kaya")
        self.assertEqual(ayse["acik_soz"], 1)
        self.assertEqual((ayse["sozler"][0]["metin"], ayse["sozler"][0]["yazi"], ayse["sozler"][0]["gun"]), ("kitabı göndermek", "2 gün gecikti", 2))
        self.assertEqual((ayse["uzak_kapali"], mehmet["uzak_kapali"]), ("", "kapali"))
        (b,) = [b for b in v["bu_hafta"] if b.get("tur") == "soz"]
        self.assertEqual(b["id"], "ayse-yilmaz")
        self.assertIn("verdiğin söz: 2 gün gecikti", b["neden"])

    # ---- doğal dil ----
    def oner(self, metin, bugun=BUGUN):
        return sz.oner(metin, self.kisiler(), bugun)

    def test_olumlu_ornekler(self):
        (o,) = self.oner("Ayşe'ye kitabı cuma göndereceğim")
        self.assertEqual((o["kisi"], o["yon"], o["metin"], o["son"]), ("ayse-yilmaz", "ben", "kitabı göndereceğim", "2026-10-16"))
        self.assertEqual(o["soru"], "Ayşe'ye söz olarak ekleyeyim mi? (son: 16.10)")
        (o,) = self.oner("Mehmet bana staj ilanını yollayacak")
        self.assertEqual((o["kisi"], o["yon"], o["metin"], o["son"]), ("mehmet-kaya", "o", "staj ilanını yollayacak", ""))
        (o,) = self.oner("Ayşe Yılmaz'a haftaya cuma raporu göndereceğim")
        self.assertEqual((o["kisi"], o["yon"], o["metin"], o["son"]), ("ayse-yilmaz", "ben", "raporu göndereceğim", "2026-10-23"))
        self.assertEqual(self.oner("Ayşe Yılmaz'a raporu göndermem gerek"), [])      # gereklilik ("-mam gerek", "-meli", "lazım") açık taahhüt değildir

    def test_goreli_tarihler(self):
        durum = {"Ayşe'ye yarın kitabı göndereceğim": "2026-10-14", "Ayşe'ye haftaya kitabı göndereceğim": "2026-10-20",
                 "Ayşe'ye ay sonuna kadar kitabı göndereceğim": "2026-10-31", "Ayşe'ye kitabı 3 gün sonra göndereceğim": "2026-10-16",
                 "Ayşe'ye kitabı 17 Ekim'e kadar göndereceğim": "2026-10-17", "Ayşe'ye kitabı 17.10 göndereceğim": "2026-10-17",
                 "Ayşe'ye kitabı 2026-11-02 göndereceğim": "2026-11-02", "Ayşe'ye hafta sonu kitabı göndereceğim": "2026-10-18",
                 "Ayşe'ye kitabı bugün göndereceğim": "2026-10-13", "Ayşe'ye kitabı salı göndereceğim": "2026-10-20",
                 "Ayşe'ye kitabı göndereceğim, cuma.": "2026-10-16", "Ayşe'ye kitabı 5 Ekim'de göndereceğim": "2027-10-05",
                 "Ayşe'ye kitabı göndereceğim": ""}
        for cumle, beklenen in durum.items():
            o = self.oner(cumle)
            self.assertEqual(len(o), 1, cumle)
            self.assertEqual(o[0]["son"], beklenen, cumle)
            self.assertEqual(o[0]["metin"], "kitabı göndereceğim", cumle)

    def test_soru_olumsuz_gecmis_ve_kosul_oneri_uretmez(self):
        for cumle in ("Ayşe'ye kitabı göndermeli miyim?", "Ayşe'ye kitabı ne zaman göndereceğim", "Ayşe'ye kitabı göndermeyeceğim",
                      "Ayşe'ye kitabı gönderemem", "Ayşe'ye kitabı göndermem", "Ayşe'ye kitabı göndermiyorum", "Ayşe'ye kitabı gönderdim",
                      "Geçen hafta Ayşe'ye kitabı göndereceğimi söylemiştim", "Ayşe bana kitabı gönderecekti", "Dün Ayşe'ye kitabı göndereceğim demiştim",
                      "Keşke Ayşe'ye kitabı göndereceğim desem", "Ayşe'ye kitabı göndersem mi", "Ayşe'ye kitabı göndereceğim, doğru mu? Bilmiyorum?",
                      "Ayşe'ye kitabı göndereceğim diye bir şey yok", "Ayşe'yi aradım", "Yarın hava güzel olacak", "Ayşe'ye kitabı dün göndereceğim"):
            self.assertEqual(self.oner(cumle), [], cumle)
        self.assertEqual(self.oner("Ayşe'ye kitabı 1 Ocak 2020'ye kadar göndereceğim"), [])    # açık geçmiş tarih
        self.assertEqual(self.oner("Mehmet bana staj ilanını yollamayacak"), [])
        self.assertEqual(self.oner(""), [])

    def test_ad_belirsizse_oneri_yok(self):
        kisi("ayse-demir", "Ayşe Demir")
        self.assertEqual(self.oner("Ayşe'ye kitabı cuma göndereceğim"), [])                    # iki Ayşe
        (o,) = self.oner("Ayşe Demir'e kitabı cuma göndereceğim")
        self.assertEqual(o["kisi"], "ayse-demir")
        self.assertEqual(self.oner("Ayşe'ye ve Mehmet'e kitabı göndereceğim"), [])             # iki kişi
        self.assertEqual(self.oner("Zeynep'e kitabı göndereceğim"), [])                        # ağda yok

    def test_haric_kisi_oneri_almaz_ve_ben_sayilmaz(self):
        with open(c.HARIC, "a", encoding="utf-8") as f:
            f.write("- Örnek Parti\n")
        kisi("parti-uyesi", "Ece Parti", kurum="Örnek Parti")
        self.assertEqual(self.oner("Ece'ye kitabı göndereceğim"), [])
        self.assertEqual(self.oner("Kerem'e kitabı göndereceğim"), [])

    def test_iki_soz_tek_mesajda(self):
        o = self.oner("Ayşe'ye kitabı cuma göndereceğim, Mehmet bana yarın dosyayı yollayacak.")
        self.assertEqual([(x["kisi"], x["yon"], x["son"]) for x in o], [("ayse-yilmaz", "ben", "2026-10-16"), ("mehmet-kaya", "o", "2026-10-14")])
        self.assertEqual(len(self.oner(". ".join(f"Ayşe'ye {x} göndereceğim" for x in ("elmayı", "armudu", "kitabı", "dergiyi", "kalemi", "çantayı", "defteri", "saati", "anahtarı")))), sz.ONERI_AZAMI)

    def test_oneri_hicbir_sey_yazmaz(self):
        once = open(os.path.join(c.KISILER, "ayse-yilmaz.md"), encoding="utf-8").read()
        sunucu.soz_onerisi("Ayşe'ye kitabı cuma göndereceğim")
        self.assertEqual(open(os.path.join(c.KISILER, "ayse-yilmaz.md"), encoding="utf-8").read(), once)
        self.assertFalse(os.path.isdir(os.path.join(c.ARSIV, "surum")) and os.listdir(os.path.join(c.ARSIV, "surum")))

    # ---- sohbet akışı ve onay ucu ----
    def sor(self, soru, kayitlar=None):
        sahte = {"cevap": "Tamam.", "oturum": "s", "oneri": 0, "kayitlar": kayitlar or []}
        with mock.patch.object(sunucu.an, "sohbet", return_value=sahte):
            return sunucu.sor({"soru": soru, "kisi": "", "oturum": ""})

    def test_sor_soz_onerir_ama_yazmaz(self):
        r = self.sor("Ayşe'ye kitabı cuma göndereceğim")
        self.assertEqual(len(r["soz_onay"]), 1)
        self.assertEqual(r["soz_onay"][0]["kisi"], "ayse-yilmaz")
        self.assertIn("söz olarak ekleyeyim mi?", r["soz_onay"][0]["soru"])
        self.assertEqual(r["kaydedilen"], [])
        self.assertEqual(sz.oku(self.govde("ayse-yilmaz")), [])
        self.assertNotIn("soz_onay", self.sor("Ayşe'ye kitabı göndermeyeceğim"))
        self.assertNotIn("soz_onay", self.sor("Ayşe'ye kitabı göndermeli miyim?"))

    def test_modelin_soz_kaydi_yazilmaz_onay_onerisi_olur(self):
        model = [{"kisi": "mehmet-kaya", "islem": "soz", "yon": "o", "metin": "tez dosyasını yollamak", "tarih": "2026-10-20"},
                 {"kisi": "yok-biri", "islem": "soz", "yon": "o", "metin": "geçersiz kişi"},
                 {"kisi": "ayse-yilmaz", "islem": "soz", "yon": "x", "metin": "geçersiz yön"},
                 {"kisi": "ayse-yilmaz", "islem": "beyan", "metin": "Bölümde asistan."}]
        r = self.sor("Mehmet'le konuştum", model)
        self.assertEqual([(o["kisi"], o["yon"], o["son"]) for o in r["soz_onay"]], [("mehmet-kaya", "o", "2026-10-20")])
        self.assertEqual(sz.oku(self.govde("mehmet-kaya")), [])                  # söz yazılmadı
        self.assertTrue(any("beyan" in x for x in r["kaydedilen"]))              # diğer kayıtlar eskisi gibi
        self.assertFalse(any("soz" in a for a in r["atlanan"]))

    def test_zaten_acik_soz_tekrar_onerilmez(self):
        sz.kisi_ekle("ayse-yilmaz", "ben", "kitabı göndereceğim", "")
        self.assertNotIn("soz_onay", self.sor("Ayşe'ye kitabı göndereceğim"))

    def test_onay_ucu_yazar_ve_dogrular(self):
        r = sunucu.soz_onayla({"kisi": "ayse-yilmaz", "yon": "ben", "metin": "kitabı göndermek", "son": "2026-10-17", "oturum": "abc"})
        self.assertIn("Ayşe Yılmaz için söz kaydedildi", r["cevap"])
        self.assertEqual(r["oturum"], "abc")
        (s,) = sz.oku(self.govde("ayse-yilmaz"))
        self.assertEqual((s["yon"], s["metin"], s["son"]), ("ben", "kitabı göndermek", "2026-10-17"))
        for kotu in ({"kisi": "yok-biri", "yon": "ben", "metin": "abc def"}, {"kisi": "ayse-yilmaz", "yon": "z", "metin": "abc def"},
                     {"kisi": "ayse-yilmaz", "yon": "ben", "metin": "ab"}, {"kisi": "ayse-yilmaz", "yon": "ben", "metin": "abc def", "son": "yarın"},
                     {"kisi": "../etc", "yon": "ben", "metin": "abc def"}, {}, "metin"):
            with self.assertRaises(ValueError, msg=kotu):
                sunucu.soz_onayla(kotu)
        with self.assertRaises(ValueError):
            sunucu.soz_onayla({"kisi": "ayse-yilmaz", "yon": "ben", "metin": "kitabı göndermek"})   # zaten açık
        self.assertEqual(len(sz.oku(self.govde("ayse-yilmaz"))), 1)

    def test_onay_ucu_haric_kisiye_yazmaz(self):
        with open(c.HARIC, "a", encoding="utf-8") as f:
            f.write("- Örnek Parti\n")
        kisi("parti-uyesi", "Ece Parti", kurum="Örnek Parti")
        with self.assertRaises(ValueError):
            sunucu.soz_onayla({"kisi": "parti-uyesi", "yon": "ben", "metin": "kitap göndermek"})
        with self.assertRaises(ValueError):
            sunucu.soz_ekle({"id": "parti-uyesi", "yon": "ben", "metin": "kitap göndermek"})

    def test_soz_ekle_ve_durum_uclari(self):
        sunucu.soz_ekle({"id": "mehmet-kaya", "yon": "o", "metin": "ilanı yollamak", "son": "2026-10-20"})
        sunucu.soz_durum({"id": "mehmet-kaya", "sira": 0, "metin": "ilanı yollamak", "durum": "iptal"})
        (s,) = sz.oku(self.govde("mehmet-kaya"))
        self.assertEqual(s["durum"], "iptal")
        with self.assertRaises(ValueError):
            sunucu.soz_durum({"id": "mehmet-kaya", "sira": 0, "durum": "tamam"})
        with self.assertRaises(ValueError):
            sunucu.soz_durum({"id": "yok", "sira": 0, "durum": "tamam"})

    def test_uclar_kilit_anahtar_ve_koken_arkasinda(self):
        for yol in ("/api/soz", "/api/soz/durum", "/api/soz/onayla", "/api/kisi/uzak"):
            self.assertIn(yol, sunucu.ISLEMLER)                # yalnız do_POST'ta çözülür: GET'te yok, kilit + X-Ag-Anahtar denetiminden sonra
            self.assertNotIn(yol, sunucu.KILITSIZ)
        for yol in ("/api/soz/onayla", "/api/kisi/uzak"):
            self.assertIn(yol, sunucu.KOKEN_DENETIMLI)         # anahtara ek olarak Origin bu sunucudan gelmeli
        isl = sunucu.Isleyici.__new__(sunucu.Isleyici)
        isl.headers = {"Origin": "http://evil.example"}
        self.assertFalse(isl._koken_ok())
        isl.headers = {"Origin": f"http://127.0.0.1:{sunucu.PORT}"}
        self.assertTrue(isl._koken_ok())

    # ---- kapı: sözler ve remote_allowed anahtarı ----
    def dosyalar(self, kok):
        return {os.path.relpath(os.path.join(y, f), kok).replace("\\", "/") for y, _, fs in os.walk(kok) for f in fs}

    def sohbet_istemi(self, kisi_id=""):
        yakalanan = {}

        def sahte(arg, **kw):
            yakalanan["istem"] = kw["input"].decode("utf-8")
            yakalanan["dosyalar"] = self.dosyalar(arg[arg.index("--add-dir") + 1])
            yakalanan["kopya"] = {}
            d = arg[arg.index("--add-dir") + 1]
            for f in yakalanan["dosyalar"]:
                if f.endswith(".md"):
                    yakalanan["kopya"][f] = open(os.path.join(d, f), encoding="utf-8").read()
            return subprocess.CompletedProcess(arg, 0, json.dumps({"result": "tamam", "session_id": "s"}).encode(), b"")
        with mock.patch.object(mdl, "yol_bul", return_value="claude"), mock.patch.object(mdl, "hazir", return_value=True), mock.patch.object(mdl.subprocess, "run", side_effect=sahte):
            an.sohbet("Kimle görüşeyim?", kisi_id, "")
        return yakalanan

    def test_acik_kisinin_sozu_sohbet_baglamina_girer(self):
        sz.kisi_ekle("ayse-yilmaz", "ben", "gizlilik-testi-kitap", "2026-10-17")
        y = self.sohbet_istemi()
        self.assertIn("açık söz", y["istem"])
        self.assertIn("gizlilik-testi-kitap", y["istem"])
        self.assertIn("gizlilik-testi-kitap", y["kopya"]["kisiler/ayse-yilmaz.md"])      # kopyada kişi dosyasıyla birlikte
        y = self.sohbet_istemi("ayse-yilmaz")
        self.assertIn("gizlilik-testi-kitap", y["istem"])

    def test_anahtar_kapatinca_kisi_ve_sozleri_kapidan_gecmez(self):
        sz.kisi_ekle("ayse-yilmaz", "ben", "gizlilik-testi-kitap", "2026-10-17")
        sz.kisi_ekle("mehmet-kaya", "o", "baska-kisi-sozu", "")
        self.assertTrue(kapi.Kapi().acik_mi("ayse-yilmaz"))
        r = sunucu.kisi_uzak({"id": "ayse-yilmaz", "kapali": True})
        self.assertEqual((r["kapali"], r["oturum_sifirla"]), (True, True))
        k = c.kisi_oku(os.path.join(c.KISILER, "ayse-yilmaz.md"))
        self.assertEqual(k["remote_allowed"], "false")
        self.assertIn("gizlilik-testi-kitap", k["govde"])                                   # yerelde duruyor
        self.assertFalse(kapi.Kapi().acik_mi("ayse-yilmaz"))
        self.assertTrue(kapi.Kapi().acik_mi("mehmet-kaya"))
        with kapi.kopya() as kok:
            d = self.dosyalar(kok)
            self.assertNotIn("kisiler/ayse-yilmaz.md", d)
            self.assertIn("kisiler/mehmet-kaya.md", d)
            tum = "\n".join(open(os.path.join(kok, f), encoding="utf-8").read() for f in d if f.endswith(".md"))
        self.assertNotIn("gizlilik-testi-kitap", tum)
        self.assertNotIn("Ayşe Yılmaz", tum)
        y = self.sohbet_istemi()
        self.assertNotIn("gizlilik-testi-kitap", y["istem"])
        self.assertNotIn("Ayşe", y["istem"])
        self.assertIn("baska-kisi-sozu", y["istem"])
        self.assertNotIn("kisiler/ayse-yilmaz.md", y["dosyalar"])
        y = self.sohbet_istemi("ayse-yilmaz")
        self.assertNotIn("gizlilik-testi-kitap", y["istem"])
        self.assertIn("gizlilik", y["istem"])

    def test_anahtar_gecmisi_temizler_ve_imza_degisir(self):
        mdl.gecmis_ekle("oturum-1", "Ayşe ile ne konuştuk?", "kitap")
        mdl.gecmis_ekle("oturum-2", "başka", "cevap")
        sunucu.kisi_uzak({"id": "ayse-yilmaz", "kapali": True})
        self.assertEqual(mdl.gecmis_al("oturum-1"), [])
        self.assertEqual(mdl.gecmis_al("oturum-2"), [])
        # sunucu ucu olmadan (dosyayı elle düzenleyince) da: kapı imzası değiştiği için sonraki sohbet turu geçmişi siler
        kisi("mehmet-kaya", "Mehmet Kaya", remote_allowed="false")
        imza = lambda: (mdl.secili(), tuple(sorted(kapi.Kapi().red)), tuple(sorted(str(h) for h in c.haric_listesi())))
        sunucu.kisi_uzak({"id": "mehmet-kaya", "kapali": False})
        mdl.gecmis_imza_denetle(imza())
        mdl.gecmis_ekle("oturum-3", "s", "c")
        mdl.gecmis_imza_denetle(imza())
        self.assertEqual(mdl.gecmis_al("oturum-3"), [("s", "c")])                           # kapı aynı: geçmiş durur
        c.kisi_yaz("mehmet-kaya", {"ad": "Mehmet Kaya", "tur": "cevre", "yakinlik": "2", "remote_allowed": "false"}, "# M\n")
        mdl.gecmis_imza_denetle(imza())
        self.assertEqual(mdl.gecmis_al("oturum-3"), [])

    def test_anahtar_claude_oturumunu_sunucuda_iptal_eder(self):
        """Denetim O: 🔒 sonrası eski Claude konuşması (o kişinin kartını bağlamında taşır) istemci sıfırlamasa da --resume edilmez."""
        oid = "0123456789abcdef0123456789abcdef"
        mdl._claude_oturumlar.clear()
        mdl._claude_iptal.clear()
        mdl._claude_oturumlar[oid] = True
        self.assertTrue(mdl.claude_oturum_gecerli(oid))
        sunucu.kisi_uzak({"id": "ayse-yilmaz", "kapali": True})
        self.assertFalse(mdl.claude_oturum_gecerli(oid))
        # elle düzenleme (haric.md / remote_allowed) ile kapı imzası değişirse de sonraki tur eski oturumu bırakır
        oid2 = "fedcba9876543210fedcba9876543210"
        mdl.gecmis_imza_denetle(("claude", ("a",), ()))
        mdl._claude_oturumlar[oid2] = True
        mdl.gecmis_imza_denetle(("claude", ("a",), ()))
        self.assertTrue(mdl.claude_oturum_gecerli(oid2))                                    # kapı aynı: oturum sürer
        mdl.gecmis_imza_denetle(("claude", ("a", "b"), ()))
        self.assertFalse(mdl.claude_oturum_gecerli(oid2))
        mdl._claude_oturumlar.clear()
        mdl._claude_iptal.clear()

    def test_anahtar_acilinca_kisi_yeniden_gidebilir_ve_alan_kalkar(self):
        sunucu.kisi_uzak({"id": "ayse-yilmaz", "kapali": True})
        sunucu.kisi_uzak({"id": "ayse-yilmaz", "kapali": False})
        self.assertNotIn("remote_allowed", c.kisi_oku(os.path.join(c.KISILER, "ayse-yilmaz.md")))
        self.assertTrue(kapi.Kapi().acik_mi("ayse-yilmaz"))
        self.assertEqual(len([f for f in os.listdir(os.path.join(c.ARSIV, "surum")) if f.startswith("ayse-yilmaz-")]), 2)   # her yazım öncesi kopya
        for kotu in (None, "true", 1, "false"):
            with self.assertRaises(ValueError):
                sunucu.kisi_uzak({"id": "ayse-yilmaz", "kapali": kotu})
        with self.assertRaises(ValueError):
            sunucu.kisi_uzak({"id": "yok-biri", "kapali": True})

    def test_kapali_kisi_icin_analiz_ve_belge_ozeti_uzak_modele_gitmez(self):
        sunucu.kisi_uzak({"id": "ayse-yilmaz", "kapali": True})
        with self.assertRaises(ValueError):
            sunucu.analiz_baslat({"id": "ayse-yilmaz"})
        with mock.patch.object(mdl, "hazir", return_value=True), mock.patch.object(sunucu.an, "belge_kuyruga_ekle") as kuyruk:
            r = sunucu.belge_ekle({"id": "ayse-yilmaz", "metin": "özgeçmiş metni"})
            self.assertEqual((r["analiz"], r["uzak_kapali"]), (False, True))
            kuyruk.assert_not_called()
            self.assertTrue(os.path.exists(os.path.join(c.BELGELER, "ayse-yilmaz", r["dosya"])))      # belge yerelde saklandı
            r = sunucu.belge_ekle({"id": "mehmet-kaya", "metin": "özgeçmiş metni"})
            self.assertEqual((r["analiz"], r["uzak_kapali"]), (True, False))
            kuyruk.assert_called_once()

    def test_sohbette_kapali_kisiye_soz_onerisi_yine_yerel_calisir(self):
        # sözü yerel ayrıştırmak model çağrısı gerektirmez; kişi yapay zekâya gitmese de kullanıcı kendi sözünü kaydedebilir
        sunucu.kisi_uzak({"id": "ayse-yilmaz", "kapali": True})
        (o,) = sz.oner("Ayşe'ye kitabı cuma göndereceğim", c.kisileri_oku(), BUGUN)
        self.assertEqual(o["kisi"], "ayse-yilmaz")
        sunucu.soz_onayla(o)
        self.assertEqual(len(sz.oku(self.govde("ayse-yilmaz"))), 1)
        self.assertFalse(kapi.Kapi().acik_mi("ayse-yilmaz"))


if __name__ == "__main__":
    unittest.main()
