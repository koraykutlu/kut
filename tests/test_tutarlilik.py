"""ag_tutarlilik testleri: sahte veri klasörü, model çağrısı yok."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_cekirdek as c  # noqa: E402
import ag_tutarlilik as t  # noqa: E402

BEN = "---\nid: kerem\nad: Kerem Test\nasistan: Ada\n---\n# Ben\n"


def kisi(kid, ad, govde="", **alan):
    alanlar = {"ad": ad, "tur": "yakin", "yakinlik": "2", **alan}
    c.kisi_yaz(kid, alanlar, f"# {ad}\n\n{govde}")


class TutarlilikTesti(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        c.veri_klasoru(self.tmp.name)
        open(c.BEN_DOSYA, "w", encoding="utf-8", newline="\n").write(BEN)
        kisi("ayla", "Ayla Test", f"## {c.BEYAN_BASLIK}\n- 10.10.2026 · Birlikte yaşıyoruz (Kerem).\n", temas_sikligi="gunluk",
             kullanici_gorusu="Birlikte yaşıyoruz; her gün görüşüyoruz.", yakinlik="3")
        kisi("defne", "Defne Test")
        kisi("selim", "Selim Test", yakinlik_kaynak="sen")
        c.iliskileri_yaz([
            {"a": "kerem", "b": "ayla", "tip": "partner", "not": "", "kaynak": "Core", "tarih": ""},
            {"a": "ayla", "b": "defne", "tip": "arkadas", "not": "", "kaynak": "sen", "tarih": ""},
        ])
        self.no = 0

    def tearDown(self):
        self.tmp.cleanup()

    def ekle(self, kid, alan, deger, durum="bekliyor", yanit="", gerekce=""):
        satirlar = c.cikarimlari_oku()
        self.no += 1
        satirlar.append({"no": str(self.no), "kisi": kid, "alan": alan, "deger": deger, "gerekce": gerekce, "durum": durum,
                         "yanit": yanit, "kaynak": "test", "tarih": "2026-10-11"})
        c.cikarimlari_yaz(satirlar)
        return str(self.no)

    def cel(self, kid, alan, deger, **ek):
        return t.celisiyor_mu({"kisi": kid, "alan": alan, "deger": deger, **ek}, t.baglam_yapisi(kid))

    # (a)
    def test_partner_temas_sorusu(self):
        sonuc, gerekce = self.cel("ayla", "soru", "Ayla ile grup dışında birebir yazışıyor musunuz, yoksa temas ağırlıklı grup üzerinden mi?")
        self.assertTrue(sonuc)
        self.assertIn("partner", gerekce)

    def test_temas_siklik_soruleri(self):
        for q in ("Ayla ile ne sıklıkla görüşüyorsunuz?", "En son ne zaman yüz yüze buluştunuz?", "Hangi kanaldan iletişim kuruyorsunuz?"):
            self.assertTrue(self.cel("ayla", "soru", q)[0], q)

    def test_ilgisiz_soru_acik_kalir(self):
        self.assertFalse(self.cel("ayla", "soru", "XYZ×Acme başvurusunda hangi rolü üstleniyorsun?")[0])
        self.assertFalse(self.cel("ayla", "soru", "Ayla'in görüşü nedir?")[0])  # 'görüş' (fikir) temas sorusu değil

    def test_tanidik_kisiye_temas_sorusu_serbest(self):
        self.assertFalse(self.cel("defne", "soru", "Defne ile birebir görüşme sıklığınız nasıl?")[0])

    def test_haftalik_siklik_yeterli(self):
        kisi("hoca", "Hoca", temas_sikligi="haftalik")
        self.assertTrue(self.cel("hoca", "soru", "Hocayla ne sıklıkla yazışıyorsunuz?")[0])

    # (b)
    def test_yakinlik_partner_ve_sen(self):
        self.assertTrue(self.cel("ayla", "yakinlik", "2")[0])
        self.assertTrue(self.cel("selim", "yakinlik", "1")[0])
        self.assertFalse(self.cel("defne", "yakinlik", "3")[0])

    # (c)
    def test_zayif_bag(self):
        sonuc, gerekce = self.cel("ayla", "iliski", "tanisiyor defne")
        self.assertTrue(sonuc)
        self.assertIn("arkadas", gerekce)
        self.assertTrue(self.cel("defne", "iliski", "tanisiyor ayla")[0])  # ters yön de aynı çift
        self.assertTrue(self.cel("ayla", "iliski", "arkadas kerem")[0])  # partnerle arkadaş bağı daha zayıf
        self.assertFalse(self.cel("ayla", "iliski", "birlikte-calisiyor defne")[0])  # eşit güç, farklı tip
        self.assertFalse(self.cel("selim", "iliski", "arkadas ayla")[0])  # kayıtlı bağ yok

    def test_onayli_oneri_bagi_guclu_sayilir(self):
        self.ekle("selim", "iliski", "arkadas defne", durum="onaylandi")
        self.assertTrue(self.cel("selim", "iliski", "tanisiyor defne")[0])

    # (d)
    def test_ayni_veya_benzer(self):
        self.ekle("defne", "soru", "Defne ile en son ne zaman yüz yüze buluştunuz?", durum="onaylandi", yanit="Geçen hafta")
        self.assertTrue(self.cel("defne", "soru", "Defne ile en son ne zaman yüz yüze buluştun?")[0])
        self.ekle("defne", "etiketler", "kosu, oyun, cizim", durum="reddedildi")
        self.assertTrue(self.cel("defne", "etiketler", "kosu, oyun, cizim")[0])
        self.assertFalse(self.cel("defne", "etiketler", "muhendislik, hackathon")[0])

    def test_reddedilen_bag_ayni_cift(self):
        self.ekle("defne", "iliski", "rakip selim", durum="reddedildi")
        self.assertTrue(self.cel("selim", "iliski", "rakip defne")[0])

    def test_kapanan_tekrar_edilmez(self):
        self.ekle("defne", "soru", "Defne ile derste mi tanıştınız?", durum=t.KAPANDI, yanit="Kut: bilinen bağlamla çelişiyor — x")
        self.assertTrue(self.cel("defne", "soru", "Defne ile derste mi tanıştınız?")[0])

    def test_kendisiyle_karsilastirma_yok(self):
        no = self.ekle("defne", "soru", "Defne hangi bölümde okuyor?")
        r = [x for x in c.cikarimlari_oku() if x["no"] == no][0]
        self.assertFalse(t.celisiyor_mu(r, t.baglam_yapisi("defne"))[0])

    # (e)
    def test_ozel_hayat_partner(self):
        self.assertTrue(self.cel("ayla", "ozet", "Ev işlerini paylaşan, kavga sonrası barışan çift")[0])
        self.assertTrue(self.cel("ayla", "etiketler", "yemek-pisirme, evcil-hayvan")[0])
        self.assertFalse(self.cel("ayla", "etiketler", "muhendislik, hackathon")[0])
        self.assertTrue(self.cel("defne", "etiketler", "yemek-pisirme")[0])  # hobi/günlük yaşam etiketi herkes için süzülür
        self.assertTrue(self.cel("ayla", "soru", "Ayla ile birebir yazışıyor musunuz?")[0])

    # bilinen bağlam metni
    def test_bilinen_baglam_metni(self):
        m = t.bilinen_baglam("ayla")
        for parca in ("partner", "Her gün", "Birlikte yaşıyoruz", "ÜRETME"):
            self.assertIn(parca, m)
        self.assertEqual(t.bilinen_baglam("yok-boyle-biri"), "")
        self.assertIn("KESİN BİLİNENLER", t.kesin_bilinenler_blogu(["ayla", "defne"]))

    # kuyruk temizliği
    def test_kuyrugu_temizle(self):
        a = self.ekle("ayla", "soru", "Ayla ile birebir yazışıyor musunuz?")
        b = self.ekle("ayla", "iliski", "tanisiyor defne")
        d = self.ekle("ayla", "yakinlik", "2")
        acik = self.ekle("ayla", "soru", "Hackathon takım adını belirlediniz mi?")
        selim = self.ekle("selim", "etiketler", "solidworks")
        s = t.kuyrugu_temizle()
        self.assertEqual({k["no"] for k in s["kapanan"]}, {a, b, d})
        satir = {r["no"]: r for r in c.cikarimlari_oku()}
        self.assertEqual(len(satir), 5)  # hiçbiri silinmedi
        for no in (a, b, d):
            self.assertEqual(satir[no]["durum"], "kapandi")
            self.assertTrue(satir[no]["yanit"].startswith("Kut: bilinen bağlamla çelişiyor — "))
        self.assertEqual(satir[acik]["durum"], "bekliyor")
        self.assertEqual(satir[selim]["durum"], "bekliyor")
        self.assertEqual(t.kuyrugu_temizle()["kapanan"], [])  # tekrar çalıştırmak zararsız
        # onceki_kararlar kapananı 'tekrar önerme' olarak verir
        self.assertTrue(any("TEKRAR ÖNERME" in x for x in t.onceki_kararlar("ayla")))

    def test_kuyrugu_temizle_tek_kisi(self):
        self.ekle("ayla", "yakinlik", "2")
        self.ekle("selim", "yakinlik", "1")
        self.assertEqual(len(t.kuyrugu_temizle("ayla")["kapanan"]), 1)
        self.assertEqual(sum(r["durum"] == "bekliyor" for r in c.cikarimlari_oku()), 1)

    def test_filtrele(self):
        gecen, elenen = t.filtrele([
            {"kisi": "ayla", "alan": "soru", "deger": "Ayla ile ne sıklıkla yazışıyorsunuz?"},
            {"kisi": "ayla", "alan": "etiketler", "deger": "hackathon"},
            {"kisi": "defne", "alan": "iliski", "deger": "tanisiyor ayla"},
        ])
        self.assertEqual([o["alan"] for o in gecen], ["etiketler"])
        self.assertEqual(len(elenen), 2)

    def test_uygula_eleneni_sayar(self):
        import ag_analiz
        sonuc = {"kisiler": {"Ayla": {"sorular": ["Ayla ile birebir yazışıyor musunuz?", "Takım adı ne olacak?"], "yakinlik": 2, "etiketler": ["hackathon"]}},
                 "iliskiler": [{"a": "Ayla", "b": "Defne", "tip": "tanisiyor"}]}
        r = ag_analiz.uygula(sonuc, {"Ayla": "ayla", "Defne": "defne"}, "test", "Ada")
        self.assertEqual(r["elenen"], 3)  # temas sorusu, yakınlık, zayıf bağ
        self.assertEqual(r["oneri"], 2)  # takım adı sorusu + etiket
        self.assertEqual(len([x for x in c.cikarimlari_oku() if x["durum"] == "bekliyor"]), 2)

    # --- denetim düzeltmeleri ---
    def test_temas_yanlis_pozitif_yok(self):
        kisi("berk", "Berk Test", tur="akademi", temas_sikligi="haftalik")
        for kid, q in (("berk", "Berk ile sınav takvimi hakkında konuştunuz mu?"),
                       ("berk", "Berk'in e-posta adresi güncel mi?"),
                       ("ayla", "Hackathon başvurusu için Ayla ile ne zaman görüşmeyi planlıyorsun?"),
                       ("ayla", "Ayla'in iletişim bilgileri güncel mi?")):
            self.assertFalse(self.cel(kid, "soru", q)[0], q)
        for q in ("Ayla ile grup dışında birebir yazışıyor musunuz, yoksa temas ağırlıklı olarak grup üzerinden mi?",
                  "Ayla ile ne kadar sık görüşüyorsunuz?", "En son ne zaman yüz yüze görüştünüz?"):
            self.assertTrue(self.cel("ayla", "soru", q)[0], q)

    def test_kapanis_gerekcesi_ozel_hayat_tekrarlamaz(self):
        sonuc, gerekce = self.cel("ayla", "soru", "Ayla ile ne sıklıkla yazışıyorsunuz?")
        self.assertTrue(sonuc)
        self.assertIn("kullanıcı beyanıyla cevaplanmış", gerekce)
        self.assertIn("partner", gerekce)
        self.assertNotIn("yaşad", gerekce)
        sonuc, gerekce = self.cel("ayla", "ozet", "Ev işlerini paylaşan, kavga sonrası barışan çift")
        self.assertTrue(sonuc)
        self.assertNotIn("kavga", gerekce)  # eşleşen özel sözcük gerekçeye taşınmaz

    def test_etiket_suz(self):
        kalan, elenen = t.etiket_suz("muhendislik-egitimi, oyun-geoguessr, kosu, dizi-film, oyun-gelistirme, cilt-bakimi")
        self.assertEqual(kalan, ["muhendislik-egitimi", "oyun-gelistirme"])
        self.assertEqual(elenen, ["oyun-geoguessr", "kosu", "dizi-film", "cilt-bakimi"])

    def test_hobi_etiketi_herkes_icin(self):
        kisi("dost", "Dost Test", tur="cevre")
        self.assertTrue(self.cel("dost", "etiketler", "oyun-geoguessr, kosu")[0])
        self.assertFalse(self.cel("dost", "etiketler", "muhendislik-egitimi, kosu")[0])  # kısmen meşru: kapanmaz
        self.assertFalse(self.cel("dost", "etiketler", "solidworks")[0])

    def test_filtrele_kismi_etiket(self):
        gecen, elenen = t.filtrele([{"kisi": "ayla", "alan": "etiketler", "deger": "muhendislik-egitimi, oyun-geoguessr, kosu, dizi-film"},
                                    {"kisi": "ayla", "alan": "etiketler", "deger": "kosu, dizi-film"}])
        self.assertEqual([o["deger"] for o in gecen], ["muhendislik-egitimi"])
        self.assertEqual(len(elenen), 1)

    def test_kuyrukta_kismi_etiket_kapanir_kalanlarla_yenisi(self):
        eski = self.ekle("ayla", "etiketler", "muhendislik-egitimi, oyun-geoguessr, kosu, dizi-film")
        sadece_hobi = self.ekle("defne", "etiketler", "kosu, oyun")
        s = t.kuyrugu_temizle()
        self.assertEqual({k["no"] for k in s["kapanan"]}, {eski, sadece_hobi})
        self.assertEqual(s["yeni"], 1)
        satirlar = c.cikarimlari_oku()
        self.assertEqual({r["no"]: r["durum"] for r in satirlar}[eski], "kapandi")
        yeni = [r for r in satirlar if r["durum"] == "bekliyor"]
        self.assertEqual([(r["kisi"], r["alan"], r["deger"]) for r in yeni], [("ayla", "etiketler", "muhendislik-egitimi")])
        self.assertEqual(t.kuyrugu_temizle()["kapanan"], [])  # ikinci tur zararsız

    def test_yakin_ozet_beyani_tekrar_eder_ya_da_hobi(self):
        # gerçek kuyruktaki #16 / #17 / #19 biçimleri
        self.assertTrue(self.cel("ayla", "ozet", "Beyana göre kullanıcıyla her gün görüşülen; grup sohbetinde oyun, koşu, plan ve ders konularında sık yazışılan bir kişi.")[0])
        self.assertTrue(self.cel("defne", "ozet", "Grup sohbetinde koşu, oyun ve çizim paylaşımları üzerinden yazışılan bir kişi.")[0])  # tür yakın
        self.assertFalse(self.cel("ayla", "ozellikler", "ulasilabilirlik=7, destek=7, etki=6", gerekce="sık yanıt veriyor")[0])
        kisi("hoca", "Hoca Test", tur="akademi", temas_sikligi="haftalik")
        self.assertTrue(self.cel("hoca", "ozet", "Haftalık görüşülen, dersini veren hoca")[0])
        self.assertFalse(self.cel("hoca", "ozet", "Bitirme projesi danışmanı")[0])

    def test_bekleyen_guclu_bag_zayifi_kapatir(self):
        self.ekle("selim", "iliski", "arkadas defne")  # bekliyor
        sonuc, gerekce = self.cel("defne", "iliski", "tanisiyor selim")
        self.assertTrue(sonuc)
        self.assertIn("bekleyen", gerekce)
        self.assertFalse(self.cel("defne", "iliski", "birlikte-calisiyor selim")[0])  # eşit güç
        # eşit güçte iki bekleyen birbirini kapatmaz
        self.ekle("defne", "iliski", "arkadas selim")
        self.assertEqual(t.kuyrugu_temizle()["kapanan"], [])

    def test_kuyrukta_bekleyen_guclu_bag_varken_tanisiyor(self):
        self.ekle("selim", "iliski", "partner defne")
        zayif = self.ekle("ayla", "iliski", "tanisiyor selim")
        guclu = self.ekle("selim", "iliski", "arkadas ayla")
        zayif2 = self.ekle("defne", "iliski", "tanisiyor selim")
        kapanan = {k["no"] for k in t.kuyrugu_temizle()["kapanan"]}
        self.assertEqual(kapanan, {zayif, zayif2})
        self.assertNotIn(guclu, kapanan)

    def test_model_denetimi_yok(self):
        self.assertFalse(hasattr(t, "model_denetimi"))
        with self.assertRaises(TypeError):
            t.kuyrugu_temizle(model=True)


if __name__ == "__main__":
    unittest.main()
