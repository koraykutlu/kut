"""Sır kapısı (ag_sir): anahtar/parola/token uzak modele ve Kut notlarına gitmez. Yalnız uydurma değerler; gerçek `claude` çağrılmaz."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
sys.path.insert(0, KOK)
import ag_analiz as an  # noqa: E402
import ag_cekirdek as c  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_kapi as kapi  # noqa: E402
import ag_sir as sir  # noqa: E402

RASTGELE = "Zk3fQ9xLm2Vb7Ra1Tn8Uc4Yw6Hd0Pj5Es"   # 34 karakter, karışık


class SirTemizleTest(unittest.TestCase):
    def gizli(self, metin, deger):
        t, n = sir.sir_temizle(metin)
        self.assertNotIn(deger, t)
        self.assertIn(sir.GIZLI, t)
        self.assertGreaterEqual(n, 1)
        return t

    def test_anahtar_atamalari(self):
        for m, d in (("api_key=abc123def456", "abc123def456"), ("API-KEY: abc123def456", "abc123def456"),
                     ("token = tkn_9f8e7d6c", "tkn_9f8e7d6c"), ("client_secret: s3cr3tdegeri", "s3cr3tdegeri"),
                     ('"password": "hunter2xyz"', "hunter2xyz"), ("PASSWORD=hunter2xyz", "hunter2xyz"),
                     ("apikey=zzz999yyy", "zzz999yyy"), ("secret=abcd", "abcd")):
            self.gizli("Selam, bak: " + m + " tamam mı", d)

    def test_turkce_anahtar_kelimeler(self):
        for m, d in (("Parola: kedi1234", "kedi1234"), ("ŞİFRE: kedi1234", "kedi1234"), ("şifre = kedi1234", "kedi1234"),
                     ("Sifre: kedi1234", "kedi1234"), ("PAROLA=KEDİ1234", "KEDİ1234"), ("wifi şifresi yok ama sifre: kedi1234", "kedi1234")):
            self.gizli(m, d)

    def test_bearer_ve_authorization(self):
        t = self.gizli("Authorization: Bearer abcDEF123456xyz.789", "abcDEF123456xyz")
        self.assertIn("Authorization", t)
        self.gizli("curl -H 'authorization: Basic dXNlcjpwYXNz1234' x", "dXNlcjpwYXNz1234")
        self.gizli("bearer abcDEF123456xyz", "abcDEF123456xyz")

    def test_bilinen_oneklar(self):
        for d in ("sk-" + "a1B2c3D4e5F6g7H8i9J0", "sk-ant-api03-" + "a1B2c3D4e5F6g7H8", "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2",
                  "gho_" + "a1B2c3D4e5F6g7H8i9J0k1L2", "github_pat_" + "11ABCDEFG0abcdefgh1234", "xoxb-" + "1234567890-abcdefghij",
                  "AKIA" + "ABCDEFGHIJKLMNOP", "AIza" + "SyA1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6", "glpat-" + "a1B2c3D4e5F6g7H8i9"):
            self.gizli(f"şunu kullan {d} ve devam", d)

    def test_pem_blogu(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAfakefakefake\nZmFrZWtleWRhdGE=\n-----END RSA PRIVATE KEY-----"
        t = self.gizli("önce\n" + pem + "\nsonra", "MIIEowIBAAKC")
        self.assertIn("önce", t)
        self.assertIn("sonra", t)
        self.assertNotIn("END RSA", t)

    def test_jwt(self):
        self.gizli("jwt: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.dummysigvalue123", "eyJhbGciOiJIUzI1NiJ9")

    def test_url_icinde_parola(self):
        t = self.gizli("bağlan https://kullanici:Gizli123x@ornek.com/yol", "Gizli123x")
        self.assertIn("kullanici", t)
        self.assertIn("ornek.com", t)

    def test_uzun_rastgele_dizge(self):
        self.gizli("kod şu: " + RASTGELE + " bitti", RASTGELE)
        self.gizli("hash " + "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", "9f86d081884c7d65")

    def test_url_kodlu(self):
        t = self.gizli("https://ornek.com/cb?x=1&%74oken=abc123def456 sonra", "abc123def456")
        self.assertIn("sonra", t)
        self.gizli("%70assword%3Dhunter2xyz", "hunter2xyz")
        self.gizli("%2570assword%253Dhunter2xyz", "hunter2xyz")   # çift kodlama
        self.gizli("a=1&%61pi_key=abc123def456", "abc123def456")

    def test_yanlis_pozitif_yok(self):
        temiz = [
            "Dün Ayşe ile kahve içtik; şifre yenileme konusunu konuştuk, yarın tekrar görüşeceğiz.",
            "Parolayı unuttum diyor, yardım istedi. Token sistemi hakkında ne düşünüyorsun?",
            "Toplantı 14.10.2026 saat 15:30'da; telefon +90 532 123 45 67 ya da 0212 555 12 34.",
            "https://www.ornek.com/haberler/cok-uzun-bir-haber-basligi-ve-ayrintilari-burada-yer-aliyor-2026?sayfa=2&sirala=tarih",
            "https://github.com/ornek/kut/blob/main/projeler/agim/ag_kapi.py",
            "Anahtar kelime: strateji. Key takeaway: dinlemek. Auth: yok. Authorization hakkında konuştuk.",
            "C:\\Users\\kullanici\\Documents\\projeler\\agim\\veri\\kisiler\\ada-deneme.md dosyası",
            "- 12.10.2026 · telefon · Ahmet Yılmaz ile staj konuşuldu, CV gönderecek",
            "kind: person\ntitle: Ada Deneme\ntur: cevre\nyakinlik: 2\nson_temas: 2026-10-01\neposta: ada@ornek.com\nanahtar: etkinlik:9f86d0818842",
            "id: ada-deneme-hukuk-fakultesi-mezunlari-2026-toplantisi-ozet-notu-final",
            "Kısa hash 9f86d0818842 ve sürüm 3.12.4, IBAN değil sadece 1234567890123.",
        ]
        for m in temiz:
            t, n = sir.sir_temizle(m)
            self.assertEqual((t, n), (m, 0), m)

    def test_url_ve_yol_degismez_iki_modda(self):
        for m in ("Bkz. `notes/akademik/dilekce-ornek-basvuru-metni-2026.md` dosyası",
                  "Harita: https://www.google.com/maps/d/viewer?mid=1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV&ll=39.9,32.8",
                  "https://x.com/Ornek_Kullanici/status/1234567890123456789",
                  "x.com/Ornek_Kullanici/status/1234567890123456789 paylaştı",
                  "C:\\Users\\ornek\\Belgeler\\Zk3fQ9xLm2Vb7Ra1Tn8Uc4Yw6Hd0Pj5Es.pdf",
                  "dosya Zk3fQ9xLm2Vb7Ra1Tn8Uc4Yw6Hd0Pj5Es.pdf"):
            for e in (True, False):
                self.assertEqual(sir.sir_temizle(m, entropi=e), (m, 0), m)

    def test_url_icinde_acik_kimlik_bilgisi_gizlenir(self):
        for m, d in (("https://ornek.com/cb?token=abc123def456&x=1", "abc123def456"), ("https://ornek.com/a?sig=Xy12Zw34Qq56", "Xy12Zw34Qq56"),
                     ("https://ornek.com/a?api_key=abc123def456", "abc123def456"), ("https://ornek.com/a?secret=abc123def456", "abc123def456")):
            for e in (True, False):
                self.gizli_mod(m, d, e)

    def gizli_mod(self, m, d, e):
        t, n = sir.sir_temizle(m, entropi=e)
        self.assertNotIn(d, t)
        self.assertGreaterEqual(n, 1)

    def test_yazma_modunda_entropi_yok(self):
        m = "kod şu: " + RASTGELE + " bitti"
        self.assertEqual(sir.sir_temizle(m, entropi=False), (m, 0))
        self.gizli_mod("anahtar ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2", "a1B2c3D4e5F6g7H8i9J0k1L2", False)
        self.gizli_mod("password=hunter2xyz", "hunter2xyz", False)

    def test_idempotent_ve_bos(self):
        t, _ = sir.sir_temizle("token=abc123def456")
        self.assertEqual(sir.sir_temizle(t), (t, 0))
        self.assertEqual(sir.sir_temizle(""), ("", 0))
        self.assertEqual(sir.sir_temizle(None), (None, 0))

    def test_sayac_deger_icermez(self):
        onceki = sir.TOPLAM
        sir.sir_temizle("password=hunter2xyz")
        self.assertEqual(sir.TOPLAM, onceki + 1)


class UctanUcaTest(unittest.TestCase):
    def setUp(self):
        self.eski = (c.VERI, ia.DEPO, ia.AYARLAR, ia.ADAYLAR, an.SOHBET_KLASOR)
        self.t = tempfile.TemporaryDirectory()
        self.veri, self.depo = os.path.join(self.t.name, "veri"), os.path.join(self.t.name, "depo")
        os.makedirs(self.depo)
        ia.DEPO, ia.AYARLAR, ia.ADAYLAR = self.depo, os.path.join(self.depo, "ayarlar.json"), os.path.join(self.depo, "adaylar.json")
        an.SOHBET_KLASOR = os.path.join(self.depo, "sohbet")
        c.veri_klasoru(self.veri)
        c.kisi_yaz("ada-deneme", {"ad": "Ada Deneme", "tur": "cevre", "yakinlik": "1"}, "# Ada Deneme\n\nKaynak: test\n")
        os.makedirs(os.path.join(self.veri, "gelen", "whatsapp"), exist_ok=True)
        for yol, ic in (("gelen/whatsapp/ada.txt", "Ada: selam\nAda: api_key=sizdi123456 bunu kimseye verme\nAda: %74oken=kodlu987654"),
                        ("notlar.md", "Wifi parola: gizli-parola-77\nnormal satır"),
                        ("belgeler/ada-deneme/cv.txt", "secret = cvdeki-sir-55")):
            os.makedirs(os.path.dirname(os.path.join(self.veri, yol)), exist_ok=True)
            open(os.path.join(self.veri, yol), "w", encoding="utf-8").write(ic)
        with open(os.path.join(c.KISILER, "ada-deneme.md"), "a", encoding="utf-8") as f:
            f.write("\nSohbet metni: `gelen/whatsapp/ada.txt`.\n")

    def tearDown(self):
        c.veri_klasoru(self.eski[0])
        ia.DEPO, ia.AYARLAR, ia.ADAYLAR, an.SOHBET_KLASOR = self.eski[1:]
        self.t.cleanup()

    def test_kopyada_sir_yok_orijinal_degismez(self):
        with kapi.kopya() as k:
            for yol in ("gelen/whatsapp/ada.txt", "notlar.md", "belgeler/ada-deneme/cv.txt"):
                m = open(os.path.join(k, yol), encoding="utf-8").read()
                for d in ("sizdi123456", "kodlu987654", "gizli-parola-77", "cvdeki-sir-55"):
                    self.assertNotIn(d, m, yol)
                self.assertIn(sir.GIZLI, m)
            self.assertIn("normal satır", open(os.path.join(k, "notlar.md"), encoding="utf-8").read())
        self.assertIn("sizdi123456", open(os.path.join(self.veri, "gelen", "whatsapp", "ada.txt"), encoding="utf-8").read())

    def test_sohbet_istemi_ve_dizin(self):
        yakalanan = {}

        def sahte(arg, **kw):
            yakalanan["istem"] = kw["input"].decode("utf-8")
            d = arg[arg.index("--add-dir") + 1]
            yakalanan["metin"] = "".join(open(os.path.join(y, f), encoding="utf-8").read()
                                         for y, _, fs in os.walk(d) for f in fs if f.endswith((".txt", ".md")))
            return subprocess.CompletedProcess(arg, 0, json.dumps({"result": "tamam", "session_id": "s"}).encode(), b"")
        with mock.patch.object(an, "claude_yolu", return_value="claude"), mock.patch.object(an.subprocess, "run", side_effect=sahte):
            an.sohbet("şu parola: kullanici-sorusu-99 ne olur?")
        self.assertNotIn("kullanici-sorusu-99", yakalanan["istem"])
        self.assertIn(sir.GIZLI, yakalanan["istem"])
        for d in ("sizdi123456", "kodlu987654", "gizli-parola-77", "cvdeki-sir-55"):
            self.assertNotIn(d, yakalanan["metin"])

    def test_analiz_istemi(self):
        yakalanan = {}

        def sahte(arg, **kw):
            yakalanan["istem"] = kw["input"].decode("utf-8")
            return subprocess.CompletedProcess(arg, 0, json.dumps({"result": "{}"}).encode(), b"")
        with mock.patch.object(an, "claude_yolu", return_value="claude"), mock.patch.object(an.subprocess, "run", side_effect=sahte):
            an._model("Sohbet:\nAda: github token=ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2 yazdı\nAda: %70assword%3Dkodlu-parola-1")
        self.assertNotIn("a1B2c3D4e5F6g7H8i9J0k1L2", yakalanan["istem"])
        self.assertNotIn("kodlu-parola-1", yakalanan["istem"])

    def test_yazma_yollari(self):
        c.cikarim_ekle([{"kisi": "ada-deneme", "alan": "hakkinda", "deger": "api_key=cikarim-sir-123 kullanıyor", "gerekce": "password: gerekce-sir-4", "kaynak": "t"}])
        m = open(c.CIKARIMLAR, encoding="utf-8").read()
        self.assertNotIn("cikarim-sir-123", m)
        self.assertNotIn("gerekce-sir-4", m)
        c.kisi_yaz("ada-deneme", {"ad": "Ada Deneme", "tur": "cevre", "yakinlik": "1", "sonraki_adim": "token=alan-sir-5551"},
                   "# Ada\n\n## Temas\n- 01.01.2026 · mesaj · şifre: govde-sir-222\n")
        m = open(os.path.join(c.KISILER, "ada-deneme.md"), encoding="utf-8").read()
        self.assertNotIn("alan-sir-5551", m)
        self.assertNotIn("govde-sir-222", m)
        self.assertIn("Ada Deneme", m)


if __name__ == "__main__":
    unittest.main()
