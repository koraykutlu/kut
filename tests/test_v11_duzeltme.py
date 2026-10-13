"""v1.1 denetim düzeltmeleri: takvim/LinkedIn içe aktarma sınırları, söz ayrıştırma, kilit sonrası model, akademik kapı, kasa fotoğrafı.
Yalnız kurgusal veri; ağ ve gerçek model yok."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ag_akademik as ak  # noqa: E402
import ag_analiz as an  # noqa: E402
import ag_cekirdek as c  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_ice_ortak as ort  # noqa: E402
import ag_kasa_kisi as kk  # noqa: E402
import ag_kilit as kl  # noqa: E402
import ag_linkedin as li  # noqa: E402
import ag_model as mdl  # noqa: E402
import ag_soz as sz  # noqa: E402
import ag_sunucu as sunucu  # noqa: E402
import ag_takvim as tk  # noqa: E402
from test_kasa_kisi import kisi_notu, png, yaz  # noqa: E402
from test_veri_entegrasyonlari import ADA, BEN, DENIZ, EYLUL, Taban, olay, takvim  # noqa: E402

BUGUN = date(2026, 10, 13)   # salı


# ================= Y1 / O1 / O2: takvim sınırları =================
class TakvimSinirTest(Taban):
    def test_satir_acma_dogrusal(self):
        parcalar = "\r\n".join([" " + "x" * 70] * 150_000)
        metin = "BEGIN:VEVENT\r\nSUMMARY:Basl\r\n" + parcalar + "\r\nEND:VEVENT\r\n"
        t0 = time.monotonic()
        satirlar = tk.satirlari_ac(metin)
        self.assertLess(time.monotonic() - t0, 5)
        self.assertEqual(len(satirlar), 3)
        self.assertEqual(len(satirlar[1]), len("SUMMARY:Basl") + 70 * 150_000)

    def test_satir_azami_asilirsa_reddedilir(self):
        with mock.patch.object(tk, "SATIR_AZAMI", 5):
            with self.assertRaises(tk.SureAsildi):
                tk.satirlari_ac("\n".join("A:1" for _ in range(10)))
        self.assertTrue(issubclass(tk.SureAsildi, ValueError))   # sunucu 400 verir, 500 değil

    def test_sure_asilirsa_aciklayici_hata(self):
        ics = takvim(olay("a", "DTSTART:20250310T100000", kisiler=[BEN, ADA])).decode()
        with mock.patch.object(tk, "SURE_AZAMI", -1.0):
            with self.assertRaises(tk.SureAsildi):
                tk.olaylari_oku(ics)
        ham, _ = tk.olaylari_oku(ics)
        with mock.patch.object(tk, "SURE_AZAMI", -1.0):
            with self.assertRaises(tk.SureAsildi):
                tk.olaylari_ac(ham, tk.datetime(2025, 6, 1))

    def test_interval_ust_sinir_ve_tarih_tasmasi(self):
        simdi = tk.datetime(2026, 10, 13, 12, 0)
        for kural in ("RRULE:FREQ=YEARLY;INTERVAL=2147483647", "RRULE:FREQ=MONTHLY;INTERVAL=999999999", "RRULE:FREQ=DAILY;INTERVAL=99999999999",
                      "RRULE:FREQ=WEEKLY;INTERVAL=99999999"):
            ham, _ = tk.olaylari_oku(takvim(olay("u", "DTSTART:20200101T100000", kisiler=[BEN, ADA], ek=[kural])).decode())
            ol, ist = tk.olaylari_ac(ham, simdi)   # çökmez
            self.assertEqual([str(o["tarih"]) for o in ol], ["2020-01-01"], kural)
        self.assertEqual(tk.kural_coz("FREQ=DAILY;INTERVAL=999999999999")["interval"], tk.INTERVAL_AZAMI)
        # başlangıç 9999'a yakın: sonraki dönem date aralığını taşar → seri tek olaya iner, çökmez
        ham, _ = tk.olaylari_oku(takvim(olay("t", "DTSTART:99991230T100000", kisiler=[BEN, ADA], ek=["RRULE:FREQ=YEARLY"])).decode())
        ol, ist = tk.olaylari_ac(ham, tk.datetime(9999, 12, 31))
        self.assertEqual(len(ol), 1)

    def test_toplam_dongu_butcesi(self):
        seriler = [olay(f"s{i}", "DTSTART:20240101T090000", kisiler=[BEN, [ADA, DENIZ, EYLUL][i % 3]], ek=["RRULE:FREQ=DAILY"]) for i in range(6)]
        ham, _ = tk.olaylari_oku(takvim(*seriler).decode())
        simdi = tk.datetime(2025, 6, 1, 12, 0)
        ol, ist = tk.olaylari_ac(ham, simdi)
        self.assertEqual(ist["butce_asildi"], 0)
        tam = len(ol)
        with mock.patch.object(tk, "TOPLAM_DONGU_AZAMI", 700):   # ~1.4 seri sığar: kalanlar tek başlangıç olayına iner
            ol, ist = tk.olaylari_ac(ham, simdi)
        self.assertEqual(ist["butce_asildi"], 1)
        self.assertLess(len(ol), tam)
        self.assertEqual({o["uid"] for o in ol}, {f"s{i}" for i in range(6)})   # hiçbir seri tamamen kaybolmaz
        with mock.patch.object(tk, "TOPLAM_DONGU_AZAMI", 700):
            r = tk.onizle("t.ics", takvim(*seriler), {})
        self.assertTrue(any("bütçesi aşıldı" in u for u in r["uyari"]))


# ================= D1 / D2: LinkedIn adresi ve formül =================
class LinkedinDuzeltmeTest(unittest.TestCase):
    def test_slug_basindan_cipali(self):
        self.assertEqual(ort.linkedin_slug("https://tr.linkedin.com/in/Ada-Deneme-123/?x=1"), "ada-deneme-123")
        self.assertEqual(ort.linkedin_slug("http://www.linkedin.com/in/ada"), "ada")
        for kotu in ("https://kotu.example/?u=linkedin.com/in/x", "https://linkedin.com.kotu.example/in/x", "https://notlinkedin.com/in/x",
                     "javascript:linkedin.com/in/x", "https://kotu.example/linkedin.com/in/x", "", None):
            self.assertEqual(ort.linkedin_slug(kotu), "", kotu)

    def test_formul_temizle(self):
        self.assertEqual(ort.formul_temizle('=HYPERLINK("http://x","t")'), 'HYPERLINK("http://x","t")')
        self.assertEqual(ort.formul_temizle("  +cmd|' /C calc'!A0 "), "cmd|' /C calc'!A0")
        self.assertEqual(ort.formul_temizle("@SUM(A1)"), "SUM(A1)")
        self.assertEqual(ort.formul_temizle("Örnek  A.Ş."), "Örnek A.Ş.")

    def test_csv_kurum_rol_formul_atilir(self):
        csv_ = "First Name,Last Name,URL,Email Address,Company,Position,Connected On\nAda,Deneme,https://www.linkedin.com/in/ada,,=EVIL(),-@rol,10 Mar 2025\n"
        (b,) = li.baglantilari_oku(csv_)
        self.assertEqual((b["kurum"], b["rol"]), ("EVIL()", "rol"))


# ================= D6: tahmin edilen e-posta ayrı onayla =================
class BenKaydetTest(Taban):
    def plan(self):
        olaylar = [olay(f"o{i}", f"DTSTART:2025030{i}T100000", kisiler=[BEN, [ADA, DENIZ, EYLUL][i % 3]]) for i in range(1, 7)]
        return tk.onizle("t.ics", takvim(*olaylar, ad="Takvimim"), {})

    def test_tahmin_varsayilan_kaydedilmez(self):
        r = self.plan()
        self.assertEqual(r["ben"]["otomatik"], ["ben@ornek.test"])
        self.assertFalse(r["ben"]["kaydet"])
        tk.uygula(r["token"], {})
        self.assertNotIn("ben@ornek.test", ia.ayarlar().get("ben_epostalari", []))
        r = self.plan()
        tk.uygula(r["token"], {"ben_kaydet": "evet"})   # yalnız gerçek True sayılır
        self.assertNotIn("ben@ornek.test", ia.ayarlar().get("ben_epostalari", []))

    def test_onayla_kaydedilir(self):
        tk.uygula(self.plan()["token"], {"ben_kaydet": True})
        self.assertIn("ben@ornek.test", ia.ayarlar()["ben_epostalari"])

    def test_yazilan_adres_onaysiz_kaydedilir(self):
        r = tk.onizle("t.ics", takvim(olay("p", "DTSTART:20250301T100000", kisiler=[BEN, ADA])), {"ben": ["ben@ornek.test"]})
        self.assertEqual(r["ben"]["otomatik"], [])
        tk.uygula(r["token"], {})
        self.assertIn("ben@ornek.test", ia.ayarlar()["ben_epostalari"])

    def test_arayuzde_isaretsiz_onay_kutusu_var(self):
        html = open(os.path.join(os.path.dirname(sunucu.__file__), "ag_sablon.html"), encoding="utf-8").read()
        self.assertIn('id="tk-ben-kaydet"', html)
        kutu = html[html.index('id="tk-ben-kaydet"'):][:60]
        self.assertNotIn("checked", kutu)
        self.assertIn("ben_kaydet", html)


# ================= Y1 / D3: sunucu uçları =================
class SunucuUcTest(unittest.TestCase):
    ONIZLE = ("/api/takvim/onizle", "/api/linkedin/onizle", "/api/ders-yapistir/onizle")

    def test_onizleme_genel_kilidi_tutmaz_ve_okuma_kilidi_baglidir(self):
        for y in self.ONIZLE:
            self.assertIn(y, sunucu.KILITSIZ)
            self.assertIn(y, sunucu.DEGISTIRMEYEN)
        for y in ("/api/takvim/uygula", "/api/linkedin/uygula", "/api/ders-yapistir/uygula"):
            self.assertNotIn(y, sunucu.KILITSIZ)
        self.assertIs(ort._okuma_kilidi, sunucu.kilit)

    def test_tek_yukleme_mesgulse_429(self):
        isl = sunucu.Isleyici.__new__(sunucu.Isleyici)
        gonderilen = []
        isl._gonder = lambda kod, govde=None, *a, **k: gonderilen.append(kod)
        isl.headers = {"Host": f"127.0.0.1:{sunucu.PORT}", "X-Ag-Anahtar": sunucu.ANAHTAR}
        isl.path = "/api/takvim/onizle"
        isl._acik = lambda dokun=True: True
        isl._govde = lambda azami: {}
        gorulen = []
        with mock.patch.dict(sunucu.ISLEMLER, {"/api/takvim/onizle": lambda g: gorulen.append(sunucu.kilit.locked()) or {}}):
            self.assertTrue(sunucu._yukleme_isi.acquire(blocking=False))   # başka bir yükleme sürüyor
            try:
                isl.do_POST()
            finally:
                sunucu._yukleme_isi.release()
            self.assertEqual(gonderilen, [429])
            self.assertEqual(gorulen, [])
            isl.do_POST()                          # boşalınca çalışır; genel veri kilidi tutulmadan
            self.assertEqual((gonderilen[-1], gorulen), (200, [False]))
            self.assertTrue(sunucu._yukleme_isi.acquire(blocking=False))   # iş bitince bırakıldı
            sunucu._yukleme_isi.release()

    def test_soz_uclari_koken_denetimli(self):
        for y in ("/api/soz", "/api/soz/durum", "/api/soz/onayla"):
            self.assertIn(y, sunucu.KOKEN_DENETIMLI)
            self.assertIn(y, sunucu.ISLEMLER)


# ================= O7 / O5 / O6 / D7: söz =================
class SozDuzeltmeTest(Taban):
    def setUp(self):
        super().setUp()
        self.kisi_ac("ayse-yilmaz", "Ayşe Yılmaz")
        self.kisi_ac("mehmet-kaya", "Mehmet Kaya")

    def oner(self, metin, bugun=BUGUN):
        return sz.oner(metin, c.kisileri_oku(), bugun)

    def kisi_govde(self, kid):
        return c.kisi_oku(os.path.join(c.KISILER, kid + ".md"))["govde"]

    def test_son_tarih_iso_normalize_ve_gecersiz_reddi(self):
        g = sz.ekle("# A\n", "ben", "kitap", " 2026-10-17 ", BUGUN)
        self.assertEqual(sz.oku(g)[0]["son"], "2026-10-17")
        for kotu in ("20261017", "2026-W42-5", "17.10.2026", "yarın", "2026-02-30", "2026-1-5", "2026-10-17T10:00"):
            with self.assertRaises(ValueError, msg=kotu):
                sz.ekle("# A\n", "ben", "kitap", kotu, BUGUN)
            self.assertIsNone(sz.oneri_dogrula({"kisi": "ayse-yilmaz", "yon": "ben", "metin": "kitap", "son": kotu}, c.kisileri_oku()), kotu)
        o = sz.oneri_dogrula({"kisi": "ayse-yilmaz", "yon": "ben", "metin": "kitap", "tarih": " 2026-10-17 "}, c.kisileri_oku())
        self.assertEqual(o["son"], "2026-10-17")
        sz.kisi_ekle("ayse-yilmaz", "ben", "kitap", " 2026-10-20 ")
        self.assertEqual(sz.oku(self.kisi_govde("ayse-yilmaz"))[0]["son"], "2026-10-20")

    def test_ay_sonu(self):
        durum = {"Ayşe'ye kitabı ay sonuna kadar göndereceğim": "2026-10-31", "Ayşe'ye kitabı ayın sonunda göndereceğim": "2026-10-31",
                 "Ayşe'ye kitabı bu ay sonu göndereceğim": "2026-10-31",
                 "Ayşe'ye kitabı gelecek ay sonu göndereceğim": "2026-11-30", "Ayşe'ye kitabı gelecek ayın sonunda göndereceğim": "2026-11-30",
                 "Ayşe'ye kitabı önümüzdeki ay sonuna kadar göndereceğim": "2026-11-30", "Ayşe'ye kitabı gelecek ay göndereceğim": "2026-11-13"}
        for cumle, beklenen in durum.items():
            (o,) = self.oner(cumle)
            self.assertEqual((o["son"], o["metin"]), (beklenen, "kitabı göndereceğim"), cumle)
        (o,) = self.oner("Ayşe'ye kitabı gelecek ay sonu göndereceğim", date(2026, 12, 20))   # yıl sonu
        self.assertEqual(o["son"], "2027-01-31")
        (o,) = self.oner("Ayşe'ye kitabı gelecek ay sonu göndereceğim", date(2026, 1, 31))     # şubat (artık yıl değil)
        self.assertEqual(o["son"], "2026-02-28")
        (o,) = self.oner("Ayşe'ye kitabı gelecek hafta sonu göndereceğim")
        self.assertEqual(o["son"], "2026-10-25")

    def test_yalniz_acik_taahhut_soz_sayilir(self):
        sayilir = {"Ayşe'ye kitabı göndereceğim": "ben", "Ayşe'ye kitabı yarın yollayacağım": "ben", "Mehmet bana staj ilanını yollayacak": "o",
                   "Ayşe bana kitabı verecek": "o"}
        for cumle, yon in sayilir.items():
            (o,) = self.oner(cumle)
            self.assertEqual(o["yon"], yon, cumle)
        sayilmaz = ["Ayşe'ye kitabı göndermeyeceğim", "Ayşe'ye kitabı gönderecek miyim?", "Ayşe'ye kitabı göndereceğim mi acaba",
                    "Eğer Ayşe'ye kitabı göndereceksem", "Ayşe'ye kitabı göndersem", "Ayşe'ye kitabı gönderebilirim", "Ayşe'ye kitabı yarın gönderebilirim",
                    "Ayşe'ye kitabı göndermeliyim", "Ayşe'ye kitabı yarın göndermeliyim", "Ayşe'ye kitabı göndermem lazım", "Ayşe'ye kitabı göndermem gerek",
                    "Ayşe'yi aramam gerekiyor yarın", "Ayşe'ye söz verdim", "Ayşe'ye söz verdim, cuma kitabı vereceğim", "Ayşe'ye kitabı dün gönderdim",
                    "Ayşe'ye kitabı göndermiştim", "Ayşe'ye kitabı gönderecektim", "Mehmet bana staj ilanını yollamayacak", "Mehmet bana staj ilanını yollayacak mı?",
                    "Mehmet bana gelecek hafta yazdı", "Mehmet bana gelecek", "Ayşe'ye kitabı göndereceğimi söylemedim"]
        for cumle in sayilmaz:
            self.assertEqual(self.oner(cumle), [], cumle)

    def test_gecmis_tarihler_ve_virgullu_cumle(self):
        self.assertEqual(self.oner("Ayşe'ye kitabı dün göndereceğim"), [])
        self.assertEqual(self.oner("Ayşe'ye kitabı göndereceğim, dün"), [])
        self.assertEqual(self.oner("Ayşe'ye kitabı 12.10.2026 göndereceğim"), [])        # açık yıllı geçmiş tarih
        (o,) = self.oner("Ayşe'ye kitabı 12 Ekim göndereceğim")                           # yıl yok: geçmişe düşen gün bir sonraki yıla kayar
        self.assertEqual(o["son"], "2027-10-12")
        (o,) = self.oner("Ayşe'ye kitabı 17 Ekim göndereceğim")
        self.assertEqual(o["son"], "2026-10-17")
        (o,) = self.oner("Mehmet bana yarın staj ilanını yollayacak, haftaya")             # parçanın kendi tarihi, sondaki kardeş parçayı ezer
        self.assertEqual(o["son"], "2026-10-14")
        (o,) = self.oner("Mehmet bana staj ilanını yollayacak, haftaya cuma")              # kendi tarihi yoksa kardeş parçadan
        self.assertEqual(o["son"], "2026-10-23")
        (o,) = self.oner("Ayşe'ye kitabı salı göndereceğim")                               # bugün salı: bir sonraki salı
        self.assertEqual(o["son"], "2026-10-20")
        for o in self.oner("Ayşe'ye kitabı cuma göndereceğim, Mehmet bana pazartesi dosyayı yollayacak"):
            self.assertGreaterEqual(o["son"], BUGUN.isoformat())


# ================= D4: kilit sonrası model =================
class KilitModelTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.eski = ia.AYARLAR
        ia.AYARLAR = os.path.join(self.d.name, "ayarlar.json")
        mdl._kilit_bagla()   # test_kilit modülü ag_kilit'i yeniden yükleyebilir
        kl.kapat()
        mdl._claude_iptal.clear()
        mdl._claude_oturumlar.clear()

    def tearDown(self):
        mock.patch.stopall()
        kl.kapat()
        mdl._claude_iptal.clear()
        mdl._claude_oturumlar.clear()
        ia.AYARLAR = self.eski
        self.d.cleanup()

    def test_kilitliyken_model_cagrisi_yok(self):
        kl.pin_yaz("2468")
        self.assertTrue(kl.kilitli_mi())
        with mock.patch.object(mdl, "_claude") as cl, mock.patch.object(mdl, "hazir", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "kilitli"):
                mdl.cagir("sohbet", "merhaba", oturum="a" * 24, oturum_kalici=True, cwd=self.d.name)
            cl.assert_not_called()
            t = kl.ac("2468")
            self.assertFalse(kl.kilitli_mi())
            cl.return_value = mdl.Cevap("tamam", "")
            mdl.cagir("sohbet", "merhaba", cwd=self.d.name)
            cl.assert_called_once()
            kl.kapat(t)
            self.assertTrue(kl.kilitli_mi())
            with self.assertRaises(RuntimeError):
                mdl.cagir("sohbet", "merhaba", cwd=self.d.name)

    def test_pin_yoksa_kilit_yok_ve_sure_dolunca_kilitli(self):
        self.assertFalse(kl.kilitli_mi())
        kl.pin_yaz("2468", sure=5)
        t = kl.ac("2468")
        kl._oturumlar[t] = time.time() - 6 * 60
        self.assertTrue(kl.kilitli_mi())

    def test_claude_oturumlari_kilitle_iptal_olur(self):
        oid = "b" * 24
        mdl._claude_oturumlar[oid] = True
        self.assertTrue(mdl.claude_oturum_gecerli(oid))
        kl.pin_yaz("2468")
        t = kl.ac("2468")
        kl.kapat(t)
        self.assertFalse(mdl.claude_oturum_gecerli(oid))
        self.assertEqual(len(mdl._claude_oturumlar), 0)
        self.assertTrue(mdl.claude_oturum_gecerli("c" * 24))
        self.assertFalse(mdl.claude_oturum_gecerli("gecersiz!"))
        # iptal edilen oturum --resume edilmez; yeni oturum sürer
        kl.ac("2468")
        cikti = '{"result": "x", "session_id": "' + "d" * 24 + '"}'
        p = mock.Mock(returncode=0, stdout=cikti.encode())
        with mock.patch.object(mdl, "_calistir", return_value=p) as calistir, mock.patch.object(mdl, "yol_bul", return_value="claude"), \
                mock.patch.object(mdl, "hazir", return_value=True):
            r = mdl.cagir("sohbet", "s", oturum=oid, oturum_kalici=True, cwd=self.d.name)
            self.assertNotIn("--resume", calistir.call_args[0][0])
            self.assertEqual(r.oturum, "d" * 24)
            mdl.cagir("sohbet", "s", oturum=r.oturum, oturum_kalici=True, cwd=self.d.name)
            self.assertIn("--resume", calistir.call_args[0][0])

    def test_analiz_kisa_istemi_gecerli_oturuma_baglidir(self):
        self.assertIn("mdl.claude_oturum_gecerli(oturum)", open(an.__file__, encoding="utf-8").read())


# ================= D5: akademik zenginleştirme kapısı =================
class AkademikKapiTest(Taban):
    def test_kapali_ve_haric_kisiler_atlanir(self):
        self.kisi_ac("kapali-hoca", "Kapalı Hoca", remote_allowed="false")
        self.kisi_ac("haric-hoca", "Hariç Hoca", kurum="Örnek Parti")
        with open(c.HARIC, "a", encoding="utf-8") as f:
            f.write("- Örnek Parti\n")
        self.kisi_ac("acik-hoca", "Açık Hoca")
        with open(ia.AYARLAR, "w", encoding="utf-8") as f:
            json.dump({"kesif": {"akademik": True}}, f)
        sorgu = []

        def sahte(url, basliklar=None):
            sorgu.append(url)
            return {"results": []} if "openalex" in url else {"expanded-result": []}
        durum = {}
        with mock.patch.object(ak, "_json", sahte):
            ak.oneriler([("kapali-hoca", "Kapalı Hoca"), ("haric-hoca", "Hariç Hoca"), ("acik-hoca", "Açık Hoca")], {"kurum_en": []}, durum)
        self.assertTrue(sorgu)
        self.assertEqual([k for k in durum if k.startswith("akademik:")], ["akademik:acik-hoca"])
        self.assertFalse(any("Kapal" in u or "Hari" in u for u in sorgu), sorgu)


# ================= O3: kasa notundan foto =================
class KasaFotoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.kok = os.path.join(t, "kasa")
        self.eski = (c.VERI, ia.AYARLAR)
        ia.AYARLAR = os.path.join(t, "ayarlar.json")
        c.veri_klasoru(os.path.join(t, "ag-veri"))
        c.ben_yaz({"ad": "Kerem"})
        with open(ia.AYARLAR, "w", encoding="utf-8") as f:
            json.dump({"ben_adlari": [], "vault": {"yol": self.kok}}, f)
        os.makedirs(os.path.join(self.kok, "notes", "kisiler"), exist_ok=True)
        with open(os.path.join(self.kok, "notes", "kisiler", "yuz.png"), "wb") as f:
            f.write(png())

    def tearDown(self):
        c.VERI, ia.AYARLAR = self.eski
        c.veri_klasoru(self.eski[0])
        self.tmp.cleanup()

    def plan(self, ad):
        return next(r for r in kk.onizle()["kisiler"] if r["ad"] == ad)

    def test_guvenilir_not_foto_alir_guvenilmez_almaz(self):
        yaz(os.path.join(self.kok, "notes", "kisiler", "iyi.md"), kisi_notu("Güvenilir Kişi", "![](yuz.png)\n"))
        yaz(os.path.join(self.kok, "notes", "kisiler", "kotu.md"), kisi_notu("Güvenilmez Kişi", "![](yuz.png)\n", ek="trust: untrusted\n"))
        self.assertTrue(self.plan("Güvenilir Kişi")["foto"])
        self.assertFalse(self.plan("Güvenilmez Kişi")["foto"])
        kk.al([r["yol"] for r in kk.onizle()["kisiler"]])
        kisiler = {x["ad"]: x for x in c.kisileri_oku()}
        self.assertEqual(kisiler["Güvenilmez Kişi"].get("foto", ""), "")
        self.assertTrue(c.foto_yolu(kisiler["Güvenilir Kişi"]["foto"]))

    def test_uzak_url_ve_yol_kacislari_reddedilir(self):
        baglar = ["https://x.example/a.png", "http://127.0.0.1/a.png", "//sunucu/paylas/a.png", "\\\\sunucu\\paylas\\a.png", "file:///C:/a.png",
                  "data:image/png;base64,AAAA", "../../../../a.png", "C:/Windows/a.png"]
        for i, b in enumerate(baglar):
            yaz(os.path.join(self.kok, "notes", "kisiler", f"u{i}.md"), kisi_notu(f"Uzak Foto {i}", f"![x]({b})\n"))
            yaz(os.path.join(self.kok, "notes", "kisiler", f"v{i}.md"), kisi_notu(f"Alan Foto {i}", "Resim\n", ek=f"foto: {b}\n"))
        for r in kk.onizle()["kisiler"]:
            if "Foto" in r["ad"]:
                self.assertFalse(r["foto"], r["ad"])
        kk.al([r["yol"] for r in kk.onizle()["kisiler"]])
        self.assertEqual(os.listdir(c.FOTO) if os.path.isdir(c.FOTO) else [], [])


if __name__ == "__main__":
    unittest.main()
