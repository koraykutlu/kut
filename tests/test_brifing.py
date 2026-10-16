"""Görüşme öncesi brifing (ag_brifing): saf işlev, dosya sistemi gerekmez. Kurgusal adlar; ag_yol/ag_sonuc/ag_hedef/ag_strateji sahte modüllerle verilir."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import copy
import json
import os
import re
import sys
import types
import unittest
from datetime import date, datetime
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_brifing as br  # noqa: E402
import ag_cekirdek as c  # noqa: E402
import ag_soz as sz  # noqa: E402

BUGUN = date(2026, 10, 15)

SELIN_GOVDE = """# Selin Hoca

## Temas
- 03.03.2026 · yüz yüze · Kahve içtik, açık veri çağrısından bahsettik
- 20.06.2026 · Toplantıdan sonra kısa konuştuk
- 11.09.2026 · WhatsApp · Çağrı metnini gönderdi
- 31.02.2026 · e-posta · geçersiz tarihli satır atlanır

## Sözler
- [ ] 2026-09-20 · ben → o · çağrı metnine yorum göndermek (son: 2026-10-10)
- [ ] 2026-09-25 · ben → o · kitabı vermek (son: 2026-10-30)
- [ ] 2026-09-01 · o → ben · staj ilanını yollamak (son: 2026-10-12)
- [x] 2026-08-01 · ben → o · eski söz (tamam: 2026-08-05)

## Senin beyanların
- 01.10.2026 · Selin Hoca ile ayda bir görüşmek istiyorum (Umut, Kut sohbeti)
"""


def kisi(kid, ad, **alan):
    k = {"id": kid, "ad": ad, "tur": "cevre", "kurum": "", "rol": "", "alan": [], "etiketler": [], "nereden": [], "yakinlik": 1, "son_temas": "",
         "etkin_son_temas": "", "sonraki_adim": "", "sonraki_tarih": "", "neden_onemli": "", "ne_verebilirim": "", "kullanici_gorusu": "",
         "haric": False, "govde": f"# {ad}\n\n## Temas\n- (henüz yok)\n", "puan": {}}
    k.update(alan)
    return k


def veri_yap(kisiler, iliskiler=(), dikkatler=(), ilgiler=()):
    merkez = {"id": "umut", "ad": "Umut", "tur": "cevre", "yakinlik": 0, "govde": "", "haric": False}
    return {"kisiler": [merkez] + list(kisiler), "iliskiler": list(iliskiler), "dikkatler": list(dikkatler),
            "ben": {"id": "umut", "ad": "Umut", "ilgiler": list(ilgiler)}, "bu_hafta": []}


def selin(**alan):
    return kisi("selin-hoca", "Selin Hoca", tur="akademi", kurum="Yeditepe Üniversitesi", rol="Doçent", yakinlik=2,
                alan=["veri görselleştirme", "açık veri"], etiketler=["yapay-zeka"], nereden=["Yeditepe", "linkedin", "yeditepe"],
                son_temas="2026-09-11", etkin_son_temas="2026-09-11", sonraki_adim="Açık veri çağrısı için yaz", sonraki_tarih="2026-10-18",
                neden_onemli="Açık veri çağrısının değerlendirme kurulunda.", ne_verebilirim="Veri görselleştirme atölyesi",
                kullanici_gorusu="Dürüst ve işini bilen biri.", puan={"sicaklik": 41, "_trend": "soğuyor"}, govde=SELIN_GOVDE, **alan)


def sahte_modul(ad, **islevler):
    m = types.ModuleType(ad)
    for k, v in islevler.items():
        setattr(m, k, v)
    return m


class TemasAyristirmaTest(unittest.TestCase):
    def test_kanalli_kanalsiz_ve_gecersiz_satirlar(self):
        t = br.temaslar(SELIN_GOVDE)
        self.assertEqual([(x["tarih"], x["kanal"]) for x in t],
                         [("2026-03-03", "yüz yüze"), ("2026-06-20", ""), ("2026-09-11", "WhatsApp")])
        self.assertEqual(t[1]["metin"], "Toplantıdan sonra kısa konuştuk")
        self.assertEqual(t[0]["metin"], "Kahve içtik, açık veri çağrısından bahsettik")

    def test_henuz_yok_ve_bos_govde(self):
        self.assertEqual(br.temaslar("# A\n\n## Temas\n- (henüz yok)\n"), [])
        self.assertEqual(br.temaslar(""), [])
        self.assertEqual(br.temaslar(None), [])
        self.assertEqual(br.temaslar("# A\n\n## Sözler\n- 11.09.2026 · temas değil\n"), [])   # yalnız temas bölümü

    def test_metinde_orta_nokta_ve_bilinmeyen_kanal(self):
        t = br.temaslar("## Temas\n- 01.02.2026 · telefon · konu a · konu b\n- 02.02.2026 · Slack · ilk · ikinci\n- 03.02.2026 · Slack · kısa not\n")
        self.assertEqual((t[0]["kanal"], t[0]["metin"]), ("telefon", "konu a · konu b"))
        self.assertEqual((t[1]["kanal"], t[1]["metin"]), ("Slack", "ilk · ikinci"))          # üç parça: ilk parça kanal (bilinmese de)
        self.assertEqual((t[2]["kanal"], t[2]["metin"]), ("", "Slack · kısa not"))          # iki parça, bilinmeyen ilk parça: kanal sayılmaz

    def test_ozel_temas_basligi(self):
        self.assertEqual(len(br.temaslar("## Görüşme temas\n- 05.05.2026 · notlar\n")), 1)


class TamDoluKisiTest(unittest.TestCase):
    def setUp(self):
        self.veri = veri_yap([selin()], ilgiler=["Açık veri", "Müzik"])
        self.b = br.brifing(self.veri, "selin-hoca", BUGUN, sonuclar=[], hedefler=[], strateji={})

    def test_kisi_ve_temel_alanlar(self):
        b = self.b
        self.assertEqual(b["kisi"], {"id": "selin-hoca", "ad": "Selin Hoca", "tur": "akademi", "tur_ad": "Akademi", "kurum": "Yeditepe Üniversitesi",
                                     "rol": "Doçent", "yakinlik": 2, "yakinlik_yazi": "Görüştük"})
        self.assertEqual(b["neden_onemli"], "Açık veri çağrısının değerlendirme kurulunda.")
        self.assertEqual(b["ne_verebilirim"], "Veri görselleştirme atölyesi")
        self.assertEqual(b["senin_gorusun"], "Dürüst ve işini bilen biri.")
        self.assertEqual(b["beyanlar"], ["01.10.2026 · Selin Hoca ile ayda bir görüşmek istiyorum (Umut, Kut sohbeti)"])
        self.assertEqual(b["uretildi"], "2026-10-15")

    def test_ozet_somut_ve_puansiz(self):
        o = self.b["ozet"]
        self.assertEqual(o, "Selin Hoca (Yeditepe Üniversitesi, Doçent) ile yakınlığınız 2; son temas 34 gün önce, bağ soğuyor. "
                            "Verdiğin bir söz gecikmiş durumda.")
        self.assertNotRegex(o, r"\d+\s*/\s*100|puan")

    def test_son_temaslar_en_yeni_once(self):
        self.assertEqual([(t["tarih"], t["kanal"]) for t in self.b["son_temaslar"]],
                         [("2026-09-11", "WhatsApp"), ("2026-06-20", ""), ("2026-03-03", "yüz yüze")])

    def test_sicaklik_ve_sonraki(self):
        self.assertEqual(self.b["sicaklik"], {"deger": 41, "trend": "soğuyor", "son_temas_gun": 34, "bag": "soğuyor"})
        self.assertEqual(self.b["sonraki"], {"adim": "Açık veri çağrısı için yaz", "tarih": "2026-10-18", "gun": 3, "yazi": "3 gün kaldı"})

    def test_nasil_tanistiniz(self):
        self.assertEqual(self.b["nasil_tanistiniz"], "Nereden: Yeditepe, linkedin. İlk kayıtlı temas: 03.03.2026.")

    def test_konusma_oncelik_sirasi(self):
        k = self.b["konusma"]
        self.assertEqual(len(k), 6)
        self.assertTrue(k[0].startswith("Gecikmiş bir sözün var: «çağrı metnine yorum göndermek» (5 gün gecikti)"))
        self.assertTrue(k[1].startswith("Selin Hoca sana bir söz vermişti: «staj ilanını yollamak» (3 gün gecikti). Nazikçe hatırlat"))
        self.assertTrue(k[2].startswith("Planladığın sonraki adım: Açık veri çağrısı için yaz (3 gün kaldı)"))
        self.assertIn("Geçen sefer (11.09.2026) şunu konuşmuşsunuz: «Çağrı metnini gönderdi»", k[3])
        self.assertIn("Ortak zemin: ikiniz de Açık veri ile ilgileniyorsunuz", k[4])
        self.assertIn("Veri görselleştirme atölyesi", k[5])

    def test_markdown_tam(self):
        md = br.markdown(self.b)
        for parca in ("# Brifing: Selin Hoca", "Akademi · Yeditepe Üniversitesi · Doçent · Yakınlık 2 (Görüştük)", "## Görüşmede konuşabileceklerin",
                      "## Açık sözler", "**Sen verdin**", "**O verdi**", "## Sonraki adım", "## Son temaslar", "## Nasıl tanıştınız",
                      "## Neden önemli", "## Ona ne verebilirsin", "## Senin görüşün", "## Senin beyanların", "11.09.2026 · WhatsApp · Çağrı metnini gönderdi",
                      "1. Gecikmiş bir sözün var", "Kut ile hazırlandı · 15.10.2026"):
            self.assertIn(parca, md)
        for bos in ("## Ortak tanıdıklar", "## Dikkat", "## Hedeflerinle bağı", "## Strateji okumasında", "## Kut'un geçmiş önerileri", "## Ulaşma yolu"):
            self.assertNotIn(bos, md)
        self.assertLess(md.index("## Görüşmede konuşabileceklerin"), md.index("## Son temaslar"))

    def test_veri_degismez(self):
        veri = veri_yap([selin()], ilgiler=["Açık veri"])
        once = copy.deepcopy(veri)
        br.brifing(veri, "selin-hoca", BUGUN, sonuclar=[], hedefler=[], strateji=None)
        self.assertEqual(veri, once)


class BosKisiTest(unittest.TestCase):
    def test_neredeyse_bos_kisi_madde_uretmez(self):
        b = br.brifing(veri_yap([kisi("ayse-yilmaz", "Ayşe Yılmaz")]), "ayse-yilmaz", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertEqual(b["ozet"], "Ayşe Yılmaz ile yakınlığınız 1; kayıtlı temas yok.")
        self.assertEqual(b["konusma"], [])
        self.assertEqual((b["son_temaslar"], b["beyanlar"], b["dikkat"], b["hedefler"], b["strateji"], b["gecmis"], b["ortak_tanidiklar"]),
                         ([], [], [], [], [], [], []))
        self.assertEqual(b["sozler"], {"senin": [], "onun": []})
        self.assertEqual(b["sonraki"], {"adim": "", "tarih": "", "gun": None, "yazi": ""})
        self.assertEqual((b["nasil_tanistiniz"], b["neden_onemli"], b["ne_verebilirim"], b["senin_gorusun"]), ("", "", "", ""))
        self.assertEqual(b["sicaklik"], {"deger": None, "trend": "", "son_temas_gun": None, "bag": ""})
        self.assertIsNone(b["yol"])

    def test_bos_kisinin_markdown_bos_bolum_icermez(self):
        md = br.markdown(br.brifing(veri_yap([kisi("ayse-yilmaz", "Ayşe Yılmaz")]), "ayse-yilmaz", BUGUN, sonuclar=[], hedefler=[], strateji={}))
        self.assertTrue(md.startswith("# Brifing: Ayşe Yılmaz"))
        self.assertNotIn("##", md)
        self.assertNotIn("\n\n\n", md)

    def test_hicbir_markdown_bolumu_bos_degil(self):
        veri = veri_yap([selin(), kisi("elif-demir", "Elif Demir", yakinlik=3)],
                        iliskiler=[{"a": "selin-hoca", "b": "elif-demir", "tip": "arkadas", "not": "", "kaynak": "", "tarih": ""}],
                        dikkatler=[{"kisiler": ["selin-hoca"], "seviye": "orta", "metin": "Sen ile Selin Hoca aranda: gerginlik."}])
        md = br.markdown(br.brifing(veri, "selin-hoca", BUGUN, sonuclar=[{"no": 1, "tarih": "2026-10-01", "kaynak": "ozet", "kisi": "selin-hoca",
                                                                         "oneri": "Selam yaz", "sonuc": "yaptim", "not": "", "kapanis": ""}],
                                    hedefler=[], strateji={}))
        satirlar = md.split("\n")
        for i, s in enumerate(satirlar):
            if s.startswith("## "):
                sonraki = next((x for x in satirlar[i + 1:] if x.strip()), "")
                self.assertTrue(sonraki and not sonraki.startswith("#") and sonraki != "---", f"boş bölüm: {s}")


class HataTest(unittest.TestCase):
    def setUp(self):
        self.veri = veri_yap([selin(), kisi("mehmet-kaya", "Mehmet Kaya", haric=True)])

    def test_haric_kisi(self):
        with self.assertRaises(ValueError) as h:
            br.brifing(self.veri, "mehmet-kaya", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertEqual(str(h.exception), "Bu kişi hariç listende.")

    def test_olmayan_kisi_ve_merkez(self):
        for kid in ("yok-kimse", "", None, "umut"):
            with self.assertRaises(ValueError) as h:
                br.brifing(self.veri, kid, BUGUN, sonuclar=[], hedefler=[], strateji={})
            self.assertEqual(str(h.exception), "kişi bulunamadı")

    def test_bos_veri(self):
        with self.assertRaises(ValueError):
            br.brifing({}, "x", BUGUN, sonuclar=[], hedefler=[], strateji={})


class HaricSizintisiTest(unittest.TestCase):
    def test_hic_bir_alanda_haric_ad_gorunmez(self):
        veri = veri_yap(
            [selin(), kisi("mehmet-kaya", "Mehmet Kaya", haric=True, yakinlik=3), kisi("elif-demir", "Elif Demir", yakinlik=2)],
            iliskiler=[{"a": "selin-hoca", "b": "mehmet-kaya", "tip": "arkadas", "not": "", "kaynak": "", "tarih": ""},
                       {"a": "selin-hoca", "b": "elif-demir", "tip": "birlikte-calisiyor", "not": "", "kaynak": "", "tarih": ""}],
            dikkatler=[{"kisiler": ["selin-hoca", "mehmet-kaya"], "seviye": "orta", "metin": "Selin Hoca – Mehmet Kaya arasında: rakip."},
                       {"kisiler": ["selin-hoca"], "seviye": "dusuk", "metin": "Mehmet Kaya ile ilgili bir not."},
                       {"kisiler": ["selin-hoca", "elif-demir"], "seviye": "dusuk", "metin": "Selin Hoca – Elif Demir: birlikte çalışıyor. Referansları bağımsız sayılmaz."}])
        hedefler = [{"id": "h1", "baslik": "Mehmet Kaya ile ortak proje", "durum": "aktif", "govde": "Selin Hoca ile konuş"},
                    {"id": "h2", "baslik": "Açık veri çağrısı", "durum": "aktif", "govde": "Selin Hoca değerlendirecek"}]
        sonuclar = [{"no": 1, "tarih": "2026-10-01", "kaynak": "yol", "kisi": "selin-hoca", "oneri": "Mehmet Kaya üzerinden yaz", "sonuc": "atlandi", "not": "", "kapanis": ""},
                    {"no": 2, "tarih": "2026-10-02", "kaynak": "ozet", "kisi": "selin-hoca", "oneri": "Selam yaz", "sonuc": "yaptim", "not": "Mehmet Kaya da duydu", "kapanis": ""}]
        strateji = {"hamleler": [{"hedef": "h2", "baslik": "Mehmet Kaya'yı da çağıran hamle", "kim": "selin-hoca", "kanit": ["selin-hoca"], "sonuc": ""},
                                 {"hedef": "h2", "baslik": "Selin Hoca ile çağrıyı konuş", "kim": "selin-hoca", "kanit": ["selin-hoca"], "sonuc": ""}]}
        b = br.brifing(veri, "selin-hoca", BUGUN, sonuclar=sonuclar, hedefler=hedefler, strateji=strateji)
        self.assertNotIn("Mehmet", json.dumps(b, ensure_ascii=False))
        self.assertNotIn("Mehmet", br.markdown(b))
        self.assertEqual([d for d in b["dikkat"]], ["Selin Hoca – Elif Demir: birlikte çalışıyor. Referansları bağımsız sayılmaz."])
        self.assertEqual([x["id"] for x in b["ortak_tanidiklar"]], ["elif-demir"])
        self.assertEqual([h["id"] for h in b["hedefler"]], ["h2"])
        self.assertEqual([x["baslik"] for x in b["strateji"]], ["Selin Hoca ile çağrıyı konuş"])
        self.assertEqual([(g["oneri"], g["not"]) for g in b["gecmis"]], [("Selam yaz", "")])

    def test_yolda_haric_dugum_ve_metin_duser(self):
        veri = veri_yap([kisi("hedef-kisi", "Deniz Demo", yakinlik=0), kisi("mehmet-kaya", "Mehmet Kaya", haric=True, yakinlik=3),
                         kisi("elif-demir", "Elif Demir", yakinlik=3)])
        yol = {"hedef": {"id": "hedef-kisi"}, "dogrudan": False, "yok_nedeni": "", "yollar": [
            {"skor": 80, "dugumler": [{"id": "umut", "ad": "Umut"}, {"id": "mehmet-kaya", "ad": "Mehmet Kaya"}, {"id": "hedef-kisi", "ad": "Deniz Demo"}],
             "gerekce": [], "uyarilar": [], "taslak": ""},
            {"skor": 70, "dugumler": [{"id": "umut", "ad": "Umut"}, {"id": "elif-demir", "ad": "Elif Demir"}, {"id": "hedef-kisi", "ad": "Deniz Demo"}],
             "gerekce": ["Elif ile yakınsın.", "Elif Demir ve Mehmet Kaya birlikte çalışıyor."], "uyarilar": ["Mehmet Kaya ile aran gergin."],
             "taslak": "Selam Elif"}]}
        with mock.patch.dict(sys.modules, {"ag_yol": sahte_modul("ag_yol", yollar=lambda v, kimlik, **kw: yol)}):
            b = br.brifing(veri, "hedef-kisi", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertNotIn("Mehmet", json.dumps(b, ensure_ascii=False))
        self.assertEqual(len(b["yol"]["yollar"]), 1)
        self.assertEqual(b["yol"]["yollar"][0]["gerekce"], ["Elif ile yakınsın."])


class YakinlikSifirYolTest(unittest.TestCase):
    YOL = {"hedef": {"id": "deniz-demo", "ad": "Deniz Demo"}, "dogrudan": False, "yok_nedeni": "", "yollar": [
        {"skor": 63, "dugumler": [{"id": "umut", "ad": "Umut", "tur": "ben", "yakinlik": 3}, {"id": "elif-demir", "ad": "Elif Demir", "tur": "yakin", "yakinlik": 3},
                                  {"id": "deniz-demo", "ad": "Deniz Demo", "tur": "is", "yakinlik": 0}],
         "kenarlar": [], "ilk_adim": {"id": "elif-demir", "ad": "Elif Demir"}, "gerekce": ["Elif ile yakınsın."], "uyarilar": ["Elif ile 90 gündür konuşmadın."],
         "taslak": "Selam Elif, bir ricam olacak."}]}

    def veri(self):
        return veri_yap([kisi("deniz-demo", "Deniz Demo", yakinlik=0, kurum="Lodos Teknoloji"), kisi("elif-demir", "Elif Demir", yakinlik=3)])

    def test_yol_cagrilir(self):
        cagri = mock.Mock(return_value=self.YOL)
        veri = self.veri()
        with mock.patch.dict(sys.modules, {"ag_yol": sahte_modul("ag_yol", yollar=cagri)}):
            b = br.brifing(veri, "deniz-demo", BUGUN, sonuclar=[], hedefler=[], strateji={})
        cagri.assert_called_once_with(veri, "deniz-demo", k=1)
        self.assertEqual(b["yol"]["yollar"][0]["ilk_adim"]["id"], "elif-demir")
        self.assertEqual(b["ozet"], "Deniz Demo (Lodos Teknoloji) ile henüz birebir temasın yok.")
        self.assertEqual(b["konusma"], ["Henüz tanışmıyorsunuz. Ona Elif üzerinden ulaşabilirsin; önce onunla konuş."])
        md = br.markdown(b)
        self.assertIn("## Ulaşma yolu", md)
        self.assertIn("Umut → Elif Demir → Deniz Demo", md)
        self.assertIn("Taslak: Selam Elif, bir ricam olacak.", md)

    def test_yakinlik_birde_yol_cagrilmaz(self):
        cagri = mock.Mock(return_value=self.YOL)
        with mock.patch.dict(sys.modules, {"ag_yol": sahte_modul("ag_yol", yollar=cagri)}):
            b = br.brifing(veri_yap([selin()]), "selin-hoca", BUGUN, sonuclar=[], hedefler=[], strateji={})
        cagri.assert_not_called()
        self.assertIsNone(b["yol"])

    def test_yol_modulu_yok_ya_da_hata_verirse_none(self):
        with mock.patch.dict(sys.modules, {"ag_yol": None}):   # None → ImportError
            self.assertIsNone(br.brifing(self.veri(), "deniz-demo", BUGUN, sonuclar=[], hedefler=[], strateji={})["yol"])
        def patla(*a, **k):
            raise ValueError("Bu kişi hariç listende; öneri üretilmez.")
        with mock.patch.dict(sys.modules, {"ag_yol": sahte_modul("ag_yol", yollar=patla)}):
            self.assertIsNone(br.brifing(self.veri(), "deniz-demo", BUGUN, sonuclar=[], hedefler=[], strateji={})["yol"])

    def test_yol_yok_nedeni_markdowna_girer(self):
        yol = {"hedef": {}, "dogrudan": False, "yollar": [], "yok_nedeni": "Ağında bu kişiye giden bir bağ yok. Bir bağ ekle ya da doğrudan yaz."}
        with mock.patch.dict(sys.modules, {"ag_yol": sahte_modul("ag_yol", yollar=lambda *a, **k: yol)}):
            b = br.brifing(self.veri(), "deniz-demo", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertEqual(b["konusma"], [])
        self.assertIn("Ağında bu kişiye giden bir bağ yok.", br.markdown(b))

    def test_dogrudan_yol_konusmasi(self):
        yol = {"hedef": {}, "dogrudan": True, "yok_nedeni": "", "yollar": [{"skor": 50, "dugumler": [{"id": "umut", "ad": "Umut"}, {"id": "deniz-demo", "ad": "Deniz Demo"}]}]}
        with mock.patch.dict(sys.modules, {"ag_yol": sahte_modul("ag_yol", yollar=lambda *a, **k: yol)}):
            b = br.brifing(self.veri(), "deniz-demo", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertIn("doğrudan yazabilirsin", b["konusma"][0])


class SozSiralamaTest(unittest.TestCase):
    def govde(self):
        g = "# A\n"
        for yon, metin, son in (("ben", "tarihsiz eski", ""), ("ben", "yaklaşan", "2026-10-20"), ("ben", "az gecikmiş", "2026-10-14"),
                                ("ben", "çok gecikmiş", "2026-10-01"), ("ben", "bugün biten", "2026-10-15"), ("o", "onun tarihsizi", ""),
                                ("o", "onun gecikmişi", "2026-10-10")):
            g = sz.ekle(g, yon, metin, son, date(2026, 9, 1))
        return g

    def test_gecikmis_sozler_once(self):
        b = br.brifing(veri_yap([kisi("a", "Ada Test", govde=self.govde())]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertEqual([s["metin"] for s in b["sozler"]["senin"]], ["çok gecikmiş", "az gecikmiş", "bugün biten", "yaklaşan", "tarihsiz eski"])
        self.assertEqual([s["metin"] for s in b["sozler"]["onun"]], ["onun gecikmişi", "onun tarihsizi"])
        self.assertEqual([s["gecikmis"] for s in b["sozler"]["senin"]], [True, True, False, False, False])
        self.assertEqual(b["sozler"]["senin"][0]["yazi"], "14 gün gecikti")
        self.assertEqual(b["sozler"]["senin"][2]["yazi"], "bugün")
        self.assertEqual(b["sozler"]["senin"][3]["yazi"], "5 gün kaldı")

    def test_konusmada_gecikmis_ve_yaklasan_soz(self):
        b = br.brifing(veri_yap([kisi("a", "Ada Test", govde=self.govde())]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertTrue(b["konusma"][0].startswith("Gecikmiş bir sözün var: «çok gecikmiş» (14 gün gecikti)"))
        self.assertTrue(b["konusma"][1].startswith("Gecikmiş bir sözün var: «az gecikmiş»"))
        self.assertTrue(b["konusma"][2].startswith("Ada sana bir söz vermişti: «onun gecikmişi» (5 gün gecikti)"))
        self.assertEqual(b["ozet"], "Ada Test ile yakınlığınız 1; kayıtlı temas yok. Verdiğin 2 söz gecikmiş durumda.")

    def test_hazir_sozler_alani_kullanilir_yazi_bugunle_yeniden(self):
        k = kisi("a", "Ada Test", sozler=[{"durum": "acik", "yon": "ben", "tarih": "2026-09-01", "metin": "kitap", "son": "2026-10-10", "kapanis": "", "sira": 0,
                                         "yazi": "eski yazı", "gun": 99}, {"durum": "tamam", "yon": "ben", "tarih": "2026-09-01", "metin": "kapalı", "son": "", "kapanis": "2026-09-02"}])
        s = br.brifing(veri_yap([k]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})["sozler"]["senin"]
        self.assertEqual([(x["metin"], x["yazi"], x["gun"]) for x in s], [("kitap", "5 gün gecikti", 5)])


class OrtakTanidikTest(unittest.TestCase):
    def iliski(self, a, b, tip="arkadas"):
        return {"a": a, "b": b, "tip": tip, "not": "", "kaynak": "", "tarih": ""}

    def test_suzme_ve_siralama(self):
        kisiler = [selin(), kisi("yakin-biri", "Zeynep Arı", yakinlik=3), kisi("orta-biri", "Baran Su", yakinlik=2), kisi("tanimadigim", "Hedef Kişi", yakinlik=0),
                   kisi("haric-kisi", "Haris Ayrık", yakinlik=3, haric=True), kisi("rakip-kisi", "Rakip Kişi", yakinlik=3)]
        iliskiler = [self.iliski("selin-hoca", "yakin-biri"), self.iliski("orta-biri", "selin-hoca", "tanisiyor"), self.iliski("selin-hoca", "tanimadigim"),
                     self.iliski("selin-hoca", "haric-kisi"), self.iliski("selin-hoca", "rakip-kisi", "rakip"), self.iliski("selin-hoca", "umut", "hocasi"),
                     self.iliski("yakin-biri", "orta-biri"), self.iliski("selin-hoca", "yok-boyle-biri")]
        b = br.brifing(veri_yap(kisiler, iliskiler), "selin-hoca", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertEqual([(x["id"], x["tip_etiket"]) for x in b["ortak_tanidiklar"]], [("yakin-biri", "Arkadaş"), ("orta-biri", "Tanışıyor")])

    def test_en_cok_alti_ve_ayni_kisi_bir_kez(self):
        kisiler = [selin()] + [kisi(f"k{i}", f"Kişi {chr(65 + i)}", yakinlik=1 + i % 3) for i in range(9)]
        iliskiler = [self.iliski("selin-hoca", f"k{i}") for i in range(9)] + [self.iliski("k0", "selin-hoca", "partner")]
        b = br.brifing(veri_yap(kisiler, iliskiler), "selin-hoca", BUGUN, sonuclar=[], hedefler=[], strateji={})
        idler = [x["id"] for x in b["ortak_tanidiklar"]]
        self.assertEqual(len(idler), 6)
        self.assertEqual(len(set(idler)), 6)
        self.assertTrue(all(x["yakinlik"] >= 1 for x in b["ortak_tanidiklar"]))
        self.assertEqual([x["yakinlik"] for x in b["ortak_tanidiklar"]], sorted((x["yakinlik"] for x in b["ortak_tanidiklar"]), reverse=True))

    def test_ayni_kisiyle_birden_cok_bag_en_gucluyu_alir(self):
        veri = veri_yap([selin(), kisi("k0", "Kişi A", yakinlik=2)], [self.iliski("selin-hoca", "k0", "tanisiyor"), self.iliski("k0", "selin-hoca", "partner")])
        b = br.brifing(veri, "selin-hoca", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertEqual([(x["id"], x["tip_etiket"]) for x in b["ortak_tanidiklar"]], [("k0", "Partner")])

    def test_yonlu_tip_kisiye_gore(self):
        kisiler = [selin(), kisi("baran", "Baran Su", yakinlik=2)]
        ilis = [self.iliski("selin-hoca", "baran", "hocasi")]   # Selin, Baran'ın hocası
        veri = veri_yap(kisiler, ilis)
        self.assertEqual(br.brifing(veri, "baran", BUGUN, sonuclar=[], hedefler=[], strateji={})["ortak_tanidiklar"][0]["tip_etiket"], "Hocası")
        self.assertEqual(br.brifing(veri, "selin-hoca", BUGUN, sonuclar=[], hedefler=[], strateji={})["ortak_tanidiklar"][0]["tip_etiket"], "Öğrencisi")

    def test_ortak_tanidik_markdownda(self):
        veri = veri_yap([selin(), kisi("baran", "Baran Su", yakinlik=2)], [self.iliski("selin-hoca", "baran", "is-ortagi")])
        md = br.markdown(br.brifing(veri, "selin-hoca", BUGUN, sonuclar=[], hedefler=[], strateji={}))
        self.assertIn("## Ortak tanıdıklar\n\n- Baran Su (İş ortağı)", md)


class HedefStratejiTest(unittest.TestCase):
    def test_hedef_eslesmesi(self):
        hedefler = [
            {"id": "acik-veri", "baslik": "Açık veri çağrısına başvur", "durum": "taslak", "anahtar": ["açık veri"], "govde": "# x\n\nSelin Hoca'nın kurulu değerlendirecek", "ilerleme": []},
            {"id": "lodos", "baslik": "Yeditepe Üniversitesi ile ortak proje", "durum": "aktif", "anahtar": [], "govde": "", "neden": "", "ilerleme": []},
            {"id": "alakasiz", "baslik": "Maraton koş", "durum": "aktif", "anahtar": ["koşu"], "govde": "", "ilerleme": []},
            {"id": "bitti", "baslik": "Selin Hoca ile makale", "durum": "tamam", "anahtar": [], "govde": "", "ilerleme": []},
            {"id": "beklemede", "baslik": "Selin Hoca ile makale 2", "durum": "beklemede", "anahtar": [], "govde": "", "ilerleme": []},
        ]
        b = br.brifing(veri_yap([selin()]), "selin-hoca", BUGUN, sonuclar=[], hedefler=hedefler, strateji={})
        self.assertEqual([(h["id"], h["baslik"]) for h in b["hedefler"]],
                         [("lodos", "Yeditepe Üniversitesi ile ortak proje"), ("acik-veri", "Açık veri çağrısına başvur")])   # aktif önce
        self.assertIn("«Yeditepe Üniversitesi ile ortak proje» hedefin için ondan ne isteyeceğini netleştir.", " ".join(b["konusma"]))
        self.assertIn("## Hedeflerinle bağı\n\n- Yeditepe Üniversitesi ile ortak proje\n- Açık veri çağrısına başvur", br.markdown(b))

    def test_hedef_eslesmesi_kelime_siniri(self):
        k = kisi("ali", "Ali Can", kurum="Lodos")
        hedefler = [{"id": "h", "baslik": "Alicante gezisi", "durum": "aktif", "govde": "Lodosun rüzgârı", "anahtar": [], "ilerleme": []}]
        self.assertEqual(br.brifing(veri_yap([k]), "ali", BUGUN, sonuclar=[], hedefler=hedefler, strateji={})["hedefler"], [])

    def test_strateji_eslesmesi(self):
        strateji = {"hamleler": [
            {"hedef": "h", "baslik": "Selin Hoca'ya çağrıyı sor", "kim": "selin-hoca", "kim_uzerinden": "", "kanit": ["kisi:selin-hoca"], "sonuc": "", "ilk_adim": "Kısa bir mesaj yaz"},
            {"hedef": "h", "baslik": "Baran üzerinden tanış", "kim": "deniz", "kim_uzerinden": "selin-hoca", "kanit": ["x"], "sonuc": "ise_yaradi"},
            {"hedef": "h", "baslik": "Etkinliğe katıl", "kim": "etkinlik:abc", "kanit": ["selin-hoca-2 de orada", "başka"], "sonuc": ""},
            {"hedef": "h", "baslik": "Kanıt olarak anıyor", "kim": "etkinlik:abc", "kanit": ["ağ: selin-hoca yakınlık 2"], "sonuc": "yapmadim"},
            {"hedef": "h", "baslik": "Alakasız", "kim": "baran", "kanit": ["baran"], "sonuc": ""},
        ]}
        b = br.brifing(veri_yap([selin()]), "selin-hoca", BUGUN, sonuclar=[], hedefler=[], strateji=strateji)
        self.assertEqual([(x["baslik"], x["sonuc"]) for x in b["strateji"]],
                         [("Selin Hoca'ya çağrıyı sor", "Bekliyor"), ("Baran üzerinden tanış", "İşe yaradı"), ("Kanıt olarak anıyor", "Yapmadım")])
        self.assertIn("Strateji okumasındaki ilk adım: Kısa bir mesaj yaz.", b["konusma"])
        self.assertIn("- Baran üzerinden tanış (İşe yaradı)", br.markdown(b))

    def test_strateji_liste_olarak_da_verilebilir(self):
        b = br.brifing(veri_yap([selin()]), "selin-hoca", BUGUN, sonuclar=[], hedefler=[],
                       strateji=[{"hedef": "h", "baslik": "X", "kim": "selin-hoca", "kanit": ["a"]}])
        self.assertEqual([x["baslik"] for x in b["strateji"]], ["X"])

    def test_parametre_none_ise_gec_ice_aktarma(self):
        sahteler = {"ag_sonuc": sahte_modul("ag_sonuc", oku=lambda: [{"no": 1, "tarih": "2026-10-01", "kisi": "selin-hoca", "oneri": "Selam yaz", "sonuc": "yaptim"}]),
                    "ag_hedef": sahte_modul("ag_hedef", hepsi=lambda d=None: [{"id": "h", "baslik": "Selin Hoca ile makale", "durum": "aktif", "govde": ""}]),
                    "ag_strateji": sahte_modul("ag_strateji", son=lambda: {"hamleler": [{"baslik": "Sor", "kim": "selin-hoca", "kanit": ["a"]}]})}
        with mock.patch.dict(sys.modules, sahteler):
            b = br.brifing(veri_yap([selin()]), "selin-hoca", BUGUN)
        self.assertEqual([g["oneri"] for g in b["gecmis"]], ["Selam yaz"])
        self.assertEqual([h["id"] for h in b["hedefler"]], ["h"])
        self.assertEqual([x["baslik"] for x in b["strateji"]], ["Sor"])

    def test_parametre_none_ve_modul_yok_ya_da_hatali_ise_bos(self):
        def patla(*a, **k):
            raise RuntimeError("dosya bozuk")
        sahteler = {"ag_sonuc": None, "ag_hedef": sahte_modul("ag_hedef", hepsi=patla), "ag_strateji": sahte_modul("ag_strateji", son=lambda: None)}
        with mock.patch.dict(sys.modules, sahteler):
            b = br.brifing(veri_yap([selin()]), "selin-hoca", BUGUN)
        self.assertEqual((b["gecmis"], b["hedefler"], b["strateji"]), ([], [], []))


class GecmisTest(unittest.TestCase):
    def kayit(self, no, tarih, kisi_id="selin-hoca", sonuc="yaptim", oneri=None, **ek):
        return {"no": no, "tarih": tarih, "kaynak": "ozet", "kisi": kisi_id, "oneri": oneri or f"Öneri {no}", "sonuc": sonuc, "not": "", "kapanis": "", **ek}

    def test_en_yeni_once_bes_kayit_baska_kisi_suzulur(self):
        kayitlar = [self.kayit(1, "2026-08-01"), self.kayit(2, "2026-10-12", sonuc="ise_yaradi", **{"not": "Hemen döndü"}), self.kayit(3, "2026-09-01", sonuc="atlandi"),
                    self.kayit(4, "2026-10-12", sonuc="bekliyor"), self.kayit(5, "2026-07-01"), self.kayit(6, "2026-06-01"), self.kayit(7, "2026-10-14", kisi_id="baran"),
                    self.kayit(8, "2026-10-13", sonuc="ertelendi")]
        b = br.brifing(veri_yap([selin()]), "selin-hoca", BUGUN, sonuclar=kayitlar, hedefler=[], strateji={})
        self.assertEqual([g["oneri"] for g in b["gecmis"]], ["Öneri 8", "Öneri 4", "Öneri 2", "Öneri 3", "Öneri 1"])   # aynı günde büyük no önce
        self.assertEqual([g["sonuc"] for g in b["gecmis"]], ["Ertelendi", "Bekliyor", "İşe yaradı", "Atlandı", "Yaptım"])
        self.assertEqual(b["gecmis"][2]["not"], "Hemen döndü")
        self.assertEqual(set(b["gecmis"][0]), {"tarih", "oneri", "sonuc", "sonuc_kodu", "not", "no"})

    def test_markdownda_gecmis(self):
        b = br.brifing(veri_yap([selin()]), "selin-hoca", BUGUN, sonuclar=[self.kayit(2, "2026-10-12", sonuc="ise_yaramadi", **{"not": "Cevap gelmedi"})], hedefler=[], strateji={})
        self.assertIn("## Kut'un geçmiş önerileri\n\n- 12.10.2026 · Öneri 2 · **İşe yaramadı** (Cevap gelmedi)", br.markdown(b))


class MarkdownKacisTest(unittest.TestCase):
    def test_ad_ve_metinlerde_ozel_karakterler_kacar(self):
        k = kisi("ozel", "Ayşe *Yıldız_* | Co", kurum="A_B*C", neden_onemli="# başlık gibi_ *vurgu* [bağ](http://x) <b>kalın</b>",
                 govde="## Temas\n- 01.02.2026 · telefon · satır | tablo `kod`\n")
        md = br.markdown(br.brifing(veri_yap([k]), "ozel", BUGUN, sonuclar=[], hedefler=[], strateji={}))
        self.assertIn("# Brifing: Ayşe \\*Yıldız\\_\\* \\| Co", md)
        self.assertIn("A\\_B\\*C", md)
        self.assertIn("\\# başlık gibi\\_ \\*vurgu\\* \\[bağ\\](http://x) \\<b\\>kalın\\</b\\>", md)
        self.assertIn("01.02.2026 · telefon · satır \\| tablo \\`kod\\`", md)
        self.assertNotRegex(md, r"(?<!\\)\*Yıldız")

    def test_cok_satirli_metin_tek_satira_iner(self):
        k = kisi("ozel", "Ada Test", neden_onemli="satır bir\n## sahte başlık\n- sahte madde")
        md = br.markdown(br.brifing(veri_yap([k]), "ozel", BUGUN, sonuclar=[], hedefler=[], strateji={}))
        self.assertNotIn("\n## sahte", md)
        self.assertIn("satır bir ## sahte başlık - sahte madde", md)

    def test_kac_liste_basi(self):
        self.assertEqual(br._kac("1. madde"), "1\\. madde")
        self.assertEqual(br._kac("- madde"), "\\- madde")
        self.assertEqual(br._kac("5-6 kişi"), "5-6 kişi")


class TarihVeKisalikTest(unittest.TestCase):
    def test_bugun_datetime_str_none(self):
        v = veri_yap([selin()])
        a = br.brifing(v, "selin-hoca", datetime(2026, 10, 15, 9, 30), sonuclar=[], hedefler=[], strateji={})
        b = br.brifing(v, "selin-hoca", "2026-10-15", sonuclar=[], hedefler=[], strateji={})
        self.assertEqual(a["sicaklik"]["son_temas_gun"], 34)
        self.assertEqual(a, b)
        self.assertEqual(br.brifing(v, "selin-hoca", None, sonuclar=[], hedefler=[], strateji={})["uretildi"], date.today().isoformat())

    def test_son_temas_gunu_en_yeni_kaynaktan_ve_gelecek_sifir(self):
        k = kisi("a", "Ada Test", son_temas="2026-01-01", etkin_son_temas="", govde="## Temas\n- 10.10.2026 · telefon · konuştuk\n")
        self.assertEqual(br.brifing(veri_yap([k]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})["sicaklik"]["son_temas_gun"], 5)
        k = kisi("a", "Ada Test", son_temas="2026-12-01")
        self.assertEqual(br.brifing(veri_yap([k]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})["sicaklik"]["son_temas_gun"], 0)

    def test_ozet_son_temas_ifadeleri(self):
        for iso, beklenen in (("2026-10-15", "son temas bugün"), ("2026-10-14", "son temas dün"), ("2026-10-10", "son temas 5 gün önce")):
            b = br.brifing(veri_yap([kisi("a", "Ada Test", yakinlik=3, son_temas=iso)]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})
            self.assertIn(beklenen, b["ozet"])
            self.assertIn("bağ canlı" if iso != "2026-10-10" else "son temas 5", b["ozet"])

    def test_bag_isinma_ve_ihmal_esigi(self):
        a = br.brifing(veri_yap([kisi("a", "Ada Test", yakinlik=2, son_temas="2026-09-30", puan={"_trend": "ısınıyor"})]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertIn("bağ ısınıyor", a["ozet"])
        b = br.brifing(veri_yap([kisi("a", "Ada Test", yakinlik=3, son_temas="2026-09-30")]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})   # 15 gün, eşik 14
        self.assertIn("bağ soğuyor", b["ozet"])

    def test_sonraki_adim_gecikmis(self):
        k = kisi("a", "Ada Test", sonraki_adim="Raporu gönder.", sonraki_tarih="2026-10-12")
        b = br.brifing(veri_yap([k]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertEqual(b["sonraki"], {"adim": "Raporu gönder.", "tarih": "2026-10-12", "gun": -3, "yazi": "3 gün gecikti"})
        self.assertTrue(b["ozet"].endswith("Planladığın sonraki adım gecikmiş durumda."))
        self.assertEqual(b["konusma"], ["Planladığın sonraki adım: Raporu gönder (3 gün gecikti). Görüşmede netleştir."])
        bozuk = br.brifing(veri_yap([kisi("a", "Ada Test", sonraki_adim="Ara", sonraki_tarih="yarın")]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertEqual(bozuk["sonraki"], {"adim": "Ara", "tarih": "", "gun": None, "yazi": ""})

    def test_kut_onerisi_satiri_takip_konusu_olmaz(self):
        k = kisi("a", "Ada Test", govde="## Temas\n- 10.10.2026 · telefon · Kut önerisi: Selam yaz\n- 09.10.2026 · telefon · Rapor konuşuldu\n")
        b = br.brifing(veri_yap([k]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertEqual(len(b["konusma"]), 1)
        self.assertIn("09.10.2026", b["konusma"][0])
        self.assertIn("«Rapor konuşuldu»", b["konusma"][0])

    def test_hitap_unvanli_ad_oldugu_gibi(self):
        self.assertEqual(br._hitap("Selin Hoca"), "Selin Hoca")
        self.assertEqual(br._hitap("Dr. Ayşe Yılmaz"), "Dr. Ayşe Yılmaz")
        self.assertEqual(br._hitap("Mert Aksoy"), "Mert")

    def test_alinti_kisalir(self):
        uzun = "çok " * 60
        k = kisi("a", "Ada Test", govde="## Temas\n- 10.10.2026 · telefon · " + uzun)
        self.assertLess(len(br.brifing(veri_yap([k]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})["konusma"][0]), 200)


class OrtakZeminTest(unittest.TestCase):
    def test_kesisim_sade_esitlik(self):
        k = kisi("a", "Ada Test", alan=["Veri Görselleştirme"], etiketler=["açık-veri", "yapay-zeka"])
        b = br.brifing(veri_yap([k], ilgiler=["veri görselleştirme", "Açık veri", "Müzik"]), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})
        self.assertEqual(b["konusma"], ["Ortak zemin: ikiniz de veri görselleştirme ve Açık veri ile ilgileniyorsunuz. Sohbeti buradan açabilirsin."])

    def test_ilgi_yoksa_madde_yok(self):
        k = kisi("a", "Ada Test", alan=["veri"])
        for ilgiler in ([], ["müzik"]):
            self.assertEqual(br.brifing(veri_yap([k], ilgiler=ilgiler), "a", BUGUN, sonuclar=[], hedefler=[], strateji={})["konusma"], [])


if __name__ == "__main__":
    unittest.main()
