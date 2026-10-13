"""Uzak model kapısı (ag_kapi): reddedilen kişi ne kopyada ne de sohbet isteminde bulunur. Gerçek `claude` çağrılmaz."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

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
import ag_model as mdl  # noqa: E402


def kisi(kid, ad, **alan):
    c.kisi_yaz(kid, {"ad": ad, "tur": "cevre", "yakinlik": "1", **alan}, f"# {ad}\n\n## Temas\n- 01.01.2026 · telefon · gizli-not-{kid}\n")


class KapiTest(unittest.TestCase):
    def setUp(self):
        self.eski = (c.VERI, ia.DEPO, ia.AYARLAR, ia.ADAYLAR, an.SOHBET_KLASOR)
        self.t = tempfile.TemporaryDirectory()
        self.veri, self.depo = os.path.join(self.t.name, "veri"), os.path.join(self.t.name, "depo")
        os.makedirs(self.depo)
        ia.DEPO, ia.AYARLAR, ia.ADAYLAR = self.depo, os.path.join(self.depo, "ayarlar.json"), os.path.join(self.depo, "adaylar.json")
        an.SOHBET_KLASOR = os.path.join(self.depo, "sohbet")
        c.veri_klasoru(self.veri)
        kisi("ada-deneme", "Ada Deneme")
        kisi("test-kisi", "Test Kişi", kurum="Örnek Parti")          # haric.md ile eşleşir
        kisi("gizli-biri", "Gizli Biri", remote_allowed="false")     # alan ile kapalı
        with open(c.HARIC, "a", encoding="utf-8") as f:
            f.write("- Örnek Parti\n")
        with open(c.ILISKILER, "a", encoding="utf-8") as f:
            f.write("| ada-deneme | test-kisi | tanisiyor | ortak | x | |\n| ada-deneme | gizli-biri | arkadas | y | x | |\n"
                    "| ada-deneme | ben | arkadas | ok-satir | x | |\n")
        os.makedirs(os.path.join(self.veri, "gelen", "whatsapp"))
        os.makedirs(os.path.join(c.BELGELER, "test-kisi"))
        os.makedirs(os.path.join(c.BELGELER, "ada-deneme"))
        for yol, ic in (("gelen/whatsapp/ada.txt", "merhaba"), ("gelen/whatsapp/test.txt", "selam"), ("gelen/whatsapp/sahipsiz.txt", "x"),
                        ("gelen/whatsapp/grup.txt", "Ada Deneme: hi\nTest Kişi: hey"), ("belgeler/test-kisi/cv.txt", "cv"),
                        ("belgeler/ada-deneme/cv.txt", "cv"), ("yorumlar/test-kisi.md", "yorum"), ("yorumlar/ada-deneme.md", "yorum"),
                        ("kilit-ayar.json", "{}"), ("ag.html", "<html>"), ("arsiv/surum/ada-deneme-1.md", "eski"), ("serbest.md", "genel not")):
            os.makedirs(os.path.dirname(os.path.join(self.veri, yol)), exist_ok=True)
            open(os.path.join(self.veri, yol), "w", encoding="utf-8").write(ic)
        os.makedirs(c.FOTO, exist_ok=True)
        for f in ("ada-deneme.png", "test-kisi.png", "gizli-biri.jpg"):
            open(os.path.join(c.FOTO, f), "wb").write(b"\x89PNG")
        with open(os.path.join(c.KISILER, "ada-deneme.md"), "a", encoding="utf-8") as f:   # sohbet dosyası kişi notunda anılır
            f.write("\nSohbet metni: `gelen/whatsapp/ada.txt, grup.txt`.\n")
        with open(os.path.join(c.KISILER, "test-kisi.md"), "a", encoding="utf-8") as f:
            f.write("\nSohbet metni: `gelen/whatsapp/test.txt`.\n")

    def tearDown(self):
        c.veri_klasoru(self.eski[0])
        ia.DEPO, ia.AYARLAR, ia.ADAYLAR, an.SOHBET_KLASOR = self.eski[1:]
        self.t.cleanup()

    def dosyalar(self, kok):
        return {os.path.relpath(os.path.join(y, f), kok).replace("\\", "/") for y, _, fs in os.walk(kok) for f in fs}

    def test_kapi_karar(self):
        k = kapi.Kapi()
        self.assertTrue(k.acik_mi("ada-deneme"))
        self.assertFalse(k.acik_mi("test-kisi"))      # haric
        self.assertFalse(k.acik_mi("gizli-biri"))     # remote_allowed: false
        self.assertFalse(k.acik_mi("yok-boyle-biri"))  # dosyası yok → kapalı
        self.assertFalse(k.acik_mi("../x"))

    def test_bozuk_kisi_dosyasi_kapali(self):
        open(os.path.join(c.KISILER, "bozuk.md"), "w", encoding="utf-8").write("frontmatter yok")
        self.assertFalse(kapi.Kapi().acik_mi("bozuk"))
        with kapi.kopya() as k:
            self.assertNotIn("kisiler/bozuk.md", self.dosyalar(k))

    def test_alan_yoksa_varsayilan_acik(self):
        kisi("serbest", "Serbest Kişi")
        self.assertTrue(kapi.Kapi().acik_mi("serbest"))

    def test_kopya_icerigi(self):
        with kapi.kopya() as k:
            d = self.dosyalar(k)
            self.assertIn("kisiler/ada-deneme.md", d)
            self.assertIn("foto/ada-deneme.png", d)
            self.assertIn("belgeler/ada-deneme/cv.txt", d)
            self.assertIn("serbest.md", d)
            self.assertIn("gelen/whatsapp/ada.txt", d)
            for yok in ("kisiler/test-kisi.md", "kisiler/gizli-biri.md", "foto/test-kisi.png", "foto/gizli-biri.jpg", "belgeler/test-kisi/cv.txt",
                        "yorumlar/test-kisi.md", "gelen/whatsapp/test.txt", "gelen/whatsapp/sahipsiz.txt", "gelen/whatsapp/grup.txt",
                        "haric.md", "ag.html", "kilit-ayar.json", "arsiv/surum/ada-deneme-1.md"):
                self.assertNotIn(yok, d, yok)
            self.assertTrue(k.startswith(os.path.realpath(self.depo)) or not k.startswith(os.path.realpath(self.veri)))
        self.assertFalse(os.path.exists(k))

    def test_ortak_dosyada_satir_atilir(self):
        with kapi.kopya() as k:
            il = open(os.path.join(k, "iliskiler.md"), encoding="utf-8").read()
            ak = open(os.path.join(k, "kisiler", "ada-deneme.md"), encoding="utf-8").read()
        self.assertNotIn("test-kisi", il)
        self.assertNotIn("gizli-biri", il)
        self.assertIn("ok-satir", il)
        self.assertNotIn("gizli-not-test-kisi", ak)
        self.assertIn("gizli-not-ada-deneme", ak)

    def test_ad_gecen_satir_atilir(self):
        open(os.path.join(self.veri, "notlar.md"), "w", encoding="utf-8").write("Test Kişi ile görüştüm\nÇay içtim\n")
        with kapi.kopya() as k:
            n = open(os.path.join(k, "notlar.md"), encoding="utf-8").read()
        self.assertNotIn("Test", n)
        self.assertIn("Çay", n)

    def test_sembolik_ve_dis_yol_atlanir(self):
        dis = os.path.join(self.t.name, "dis")
        os.makedirs(dis)
        open(os.path.join(dis, "sir.md"), "w", encoding="utf-8").write("dis")
        try:
            os.symlink(os.path.join(dis, "sir.md"), os.path.join(self.veri, "link.md"))
            os.symlink(dis, os.path.join(self.veri, "linkli-klasor"), target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("sembolik bağ oluşturulamadı (yetki yok)")
        with kapi.kopya() as k:
            d = self.dosyalar(k)
        self.assertNotIn("link.md", d)
        self.assertFalse([x for x in d if x.startswith("linkli-klasor")])

    @unittest.skipUnless(os.name == "nt", "junction yalnız Windows")
    def test_junction_atlanir(self):
        dis = os.path.join(self.t.name, "dis2")
        os.makedirs(dis)
        open(os.path.join(dis, "sir.md"), "w", encoding="utf-8").write("dis")
        if subprocess.run(["cmd", "/c", "mklink", "/J", os.path.join(self.veri, "kavsak"), dis], capture_output=True).returncode:
            self.skipTest("junction oluşturulamadı")
        with kapi.kopya() as k:
            self.assertFalse([x for x in self.dosyalar(k) if x.startswith("kavsak")])

    def test_dis_yola_cozulen_atlanir(self):
        kok = os.path.normcase(os.path.realpath(self.veri))
        self.assertTrue(kapi._gercek(os.path.join(self.veri, "serbest.md"), kok))
        self.assertFalse(kapi._gercek(os.path.join(self.t.name, "depo"), kok))

    def sohbet_cagir(self, kisi_id="", oturum="", hata=None):
        yakalanan = {}

        def sahte(arg, **kw):
            yakalanan["arg"], yakalanan["istem"] = arg, kw["input"].decode("utf-8")
            yakalanan["dizin"] = arg[arg.index("--add-dir") + 1]
            yakalanan["var"] = os.path.isdir(yakalanan["dizin"])
            yakalanan["dosyalar"] = self.dosyalar(yakalanan["dizin"])
            if hata:
                raise hata
            return subprocess.CompletedProcess(arg, 0, json.dumps({"result": "tamam", "session_id": "s"}).encode(), b"")
        with mock.patch.object(mdl, "yol_bul", return_value="claude"), mock.patch.object(mdl, "hazir", return_value=True), mock.patch.object(mdl.subprocess, "run", side_effect=sahte):
            try:
                an.sohbet("Kimle görüşeyim?", kisi_id, oturum)
            except RuntimeError:
                pass
        return yakalanan

    def test_sohbet_istemi_reddedileni_icermez(self):
        y = self.sohbet_cagir()
        self.assertIn("Ada Deneme", y["istem"])
        for yok in ("Test Kişi", "test-kisi", "Gizli Biri", "gizli-biri", "gizli-not-test-kisi"):
            self.assertNotIn(yok, y["istem"])
        self.assertTrue(y["var"])
        self.assertNotIn("kisiler/test-kisi.md", y["dosyalar"])
        self.assertNotEqual(os.path.realpath(y["dizin"]), os.path.realpath(self.veri))
        self.assertFalse(os.path.exists(y["dizin"]))   # çağrı bitince silindi

    def test_acik_reddedilen_kart_gonderilmez(self):
        for kid in ("test-kisi", "gizli-biri"):
            for oturum in ("", "a" * 24):
                y = self.sohbet_cagir(kid, oturum)
                self.assertNotIn("gizli-not", y["istem"])
                self.assertNotIn("Test Kişi", y["istem"])
                self.assertNotIn(kid, y["istem"])
                self.assertIn("gizlilik", y["istem"])

    def test_acik_izinli_kart_gonderilir(self):
        y = self.sohbet_cagir("ada-deneme")
        self.assertIn("gizli-not-ada-deneme", y["istem"])
        self.assertNotIn("test-kisi", y["istem"])

    def test_hata_olsa_da_gecici_klasor_silinir(self):
        y = self.sohbet_cagir(hata=RuntimeError("patladi"))
        self.assertFalse(os.path.exists(y["dizin"]))

    def test_oturumsuz_saglayicida_baglam_her_turda_verilir(self):
        ia.ayar_yaz({"saglayici": "codex"})
        istemler = []

        def sahte(gorev, istem, **kw):
            istemler.append((istem, kw))
            return mdl.Cevap(f"cevap{len(istemler)}")
        with mock.patch.object(mdl, "hazir", return_value=True), mock.patch.object(mdl, "cagir", side_effect=sahte):
            r1 = an.sohbet("Birinci soru?")
            r2 = an.sohbet("Ikinci soru?", "", r1["oturum"])
        self.assertTrue(r1["oturum"])
        self.assertEqual(r2["oturum"], r1["oturum"])
        self.assertIn("Ada Deneme", istemler[1][0])            # ağ bağlamı yeniden verildi
        self.assertIn("Birinci soru?", istemler[1][0])         # geçmiş de
        self.assertNotIn("Test Kişi", istemler[1][0])          # kapı yine geçerli
        self.assertTrue(istemler[1][1]["veri_klasoru"])

    def _oturumsuz_sohbet(self):
        ia.ayar_yaz({"saglayici": "codex"})
        istemler = []

        def sahte(gorev, istem, **kw):
            istemler.append(istem)
            return mdl.Cevap(f"cevap{len(istemler)}")
        mock.patch.object(mdl, "hazir", return_value=True).start()
        mock.patch.object(mdl, "cagir", side_effect=sahte).start()
        mdl.gecmis_temizle()
        return istemler

    def test_gecmis_her_turda_kapidan_gecer(self):
        istemler = self._oturumsuz_sohbet()
        try:
            r1 = an.sohbet("Birinci soru?")
            # geçmişe sonradan reddedilen kişiyi anan bir tur ve bir sır girmiş olsun
            mdl.gecmis_ekle(r1["oturum"], "Test Kişi ile ne konuştuk?", "gizli-not-test-kisi içeriği")
            mdl.gecmis_ekle(r1["oturum"], "anahtar?", "api_key=sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123")
            an.sohbet("Ikinci soru?", "", r1["oturum"])
        finally:
            mock.patch.stopall()
        son = istemler[1]
        self.assertIn("Birinci soru?", son)
        self.assertNotIn("Test Kişi", son)
        self.assertNotIn("gizli-not-test-kisi", son)
        self.assertNotIn("sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123", son)

    def test_kapi_degisince_gecmis_silinir(self):
        istemler = self._oturumsuz_sohbet()
        try:
            r1 = an.sohbet("Birinci ozel soru?")
            kisi("yeni-kapali", "Yeni Kapalı", remote_allowed="false")   # kapı listesi değişti
            r2 = an.sohbet("Ikinci soru?", "", r1["oturum"])
            an.sohbet("Ucuncu soru?", "", r2["oturum"])
        finally:
            mock.patch.stopall()
        self.assertNotIn("Birinci ozel soru?", istemler[1])   # geçmiş silindi
        self.assertIn("Ikinci soru?", istemler[2])             # yeni kapıyla biriken geçmiş sürer

    def test_kilitlenince_gecmis_silinir(self):
        istemler = self._oturumsuz_sohbet()
        import ag_kilit
        mdl._kilit_bagla()
        try:
            r1 = an.sohbet("Birinci soru?")
            ag_kilit.kapat()
            an.sohbet("Ikinci soru?", "", r1["oturum"])
        finally:
            mock.patch.stopall()
        self.assertNotIn("Birinci soru?", istemler[1])

    def test_belge_ekle_claude_disinda_pdf_icin_bastan_hata_verir(self):
        import base64
        import ag_sunucu as sunucu
        ia.ayar_yaz({"saglayici": "codex"})
        g = {"id": "ada-deneme", "ad": "cv.pdf", "veri": base64.b64encode(b"%PDF-1.4 x").decode()}
        with mock.patch.object(mdl, "hazir", return_value=True), mock.patch.object(an, "belge_kuyruga_ekle") as kuyruk:
            with self.assertRaisesRegex(ValueError, "PDF/görsel belge okuyamaz"):
                sunucu.belge_ekle(dict(g))
            self.assertFalse(os.path.exists(os.path.join(c.BELGELER, "ada-deneme", "cv.pdf")))   # dosya da yazılmadı
            kuyruk.assert_not_called()
            r = sunucu.belge_ekle({**g, "ozetle": False})   # özetleme istenmiyorsa yalnız saklanır
            self.assertFalse(r["analiz"])
            r = sunucu.belge_ekle({"id": "ada-deneme", "ad": "not.txt", "veri": base64.b64encode(b"metin").decode()})
            self.assertTrue(r["analiz"])   # metin belgeleri Claude dışında da özetlenir

    def test_analiz_reddedileni_uzak_modele_vermez(self):
        with mock.patch.object(an, "_model") as m, mock.patch.object(an, "claude_yolu", return_value="claude"):
            with self.assertRaises(RuntimeError):
                an.analiz_et("test.txt", "Sohbet", {"Test Kişi": "test-kisi"}, self.veri)
            with self.assertRaises(RuntimeError):
                an.analiz_et("grup.txt", "Grup", {"Ada Deneme": "ada-deneme", "Gizli Biri": "gizli-biri"}, self.veri)
            with self.assertRaises(RuntimeError):
                an.belge_analiz_et("gizli-biri", "cv.txt")
            m.assert_not_called()

    def test_wa_sahibi_analiz_durumundan(self):
        os.makedirs(os.path.join(self.depo, "analiz"))
        json.dump({"isler": [{"ham": "sahipsiz.txt", "kisiler": ["ada-deneme"]}]}, open(os.path.join(self.depo, "analiz", "durum.json"), "w"))
        with kapi.kopya() as k:
            self.assertIn("gelen/whatsapp/sahipsiz.txt", self.dosyalar(k))


if __name__ == "__main__":
    unittest.main()
