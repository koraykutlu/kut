"""ag_baglam testleri: geçici klasörde sahte veriyle, ağ isteği yok."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_baglam as b  # noqa: E402
import ag_cekirdek as c  # noqa: E402
import ag_kaynak as k  # noqa: E402


def kisi(kid, ad, kurum="Örnek Üniversite · Endüstri Mühendisliği", rol="", eposta="", dersler=()):
    govde = f"# {ad}\n\n" + ("## Dersler\n" + "\n".join(f"- Güz 2026 · {d} Ders · x" for d in dersler) + "\n" if dersler else "")
    c.kisi_yaz(kid, {"ad": ad, "tur": "akademi", "kurum": kurum, "rol": rol, "eposta": eposta, "yakinlik": "1"}, govde)


class BaglamTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.eski_veri, self.eski_onbellek = c.VERI, k.ONBELLEK
        c.veri_klasoru(os.path.join(self.tmp.name, "veri"))
        k.ONBELLEK = os.path.join(self.tmp.name, "kaynak")
        k.OKULLAR["ornek"] = {"ad": "Örnek Üniversite", "kisa": "Örnek", "ders_json": "https://ornek.edu/{donem}.json", "ders_kaynak": "ornek.edu",
                              "donem": "1", "donem_adi": "Güz 2026", "kadro": {"ABC": ("https://mdbf.ornek.edu.tr", "141")},
                              "kadro_adi": {"ABC": "Örnek Endüstri Müh."}, "kadro_plugin": "ornek_kadro", "eposta_alani": "ornek.edu.tr"}
        c.ben_yaz({"ad": "Kerem", "okul": "ornek", "dersler": ["ABC 316-1", "ABC 426-1"]})
        kisi("ada", "Ada Deneme Yıldız", eposta="ada@ornek.edu.tr")
        kisi("derya", "Derya Örnek Aksoy", dersler=["ABC 426-1"])
        kisi("emre", "Emre Elmas", eposta="emre@ornek.edu.tr", dersler=["ABC 316-1"])
        kisi("berk", "Mehmet Berk Özer", rol="Asistan (ders asistanı)", eposta="berk@ornek.edu.tr")
        kisi("yabanci", "Yabancı Kişi", kurum="Başka Kurum")
        k.kadro_onbellek_yaz("https://mdbf.ornek.edu.tr", "141", "ABC", [
            {"ad": "Ada Deneme Yıldız", "eposta": "ada@ornek.edu.tr", "unvan": "", "profil": "", "foto": ""},
            {"ad": "Derya Örnek Aksoy", "eposta": "", "unvan": "", "profil": "", "foto": ""},
            {"ad": "Emre Elmas", "eposta": "emre@ornek.edu.tr", "unvan": "", "profil": "", "foto": ""},
            {"ad": "Mert Berk Özer", "eposta": "berk@ornek.edu.tr", "unvan": "", "profil": "", "foto": ""},
            {"ad": "Ağda Olmayan Hoca", "eposta": "", "unvan": "", "profil": "", "foto": ""}])

    def tearDown(self):
        k.OKULLAR.pop("ornek", None)
        c.veri_klasoru(self.eski_veri)
        k.ONBELLEK = self.eski_onbellek
        self.tmp.cleanup()

    def cift(self, a, b_, tip):
        return [i for i in c.iliskileri_oku() if {i["a"], i["b"]} == {a, b_} and i["tip"] == tip]

    def test_kuru_calisma_yazmaz(self):
        r = b.bag_cikar()
        self.assertEqual(len(r["yazilan"]), 6 + 2)  # 4 kişi → 6 kadro çifti + 2 hocasi
        self.assertEqual(c.iliskileri_oku(), [])
        self.assertEqual(c.cikarimlari_oku(), [])

    def test_kadro_ve_hoca_baglari(self):
        b.bag_cikar(kaydet=True)
        self.assertTrue(self.cift("emre", "derya", "birlikte-calisiyor"))
        self.assertTrue(self.cift("emre", "ada", "birlikte-calisiyor"))
        h = self.cift("emre", c.ben_id(), "hocasi")
        self.assertEqual((h[0]["a"], h[0]["b"]), ("emre", c.ben_id()))
        self.assertFalse(self.cift("ada", c.ben_id(), "hocasi"))  # ada'nın ders kaydı yok
        self.assertFalse([i for i in c.iliskileri_oku() if "yabanci" in (i["a"], i["b"])])

    def test_tekrar_eklemez_ve_elle_baglara_dokunmaz(self):
        iliskiler = [{"a": "ada", "b": "derya", "tip": "birlikte-calisiyor", "not": "elle", "kaynak": "sen", "tarih": "2026-01-01"},
                     {"a": "emre", "b": "berk", "tip": "akraba", "not": "", "kaynak": "sen", "tarih": "2026-01-01"}]
        c.iliskileri_yaz(iliskiler)
        r = b.bag_cikar(kaydet=True)
        self.assertEqual(len(self.cift("ada", "derya", "birlikte-calisiyor")), 1)
        self.assertEqual(c.iliskileri_oku()[:2], [dict(i) for i in iliskiler])
        self.assertFalse(self.cift("emre", "berk", "birlikte-calisiyor"))  # daha güçlü bağ var
        self.assertEqual(len(b.bag_cikar(kaydet=True)["yazilan"]), 0)
        self.assertTrue(any("zaten" in x for x in r["atlanan"]))

    def test_haric_ve_reddedilen(self):
        with open(c.HARIC, "a", encoding="utf-8") as f:
            f.write("- Başka Kurum\n")
        c.cikarim_ekle([{"kisi": "derya", "alan": "iliski", "deger": "tanisiyor yabanci", "gerekce": "x", "kaynak": "t"}])
        c.cikarimlari_yaz([dict(r, durum="reddedildi") for r in c.cikarimlari_oku()])
        r = b.bag_cikar(kaydet=True)
        self.assertFalse(any("Yabancı" in x for x in r["onerilen"]))

    def test_cikarim_oneri_ve_ad_sorusu_yok(self):
        kisi("defne", "Defne", kurum="Örnek Üniversite")
        r = b.bag_cikar(kaydet=True)
        oneri = [x for x in c.cikarimlari_oku() if x["alan"] == "iliski"]
        # yalnız aynı kurum (bölüm belirsiz) tanışıklık sayılmaz: öneri de bağ da yok
        self.assertFalse(any("defne" in (x["kisi"], x["deger"].split()[-1]) for x in oneri))
        self.assertFalse(self.cift("defne", "emre", "tanisiyor"))
        self.assertTrue(any("asistan" in x and "Berk" in x for x in r["onerilen"]))

    def test_kadro_onbellegi_ve_eslesme(self):
        kayit = k.kadro_onbellek_oku()[0]
        self.assertEqual(kayit["onek"], "ABC")
        self.assertEqual(len(kayit["kartlar"]), 5)
        kisiler = c.kisileri_oku()
        self.assertEqual(k.kart_esle(kayit["kartlar"][3], kisiler)["id"], "berk")  # e-posta, ad çelişse de
        self.assertIsNone(k.kart_esle(kayit["kartlar"][4], kisiler))
        self.assertFalse(k._ad_uyumlu("Mert Berk Özer", "Mehmet Berk Özer"))
        self.assertTrue(k._ad_uyumlu("Ayla Kurgu", "Ayla Nur Deniz Kurgu"))

    def test_tipler(self):
        for t in ("asistan", "hocasi"):
            self.assertTrue(c.TIPLER[t][2])

    # --- denetim düzeltmeleri ---
    def beyan_ekle(self, kid, satir):
        alanlar = c.kisi_oku(os.path.join(c.KISILER, kid + ".md"))
        govde = c.bolume_ekle(alanlar.pop("govde"), c.BEYAN_BASLIK, satir)
        c.kisi_yaz(kid, alanlar, govde)

    def test_beyandan_asistan_bagi(self):
        self.beyan_ekle("berk", "11.10.2026 · Ada Deneme Yıldız ve Emre Elmas'nin asistanı (Kerem).")
        r = b.bag_cikar(kaydet=True)
        for hoca in ("ada", "emre"):
            bag = self.cift("berk", hoca, "asistan")
            self.assertEqual(len(bag), 1, hoca)
            self.assertEqual((bag[0]["a"], bag[0]["b"]), ("berk", hoca))  # a = asistan, b = hoca
            self.assertEqual(bag[0]["kaynak"], "Kut · kullanıcı beyanı (11.10.2026)")
        self.assertTrue(self.cift("berk", "ada", "birlikte-calisiyor"))  # kadro bağı da kalır
        self.assertTrue(any("Asistanı" in x and "kullanıcı beyanı" in x for x in r["yazilan"]))
        # asistan sorusu artık sorulmaz, ikinci çalıştırma bağı çoğaltmaz
        self.assertFalse(any(x["alan"] == "soru" and x["kisi"] == "berk" for x in c.cikarimlari_oku()))
        self.assertEqual(len(b.bag_cikar(kaydet=True)["yazilan"]), 0)
        self.assertEqual(len(self.cift("berk", "ada", "asistan")), 1)

    def test_beyandan_asistan_tek_kisi_ve_eslesmeyen_ad(self):
        self.beyan_ekle("berk", "11.10.2026 · Derya Ornek Aksoy'nun asistanı.")
        self.beyan_ekle("berk", "11.10.2026 · Ağda Olmayan Hoca ve Emre Elmas’nin asistanı.")
        r = b.bag_cikar(kaydet=True)
        self.assertTrue(self.cift("berk", "derya", "asistan"))  # Türkçe karakter duyarsız
        self.assertTrue(self.cift("berk", "emre", "asistan"))
        self.assertEqual(len([i for i in c.iliskileri_oku() if i["tip"] == "asistan"]), 2)  # eşleşmeyen ad yazılmadı
        self.assertTrue(any("eşleşmedi" in x and "agda olmayan hoca" in x for x in r["atlanan"]))

    def test_asistan_beyani_olmayan_satir_baglamaz(self):
        self.beyan_ekle("berk", "11.10.2026 · Emre Elmas ile derste görüşüyoruz.")
        b.bag_cikar(kaydet=True)
        self.assertFalse([i for i in c.iliskileri_oku() if i["tip"] == "asistan"])

    def wa_kisi(self, kid, ad):
        c.kisi_yaz(kid, {"ad": ad, "tur": "cevre", "yakinlik": "1", "wa_sohbetler": ["shane"]}, f"# {ad}\n")

    def test_c1_bekleyen_oneri_ya_da_bag_varsa_uretilmez(self):
        for kid, ad in (("w1", "Wa Bir"), ("w2", "Wa Iki"), ("w3", "Wa Uc"), ("w4", "Wa Dort")):
            self.wa_kisi(kid, ad)
        c.cikarim_ekle([{"kisi": "w1", "alan": "iliski", "deger": "arkadas w2", "gerekce": "x", "kaynak": "t"}])  # bekliyor
        c.iliskileri_yaz(c.iliskileri_oku() + [{"a": "w3", "b": "w4", "tip": "rakip", "not": "", "kaynak": "sen", "tarih": ""}])
        r = b.bag_cikar(kaydet=True)
        cift = lambda x: frozenset((x["kisi"], x["deger"].split()[-1]))
        oneri = [x for x in c.cikarimlari_oku() if x["alan"] == "iliski" and x["durum"] == "bekliyor"]
        self.assertEqual([x for x in oneri if cift(x) == {"w1", "w2"}], [oneri[0]])  # yalnız mevcut arkadaş önerisi, tanisiyor yok
        self.assertEqual(oneri[0]["deger"], "arkadas w2")
        self.assertFalse([x for x in oneri if cift(x) == {"w3", "w4"}])  # herhangi bir bağ varsa üretilmez
        self.assertTrue(any("bekleyen bağ önerisi" in x for x in r["atlanan"]))
        self.assertTrue([x for x in oneri if cift(x) == {"w1", "w3"} and x["deger"].startswith("tanisiyor")])  # bağsız çift: öneri sürer

    def test_kart_esle_ad_alt_kume(self):
        kisiler = [{"id": "a", "ad": "Ahmet Can Yıldırım"}, {"id": "k", "ad": "Ahmet Kaya Yılmaz"}]
        self.assertEqual(k.kart_esle({"ad": "Ahmet Yıldırım"}, kisiler)["id"], "a")  # alt küme: kabul
        self.assertIsNone(k.kart_esle({"ad": "Ahmet Yıldırım"}, [kisiler[1]]))  # 'Ahmet Kaya Yılmaz' farklı kişi
        self.assertIsNone(k.kart_esle({"ad": "Ahmet Yılmaz"}, [{"id": "k2", "ad": "Ahmet Kaya Yıldırım"}]))
        self.assertIsNone(k.kart_esle({"ad": "Ahmet Kaya"}, [{"id": "x", "ad": "Kaya Ahmet Yıldırım"}]))  # ilk ad farklı
        self.assertIsNone(k.kart_esle({"ad": "Ahmet"}, kisiler))  # tek parça eşlemez
        self.assertEqual(k.kart_esle({"ad": "Başka", "eposta": "X@y.edu"}, [{"id": "e", "ad": "Ahmet", "eposta": "x@y.edu"}])["id"], "e")

    def test_kart_esle_unvan_ve_bolum_celiskisi(self):
        kisiler = [{"id": "a", "ad": "Ahmet Can Yıldırım", "rol": "Prof. Dr.", "kurum": "Örnek Üniversite · Endüstri Mühendisliği"}]
        self.assertIsNone(k.kart_esle({"ad": "Ahmet Yıldırım", "unvan": "Arş. Gör."}, kisiler))  # unvan çelişir
        self.assertEqual(k.kart_esle({"ad": "Ahmet Yıldırım", "unvan": "Prof. Dr."}, kisiler)["id"], "a")
        self.assertIsNone(k.kart_esle({"ad": "Ahmet Yıldırım"}, kisiler, "Örnek Bilişim Sistemleri ve Teknolojileri"))  # bölüm çelişir
        self.assertEqual(k.kart_esle({"ad": "Ahmet Yıldırım"}, kisiler, "Örnek Endüstri Müh.")["id"], "a")
        self.assertEqual(k.kart_esle({"ad": "Ahmet Can Yıldırım", "unvan": "Arş. Gör."}, kisiler, "Başka Bölüm")["id"], "a")  # ad tam: çelişki aranmaz

    def test_kisi_esle_ders_hocasi_alt_kume(self):
        kisiler = [{"id": "a", "ad": "Ada Yıldız Demir"}, {"id": "b", "ad": "Ada Deneme Yıldız"}]
        self.assertEqual(k._kisi_esle("Ada YILDIZ", kisiler)["id"], "a")  # ilk ad + sıralı alt küme
        self.assertIsNone(k._kisi_esle("Ada Kaya", kisiler))
        self.assertIsNone(k._kisi_esle("Ada Demir Deneme", kisiler))

    def test_bozuk_kadro_onbellegi(self):
        def yaz(ad, icerik):
            with open(os.path.join(k.ONBELLEK, ad), "w", encoding="utf-8") as f:
                f.write(icerik)
        yaz("kadro-bozuk-1.json", "{bozuk json")
        yaz("kadro-liste-2.json", json.dumps([1, 2]))
        yaz("kadro-kart-3.json", json.dumps({"kartlar": ["metin", 5, None, {"ad": "Derya Örnek Aksoy"}]}))
        yaz("kadro-tip-4.json", json.dumps({"kartlar": "liste degil"}))
        kayitlar = k.kadro_onbellek_oku()
        self.assertEqual(len(kayitlar), 2)  # asıl kayıt + kartı süzülmüş olan
        self.assertEqual([x for x in kayitlar if x.get("onek") != "ABC"][0]["kartlar"], [{"ad": "Derya Örnek Aksoy"}])
        self.assertIsNone(k.kart_esle("kart degil", c.kisileri_oku()))
        b.bag_cikar()  # çökmez

    def test_varsayilan_avatar_url(self):
        site = "https://myyu.ornek.edu.tr"
        for url in (site + "/themes/custom/myyu/images/default_user_avatar.png", site + "/img/placeholder.png",
                    site + "/img/no-image.jpg", site + "/x/Avatar.png", ""):
            self.assertTrue(k.varsayilan_foto_mu(url), url)
        # Drupal'ın '/sites/default/files/' yolu varsayılan avatar değildir
        self.assertFalse(k.varsayilan_foto_mu(site + "/sites/default/files/styles/272x272_image_style/public/pictures/2024-12/adafoto_0.jpeg?itok=x"))

    def test_foto_indirmede_varsayilan_atlanir(self):
        cagrilar = []
        eski = k._istek
        k._istek = lambda url, **kw: (cagrilar.append(url), (b"\xff\xd8\xff" + b"0" * 10, "image/jpeg"))[1]
        try:
            self.assertIsNone(k._foto_indir("https://x.edu/themes/default_user_avatar.png"))
            self.assertEqual(cagrilar, [])  # indirilmedi bile
            self.assertEqual(k._foto_indir("https://x.edu/sites/default/files/a.jpg")[:3], b"\xff\xd8\xff")
            self.assertEqual(len(cagrilar), 1)
        finally:
            k._istek = eski

    def test_personel_doldur_agsiz_ve_avatar_yazmaz(self):
        def yasak(*a, **kw):
            raise AssertionError("_personel_doldur içinde ağ isteği")
        eski = k._istek
        k._istek = yasak
        try:
            gercek, varsayilan = "https://x.edu/sites/default/files/g.jpg", "https://x.edu/themes/default_user_avatar.png"
            jpeg = b"\xff\xd8\xff" + b"0" * 10
            ozet = {"eklenen": [], "guncellenen": [], "bekleyen": [], "hata": []}
            kartlar = {"ABC": [{"ad": "Mert Berk Özer", "eposta": "berk@ornek.edu.tr", "unvan": "", "profil": "", "foto": gercek}]}
            k._personel_doldur(kartlar, c.kisileri_oku(), set(), {gercek: jpeg, varsayilan: jpeg}, ozet, [])
            self.assertTrue(c.kisi_oku(os.path.join(c.KISILER, "berk.md")).get("foto"))
            kartlar = {"ABC": [{"ad": "Derya Örnek Aksoy", "eposta": "", "unvan": "", "profil": "", "foto": varsayilan}]}
            k._personel_doldur(kartlar, c.kisileri_oku(), set(), {varsayilan: jpeg}, ozet, [])
            self.assertFalse(c.kisi_oku(os.path.join(c.KISILER, "derya.md")).get("foto"))
        finally:
            k._istek = eski

    def test_olu_kod_kaldirildi(self):
        import ag_tutarlilik
        self.assertFalse(hasattr(ag_tutarlilik, "model_denetimi"))
        self.assertFalse(hasattr(c, "onceki_kararlar"))  # tek tanım ag_tutarlilik'te
        self.assertTrue(callable(ag_tutarlilik.onceki_kararlar))


if __name__ == "__main__":
    unittest.main()
