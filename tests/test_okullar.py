"""Okul bağdaştırıcıları (kayıt defteri, İTÜ ayrıştırıcı), akademik zenginleştirme ve doğal dil ders girdisi.
Kaydedilmiş küçük örneklerle (tests/fixtures); ağ çağrısı yapan test yok: her yerde ağ işlevi sahtelenir ya da çağrılırsa test düşer."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from unittest import mock

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
sys.path.insert(0, KOK)
import ag_akademik as ak  # noqa: E402
import ag_cekirdek as c  # noqa: E402
import ag_ders_girdi as dg  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_kaynak as kn  # noqa: E402
import ag_kesif as ks  # noqa: E402
import ag_okullar as ok  # noqa: E402


def fix(ad):
    with open(os.path.join(FIX, ad), encoding="utf-8") as f:
        return f.read()


def ag_yok(*a, **k):
    raise AssertionError("ağ çağrıldı")


class KayitDefteriTest(unittest.TestCase):
    def test_okullar_kayit_defterinden_gelir(self):
        self.assertIn("yeditepe", kn.OKULLAR)
        self.assertIn("itu", kn.OKULLAR)
        self.assertEqual(set(ok.KAYIT), {"yeditepe", "itu"})
        itu = kn.OKULLAR["itu"]
        self.assertEqual(itu["tur"], "itu")
        self.assertEqual(itu["kadro"], {})
        self.assertIn("istanbul technical university", itu["kurum_en"])

    def test_yeditepe_eski_kayit_aynen(self):
        y = kn.OKULLAR["yeditepe"]
        self.assertNotIn("tur", y)   # eski yol: ders_hocalari Yeditepe'yi eskisi gibi çözer
        self.assertEqual(y["donem"], "141")
        self.assertIn("ISE", y["kadro"])

    def test_acilir_liste_kayit_defterinden_dolar(self):
        d = ks.kaynaklar_durum()
        self.assertEqual({o["anahtar"] for o in d["okullar"]}, set(kn.OKULLAR))
        self.assertIn("itu", {o["anahtar"] for o in d["okullar"]})

    def test_kayit_import_aninda_ag_yok(self):
        # kayit() ve okul_kayitlari() ağa çıkmaz (donem_adi dinamik, yalnız dersler() çağrısında alınır)
        with mock.patch.object(kn, "_istek", ag_yok), mock.patch.object(ok, "al", ag_yok):
            self.assertIn("itu", ok.okul_kayitlari())

    def test_ders_coz_harfli_sube(self):
        self.assertEqual(kn._ders_coz("ISE 424-1"), ("ISE 424", "1"))
        self.assertEqual(kn._ders_coz("CS 201-A"), (None, None))          # Yeditepe yolu eskisi gibi: yalnız rakamlı şube
        self.assertEqual(kn._ders_coz("CS 201-A", harfli=True), ("CS 201", "A"))
        self.assertEqual(kn._ders_coz("BIL 100E-14304"), ("BIL 100E", "14304"))


class ItuTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        p = mock.patch.object(kn, "ONBELLEK", self.d.name)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.d.cleanup)
        self.istekler = []

        def sahte_al(url, **kw):
            self.istekler.append(url)
            if "GetAktifDonem" in url:
                return fix("itu_donem.json")
            if "SearchBransKodu" in url:
                return fix("itu_brans.json")
            if "DersProgramSearch" in url and "dersBransKoduId=38" in url:
                return fix("itu_ders_programi.html")
            raise AssertionError("beklenmeyen adres " + url)
        p2 = mock.patch.object(ok, "al", sahte_al)
        p2.start()
        self.addCleanup(p2.stop)
        self.itu = ok.KAYIT["itu"]

    def test_tablo_ayristirma(self):
        s = ok.ItuBaglastirici.satirlari_ayristir(fix("itu_ders_programi.html"))
        self.assertEqual([x["sube"] for x in s], ["10001", "10002", "10003"])   # bozuk satır atlandı
        self.assertEqual(s[0]["kod"], "BIL 100E")
        self.assertEqual(s[0]["hocalar"], ["Ada Deneme"])
        self.assertEqual(s[0]["saat"], "Pzt 08:30–11:29")
        self.assertEqual(s[1]["saat"], "Pzt 10:30–11:29, Çar 11:30–13:29")
        self.assertEqual(s[2]["hocalar"], ["DERYA ÖRNEK", "Mert Berk"])   # <br> ile iki hoca

    def test_dersler_kod_ve_sube(self):
        kay, yok = self.itu.dersler(["BIL 100E", "BIL 101-10003", "BIL 999", "ZZZ 101", "abc"])
        self.assertEqual(sorted(x["sube"] for x in kay), ["10001", "10002", "10003"])
        self.assertEqual(sorted(yok), ["BIL 999", "ZZZ 101", "abc"])
        kay2, yok2 = self.itu.dersler(["BIL 100E-10002"])
        self.assertEqual([x["sube"] for x in kay2], ["10002"])
        self.assertEqual(yok2, [])

    def test_hoca_yapisi_doldur_ile_uyumlu(self):
        kay, _ = self.itu.dersler(["BIL 101"])
        h = ok.kayitlardan_hocalar(kay, "2026-2027 Güz Dönemi")
        self.assertEqual(set(h), {"Derya Örnek", "Mert Berk"})   # BÜYÜK HARF Türkçe başlık biçimine çevrildi
        satir = h["Derya Örnek"]["satirlar"][0]
        self.assertEqual(satir.split(" · ")[1].split(" ")[0] + " " + satir.split(" · ")[1].split(" ")[1], "BIL 101-10003")   # doldur()'un okuduğu "kod-şube"
        self.assertEqual(h["Mert Berk"]["kodlar"], {"BIL"})

    def test_ders_hocalari_kayit_defterine_yonlenir(self):
        with mock.patch.object(kn, "okul_ayar", return_value=kn.OKULLAR["itu"]):
            h, yok = kn.ders_hocalari(["BIL 100E"])
        self.assertEqual(set(h), {"Ada Deneme", "Emre Çınar"})
        self.assertEqual(yok, [])

    def test_onbellek_ikinci_cagrida_ag_yok(self):
        self.itu.dersler(["BIL 100E"])
        n = len(self.istekler)
        self.itu.dersler(["BIL 100E"])
        self.assertEqual(len(self.istekler), n)

    def test_doldur_uctan_uca_ve_akademik_dogrula(self):
        """İTÜ seçili + ders: hocalar kişi olarak eklenir (kaynaklı), akademik kaynak açıksa OpenAlex sonucu YALNIZ Doğrula'ya düşer."""
        import threading
        eski = c.VERI
        c.veri_klasoru(os.path.join(self.d.name, "veri"))
        self.addCleanup(c.veri_klasoru, eski)
        ayar = os.path.join(self.d.name, "ayarlar.json")
        with open(ayar, "w", encoding="utf-8") as f:
            json.dump({"kesif": {"akademik": True}}, f)
        c.ben_yaz({"ad": "Kerem", "okul": "itu", "dersler": ["BIL 100E"]})
        oa, orc = json.loads(fix("openalex_yazarlar.json"))["results"], json.loads(fix("orcid_arama.json"))

        def sahte_json(url, basliklar=None):
            return {"results": oa} if "openalex" in url else orc
        with mock.patch.object(kn, "DURUM", os.path.join(self.d.name, "kaynak.json")), mock.patch.object(ia, "AYARLAR", ayar), \
                mock.patch.object(ia, "DEPO", self.d.name), mock.patch.object(ak, "_json", sahte_json), mock.patch.object(kn, "okul_ayar", return_value=kn.OKULLAR["itu"]):
            o = kn.doldur(threading.Lock(), lambda: None, zorla=True)
        self.assertEqual(sorted(o["eklenen"]), ["Ada Deneme", "Emre Çınar"])
        kisi = c.kisi_oku(os.path.join(c.KISILER, "ada-deneme.md"))
        self.assertIn("2026-2027 Güz Dönemi · BIL 100E-10001", kisi["govde"])
        self.assertIn("kaynak: obs.itu.edu.tr", kisi["govde"])
        self.assertNotIn("36 yayın", kisi["govde"])   # akademik veri doğrudan dosyaya yazılmadı
        self.assertEqual(str(kisi["yakinlik"]), "0")   # okul kaynağı yakınlık artırmaz; yalnız kullanıcı onayıyla artar
        bekleyen = [r for r in c.cikarimlari_oku() if r["durum"] == "bekliyor"]
        self.assertTrue(any(r["kisi"] == "ada-deneme" and r["alan"] == "hakkinda" and "36 yayın" in r["deger"] for r in bekleyen))
        self.assertTrue(any(r["alan"] == "soru" and "tanışıklığın" in r["deger"] for r in bekleyen))   # eski soru akışı korunur
        self.assertEqual(o["dogrulanacak"], ["ada-deneme"])

    def test_onbellekte_bozuk_tip_cokertmez(self):
        os.makedirs(kn.ONBELLEK, exist_ok=True)
        for ad, icerik in (("itu-donem", "[1, 2]"), ("itu-brans-LS", '{"a": 1}'), ("itu-brans-LU", "[1]"), ("itu-brans-OL", "[]")):
            with open(os.path.join(kn.ONBELLEK, ad + ".json"), "w", encoding="utf-8") as f:
                f.write(icerik)
        self.assertEqual(self.itu.donem_adi_al(), "İTÜ aktif dönem")   # liste geldi: AttributeError yok
        with self.assertRaises(ValueError):
            self.itu._branslar("LS")
        with self.assertRaises(ValueError):
            self.itu._branslar("LU")
        self.assertEqual(self.itu._branslar("OL"), [])

    def test_hoca_profili_varsayilan_bos(self):
        self.assertEqual(self.itu.hoca_profili("Ada Deneme"), {})


class HizSiniriTest(unittest.TestCase):
    def test_ayni_makineye_aralik(self):
        with mock.patch.object(kn, "ISTEK_ARALIGI", 0.5), mock.patch.object(kn, "_son_istek", {}), mock.patch.object(kn.time, "sleep") as uyku, \
                mock.patch.object(kn.time, "monotonic", side_effect=[100.0, 100.0, 100.1, 100.1]):
            kn._hiz_sinirla("a.example")
            uyku.assert_not_called()
            kn._hiz_sinirla("a.example")
            self.assertAlmostEqual(uyku.call_args[0][0], 0.4, places=3)

    def test_istek_guvenli_url_ve_hiz(self):
        with mock.patch.object(kn, "_hiz_sinirla") as h:
            with self.assertRaises(OSError):
                kn._istek("http://127.0.0.1/x")
            h.assert_not_called()   # SSRF reddi hız sınırından önce


class AkademikTest(unittest.TestCase):
    def setUp(self):
        self.oa = json.loads(fix("openalex_yazarlar.json"))["results"]
        self.orc = [{"orcid": x["orcid-id"], "ad": f"{x['given-names']} {x['family-names']}", "kurumlar": x["institution-name"]}
                    for x in json.loads(fix("orcid_arama.json"))["expanded-result"]]
        self.kurum = ["istanbul technical university"]

    def test_kesin_ad_ve_kurum(self):
        k = ak.degerlendir("Ada Deneme", self.kurum, self.oa, self.orc)
        self.assertEqual(k["durum"], "kesin")
        self.assertIn("36 yayın", k["metin"])
        self.assertIn("Computer Science", k["metin"])
        self.assertIn("0000-0001-0000-0001", k["metin"])
        self.assertIn("ORCID kaydındaki kurum", k["metin"])

    def test_yeditepe_kurum_en_ve_kesin_eslesme(self):
        self.assertIn("yeditepe university", kn.OKULLAR["yeditepe"]["kurum_en"])
        oa = [{**self.oa[0], "last_known_institutions": [{"display_name": "Yeditepe University"}]}]
        k = ak.degerlendir("Ada Deneme", kn.OKULLAR["yeditepe"]["kurum_en"], oa, [])
        self.assertEqual(k["durum"], "kesin")

    def test_orcid_sorgusunda_tirnak_kacirilir(self):
        goruldu = []
        with mock.patch.object(ak, "_json", lambda url, basliklar=None: (goruldu.append(url), {})[1]):
            ak.orcid_ara('Ada "x" OR family-names:* Deneme')
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(goruldu[0]).query)["q"][0]
        self.assertEqual(q, 'family-names:"Deneme" AND given-names:"Ada \\"x\\" OR family-names:*"')

    def test_kurum_uymuyorsa_emin_degilim(self):
        k = ak.degerlendir("Ada Deneme", ["koc university"], self.oa, self.orc)
        self.assertEqual(k["durum"], "belirsiz")

    def test_iki_kurumlu_aday_belirsiz(self):
        oa = [self.oa[0], {**self.oa[0], "id": "x2", "works_count": 5}]
        self.assertEqual(ak.degerlendir("Ada Deneme", self.kurum, oa, [])["durum"], "belirsiz")

    def test_ad_uymuyorsa_yok(self):
        self.assertEqual(ak.degerlendir("Zeynep Kaya", self.kurum, self.oa, self.orc)["durum"], "yok")
        self.assertEqual(ak.degerlendir("Ada", self.kurum, [], [])["durum"], "yok")

    def test_kapali_iken_ag_yok(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        with mock.patch.object(ia, "AYARLAR", os.path.join(d.name, "ayarlar.json")), mock.patch.object(ak, "_json", ag_yok), mock.patch.object(kn, "_istek", ag_yok):
            self.assertFalse(ak.acik())
            self.assertEqual(ak.oneriler([("ada", "Ada Deneme")], kn.OKULLAR["itu"], {}), [])

    def test_oneriler_dogrula_dusen_cikarimlar(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        ayar = os.path.join(d.name, "ayarlar.json")
        with open(ayar, "w", encoding="utf-8") as f:
            json.dump({"kesif": {"akademik": True}}, f)

        def sahte(url, basliklar=None):
            self.assertIn(url.split("/")[2], ("api.openalex.org", "pub.orcid.org"))
            return {"results": self.oa} if "openalex" in url else json.loads(fix("orcid_arama.json"))
        durum = {}
        with mock.patch.object(ia, "AYARLAR", ayar), mock.patch.object(ak, "_json", sahte):
            self.assertTrue(ak.acik())
            o = ak.oneriler([("ada-deneme", "Ada Deneme"), ("zeynep-kaya", "Zeynep Kaya")], kn.OKULLAR["itu"], durum)
            self.assertEqual([(x["kisi"], x["alan"]) for x in o], [("ada-deneme", "hakkinda")])
            self.assertIn("akademik:ada-deneme", durum)
            self.assertEqual(ak.oneriler([("ada-deneme", "Ada Deneme")], kn.OKULLAR["itu"], durum), [])   # 30 gün tekrar sorulmaz
            belirsiz = ak.oneriler([("ada2", "Ada Deneme")], {"kurum_en": ["koc university"]}, {})
            self.assertEqual(belirsiz[0]["alan"], "soru")
            self.assertIn("Emin değilim", belirsiz[0]["deger"])

    def test_yalniz_iki_sabit_adres(self):
        with self.assertRaises(OSError):
            ak._json("https://baska.example/x")


class DersGirdisiTest(unittest.TestCase):
    def test_cumleden_kodlar(self):
        self.assertEqual(dg.ayikla("bu dönem ISE 424, ISE 426 ve MATH 101 alıyorum"), ["ISE 424", "ISE 426", "MATH 101"])
        self.assertEqual(dg.ayikla("ISE 424-1, 426-2 ve 430 dersini alıyorum"), ["ISE 424-1", "ISE 426-2", "ISE 430"])
        self.assertEqual(dg.ayikla("Bu dönem bil 100e ve MAT 103E-14304 aldım"), ["BIL 100E", "MAT 103E-14304"])

    def test_soru_ya_da_niyetsiz_metin_bos(self):
        self.assertEqual(dg.ayikla("ISE 424 hocası kim?"), [])
        self.assertEqual(dg.ayikla("COVID 191 derslerim"), [])
        self.assertEqual(dg.ayikla("2026 yılında ders alıyorum"), [])

    def test_yanlis_pozitifler_reddedilir(self):
        for cumle in ("Bu dönem ISE 424 nasıl bir ders?", "Bu dönem ISE 424'ü almalı mıyım?", "ISE 424 alıyor muyum bu dönem?",
                      "bu dönem ISE 424 almıyorum", "ISE 424'ü geçen dönem aldım", "bu dönem Mart 2026'da hocayla görüştüm",
                      "Bu dönem Mayıs 2027 hedeflerim ne?", "bu dönem Pzt 1000 TL harcadım", "bu dönem Pzt 100 TL harcadım",
                      "bu dönem ISE 424 dersini bıraktım", "bu dönem ISE 424'ten çekildim", "ISE 424 kim veriyor, bu dönem alıyorum",
                      "bu dönem ISE 424 dersi alınır mı"):
            self.assertEqual(dg.ayikla(cumle), [], cumle)
        self.assertEqual(dg._kodlar_listele("MART 2026 PZT 1000 MAYIS 2027"), [])   # sayı sonu sınırı: uzun sayılar kod değil
        self.assertEqual(dg._kodlar_listele("MART 202 PZT 100 TL 500"), [])         # ay/gün adı kara listesi

    def test_olumlu_ornekler(self):
        self.assertEqual(dg.ayikla("bu dönem ISE 424, ISE 426 ve MATH 101 alıyorum"), ["ISE 424", "ISE 426", "MATH 101"])
        self.assertEqual(dg.ayikla("ISE 424-1, 426-2 ve 430 alıyorum"), ["ISE 424-1", "ISE 426-2", "ISE 430"])
        self.assertEqual(dg.ayikla("bu dönem ISE 424'ü alıyorum"), ["ISE 424"])

    def test_model_yalniz_kod_yoksa(self):
        cagri = []
        m = lambda istem: (cagri.append(istem), {"dersler": ["ISE 424", "kötü", "MATH 101-2"]})[1]
        self.assertEqual(dg.ayikla("endüstri 4 dersini ve sistem analizi 3 dersini alıyorum", model=m), ["ISE 424", "MATH 101-2"])
        self.assertEqual(len(cagri), 1)
        self.assertEqual(dg.ayikla("ISE 424 alıyorum", model=m), ["ISE 424"])   # kod bulundu: model çağrılmaz
        self.assertEqual(len(cagri), 1)
        self.assertEqual(dg.ayikla("dersleri alıyorum", model=m), [])           # rakam yok: model çağrılmaz
        self.assertEqual(dg.ayikla("endüstri 4 dersi alıyorum", model=lambda i: 1 / 0), [])   # model patlarsa sessizce boş

    def test_birlestir_ve_liste_temizle(self):
        self.assertEqual(dg.birlestir(["ISE 424"], ["ISE 424-1", "MATH 101"]), ["ISE 424-1", "MATH 101"])
        self.assertEqual(dg.birlestir(["ISE 424-1"], ["ISE 424"]), ["ISE 424-1"])
        self.assertEqual(dg.liste_temizle(["ISE 424-1", "bu dönem MATH 101 ve ISE 426 alıyorum", "Serbest ders", "Mart 2026"]),
                         ["ISE 424-1", "MATH 101", "ISE 426", "Serbest ders", "Mart 2026"])


class DersBeyaniSunucuTest(unittest.TestCase):
    """Sohbetteki ders cümlesi: ders_onerisi hiçbir şey yazmaz; yazım yalnız ders_onayla (onay düğmesi) ile olur."""
    @classmethod
    def setUpClass(cls):
        import ag_sunucu
        cls.s = ag_sunucu

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.eski = c.VERI
        c.veri_klasoru(os.path.join(self.tmp.name, "veri"))
        c.ben_yaz({"ad": "Kerem", "okul": "", "dersler": ["ISE 100"]})

    def tearDown(self):
        c.veri_klasoru(self.eski)
        self.tmp.cleanup()

    def test_oneri_hicbir_sey_yazmaz(self):
        self.assertEqual(self.s.ders_onerisi("bu dönem ISE 424 ve MATH 101 alıyorum"), ["ISE 424", "MATH 101"])
        self.assertEqual(c.liste_yap(c.ben()["dersler"]), ["ISE 100"])   # onaydan önce profil değişmez
        self.assertEqual(self.s.ders_onay_sorusu(["ISE 424", "MATH 101"]), "ISE 424 ve MATH 101’i bu dönemki derslerine ekleyeyim mi?")

    def test_sor_onay_ister_ve_asil_soruyu_cevaplar(self):
        with mock.patch.object(self.s.an, "sohbet", return_value={"cevap": "Şöyle bir ders.", "oturum": "o1", "oneri": 0, "kayitlar": []}) as m:
            r = self.s.sor({"soru": "bu dönem ISE 424 ve MATH 101 alıyorum"})
        m.assert_called_once()   # kod bulununca sor erken bitmez, soru sohbete gider
        self.assertEqual(r["cevap"], "Şöyle bir ders.")
        self.assertEqual(r["ders_onay"]["kodlar"], ["ISE 424", "MATH 101"])
        self.assertIn("ekleyeyim mi?", r["ders_onay"]["soru"])
        self.assertEqual(c.liste_yap(c.ben()["dersler"]), ["ISE 100"])
        with mock.patch.object(self.s.an, "sohbet", return_value={"cevap": "x", "oturum": "", "oneri": 0, "kayitlar": []}):
            self.assertNotIn("ders_onay", self.s.sor({"soru": "Bu dönem ISE 424'ü almalı mıyım?"}))
            self.assertNotIn("ders_onay", self.s.sor({"soru": "bugün hava güzel"}))
        for kotu in ({"soru": ["a"]}, {"soru": "x", "oturum": ["a"]}, {"soru": "x", "kisi": 5}):
            with self.assertRaises(ValueError):
                self.s.sor(kotu)

    def test_onay_yazar_okul_yoksa_okulu_sorar(self):
        with mock.patch.object(kn, "_istek", ag_yok), mock.patch.object(ok, "al", ag_yok):
            r = self.s.ders_onayla({"kodlar": ["ISE 424", "MATH 101"]})
        self.assertTrue(r["okul_sor"])
        self.assertIn("İTÜ", r["cevap"])
        self.assertEqual(c.liste_yap(c.ben()["dersler"]), ["ISE 100", "ISE 424", "MATH 101"])   # onay beyan oldu

    def test_onay_kodlari_yeniden_dogrular(self):
        for kotu in (None, "ISE 424", [], [1], ["MART 2026"], ["PZT 100"], ["Serbest ders"], ["ISE 424"] * 21, [{"a": 1}]):
            with self.assertRaises(ValueError, msg=str(kotu)):
                self.s.ders_onayla({"kodlar": kotu})
        self.assertEqual(c.liste_yap(c.ben()["dersler"]), ["ISE 100"])

    def test_onay_ucu_koken_denetimli(self):
        self.assertIn("/api/ders/onayla", self.s.KOKEN_DENETIMLI)
        self.assertIn("/api/ders/onayla", self.s.ISLEMLER)
        self.assertNotIn("/api/ders/onayla", self.s.DEGISTIRMEYEN)   # onaydan sonra statik yenileme çalışır
        self.assertTrue({"/api/saglayici", "/api/ses/kurulum/ayar"} <= self.s.KOKEN_DENETIMLI)

    def test_okul_varken_ozet(self):
        c.ben_yaz({"okul": "itu"})
        hocalar = {"Ada Deneme": {"satirlar": [], "kodlar": {"BIL"}, "bolum": ""}, "Emre Çınar": {"satirlar": [], "kodlar": {"BIL"}, "bolum": ""}}
        with mock.patch.object(kn, "ders_hocalari", return_value=(hocalar, ["MAT 999"])), \
                mock.patch.object(self.s, "kaynak_doldur", return_value={"eklenen": ["Ada Deneme", "Emre Çınar"], "guncellenen": [], "dogrulanacak": ["ada-deneme"]}):
            r = self.s.ders_onayla({"kodlar": ["BIL 100E", "MAT 999"]})
        self.assertEqual(r["ders_ozeti"], {"ders": 2, "hoca": 2, "bulunamayan": ["MAT 999"]})
        self.assertIn("2 ders, 2 hoca", r["cevap"])
        self.assertIn("Doğrula", r["cevap"])

    def test_profilim_elle_yazilan_ogeler_bozulmaz(self):
        with mock.patch.object(self.s.threading, "Thread"):
            self.s.ben_kaydet({"dersler": ["Mart 2026", "Mayıs 2027 hedefleri", "ISE 424-1", "bu dönem MATH 101 ve ISE 426 alıyorum"]})
        self.assertEqual(c.liste_yap(c.ben()["dersler"]), ["Mart 2026", "Mayıs 2027 hedefleri", "ISE 424-1", "MATH 101", "ISE 426"])


if __name__ == "__main__":
    unittest.main()
