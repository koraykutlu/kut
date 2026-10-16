"""Veri güvenliği: yapay zekâya kapalı kişi ikinci beynin bağlamına da girmez (visibility: private), arşiv kopyaları private ve
90 günde silinir, ham WhatsApp sohbeti analizden sonra (ya da 30 günde) silinir. Gerçek model çağrılmaz; sahte isimler kullanılır."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_analiz as an  # noqa: E402
import ag_cekirdek as c  # noqa: E402
import ag_sunucu as sunucu  # noqa: E402

GUN = 86400


def kisi(kid, ad, **alan):
    c.kisi_yaz(kid, {"ad": ad, "tur": "cevre", "yakinlik": "2", **alan}, f"# {ad}\n\n## Temas\n- (henüz yok)\n")


def ham(yol):
    with open(yol, encoding="utf-8") as f:
        return f.read()


def eskit(yol, gun):
    t = time.time() - gun * GUN
    os.utime(yol, (t, t))


def eski_surum(kid, gun):
    """Arşive `gun` gün önce alınmış gibi bir sürüm kopyası (ad tarihi + mtime eski)."""
    kopya = c.surum_al(kid)
    tarih = time.strftime("%Y%m%d", time.localtime(time.time() - gun * GUN))
    yeni = os.path.join(os.path.dirname(kopya), f"{kid}-{tarih}-000000-000000.md")
    os.replace(kopya, yeni)
    eskit(yeni, gun)
    return yeni


class VeriGuvenligiTest(unittest.TestCase):
    def setUp(self):
        self.eski = c.VERI
        self.t = tempfile.TemporaryDirectory()
        c.veri_klasoru(os.path.join(self.t.name, "veri"))
        c.ben_yaz({"ad": "Kerem"})
        kisi("ayse-yilmaz", "Ayşe Yılmaz")

    def tearDown(self):
        c.veri_klasoru(self.eski)
        self.t.cleanup()

    def yol(self, kid):
        return os.path.join(c.KISILER, kid + ".md")

    def test_kapali_kisi_private_olur_acilinca_geri_doner(self):
        self.assertNotIn("visibility:", ham(self.yol("ayse-yilmaz")))
        sunucu.kisi_uzak({"id": "ayse-yilmaz", "kapali": True})
        self.assertIn("\nvisibility: private\n", ham(self.yol("ayse-yilmaz")))
        c.kisi_guncelle("ayse-yilmaz", {"rol": "mühendis"})   # sonraki yazışlarda da korunur, tek satır kalır
        self.assertEqual(ham(self.yol("ayse-yilmaz")).count("visibility:"), 1)
        sunucu.kisi_uzak({"id": "ayse-yilmaz", "kapali": False})
        self.assertNotIn("visibility:", ham(self.yol("ayse-yilmaz")))

    def test_elle_yazilan_remote_allowed_da_private_yapar(self):
        kisi("mehmet-kaya", "Mehmet Kaya", remote_allowed="false")
        self.assertIn("visibility: private", ham(self.yol("mehmet-kaya")))

    def test_surum_kopyasi_private(self):
        kopya = c.surum_al("ayse-yilmaz")
        self.assertIn("visibility: private", ham(kopya))
        self.assertIn("title: Ayşe Yılmaz", ham(kopya))   # içerik korunur

    def test_arsiv_bakimi_sureyle_siler_ve_private_yapar(self):
        yeni = c.surum_al("ayse-yilmaz")
        eski = eski_surum("ayse-yilmaz", c.ARSIV_GUN + 1)
        haric = os.path.join(c.ARSIV, "haric", "biri.md")   # kullanıcının kararı: süreyle silinmez
        os.makedirs(os.path.dirname(haric))
        with open(haric, "w", encoding="utf-8") as f:
            f.write("# Biri\n")
        eskit(haric, c.ARSIV_GUN + 30)
        yedek = os.path.join(c.ARSIV, "yedek-dogrulama-oncesi-20200101-000000")
        os.makedirs(yedek)
        open(os.path.join(yedek, "iliskiler.md"), "w").close()
        s = c.arsiv_bakimi()
        self.assertFalse(os.path.exists(eski))
        self.assertTrue(os.path.exists(yeni))
        self.assertFalse(os.path.exists(yedek))
        self.assertTrue(os.path.exists(haric))
        self.assertTrue(ham(haric).startswith("---\nvisibility: private\n---\n# Biri"))
        self.assertEqual(s["silinen"], 2)
        self.assertEqual(c.arsiv_bakimi()["ozel"], 0)   # ikinci kez çalışınca dosyalara dokunmaz

    def test_ham_sohbet_30_gunde_silinir(self):
        wa = os.path.join(c.VERI, "gelen", "whatsapp")
        os.makedirs(wa)
        eski, yeni = os.path.join(wa, "eski.txt"), os.path.join(wa, "yeni.txt")
        for y in (eski, yeni):
            with open(y, "w", encoding="utf-8") as f:
                f.write("1.10.2026 10:00 - Ayşe: merhaba\n")
        eskit(eski, c.HAM_GUN + 1)
        self.assertEqual(c.arsiv_bakimi()["ham"], 1)
        self.assertFalse(os.path.exists(eski))
        self.assertTrue(os.path.exists(yeni))

    def test_analiz_bitince_ham_sohbet_silinir(self):
        wa = os.path.join(c.VERI, "gelen", "whatsapp")
        os.makedirs(wa)
        yol = os.path.join(wa, "ayse.txt")
        with open(yol, "w", encoding="utf-8") as f:
            f.write("1.10.2026 10:00 - Ayşe Yılmaz: merhaba\n")
        with mock.patch.object(an, "_model", return_value={"kisiler": {}}):
            an.analiz_et("ayse.txt", "Ayşe Yılmaz", {"Ayşe Yılmaz": "ayse-yilmaz"}, c.VERI)
        self.assertFalse(os.path.exists(yol))
        with self.assertRaisesRegex(RuntimeError, "artık yok"):
            an.analiz_et("ayse.txt", "Ayşe Yılmaz", {"Ayşe Yılmaz": "ayse-yilmaz"}, c.VERI)

    def test_model_hatasinda_ham_sohbet_kalir(self):
        wa = os.path.join(c.VERI, "gelen", "whatsapp")
        os.makedirs(wa)
        yol = os.path.join(wa, "ayse.txt")
        with open(yol, "w", encoding="utf-8") as f:
            f.write("1.10.2026 10:00 - Ayşe Yılmaz: merhaba\n")
        with mock.patch.object(an, "_model", side_effect=ValueError("modelden JSON gelmedi")):
            with self.assertRaises(ValueError):
                an.analiz_et("ayse.txt", "Ayşe Yılmaz", {"Ayşe Yılmaz": "ayse-yilmaz"}, c.VERI)
        self.assertTrue(os.path.exists(yol))   # tekrar denenebilsin

    # ---- denetim bulguları (16 Ekim 2026) ----
    def test_agdan_cikarilan_eski_dosya_hemen_silinmez(self):
        """Taşıma mtime'ı korur; yaş dosya adındaki arşive giriş tarihinden sayılır (90 gün geri alma payı gerçek)."""
        hedef = os.path.join(c.ARSIV, "cikarilan")
        os.makedirs(hedef)
        bugun = time.strftime("%Y%m%d")
        yeni = os.path.join(hedef, f"ayse-yilmaz-{bugun}.md")
        eski = os.path.join(hedef, "mehmet-kaya-20200101.md")
        for y in (yeni, eski):
            with open(y, "w", encoding="utf-8") as f:
                f.write("---\nad: X\n---\n")
            eskit(y, 400)   # kişi dosyası uzun süredir değişmemişti
        c.arsiv_bakimi()
        self.assertTrue(os.path.exists(yeni))
        self.assertFalse(os.path.exists(eski))

    @unittest.skipUnless(os.name == "nt", "junction yalnız Windows'ta")
    def test_bakim_junction_izlemez_disaridaki_dosyaya_dokunmaz(self):
        import subprocess
        dis = os.path.join(self.t.name, "dis")
        os.makedirs(dis)
        dis_dosya = os.path.join(dis, "onemli.md")
        with open(dis_dosya, "w", encoding="utf-8") as f:
            f.write("# önemli\n")
        eskit(dis_dosya, 400)
        surum = os.path.join(c.ARSIV, "surum")
        os.makedirs(surum)
        bag = os.path.join(surum, "baglanti")
        r = subprocess.run(["cmd", "/c", "mklink", "/J", bag, dis], capture_output=True)
        if r.returncode:
            self.skipTest("junction kurulamadı")
        yedek = os.path.join(c.ARSIV, "yedek-dogrulama-oncesi-20200101-000000")
        os.makedirs(yedek)
        r = subprocess.run(["cmd", "/c", "mklink", "/J", os.path.join(yedek, "bag"), dis], capture_output=True)
        c.arsiv_bakimi()
        self.assertTrue(os.path.exists(dis_dosya))
        self.assertEqual(ham(dis_dosya), "# önemli\n")   # private da yapılmadı

    @unittest.skipUnless(os.name == "nt", "junction yalnız Windows'ta")
    def test_suresi_dolan_yedekteki_junction_hedefindeki_bos_dizine_inmez(self):
        import subprocess
        dis = os.path.join(self.t.name, "dis2")
        os.makedirs(os.path.join(dis, "bosalt", "ic"))
        yedek = os.path.join(c.ARSIV, "yedek-dogrulama-oncesi-20200101-000000")
        os.makedirs(yedek)
        bag = os.path.join(yedek, "bag")
        if subprocess.run(["cmd", "/c", "mklink", "/J", bag, dis], capture_output=True).returncode:
            self.skipTest("junction kurulamadı")
        c.arsiv_bakimi()
        self.assertTrue(os.path.isdir(os.path.join(dis, "bosalt", "ic")))   # hedefin boş alt dizini de yerinde
        self.assertFalse(os.path.exists(yedek))   # süresi dolan yedek ve bağ girişi gitti

    def test_salt_okunur_eski_arsiv_dosyasi_da_silinir(self):
        import stat
        eski = eski_surum("ayse-yilmaz", c.ARSIV_GUN + 1)
        os.chmod(eski, stat.S_IREAD)
        eskit(eski, c.ARSIV_GUN + 1)
        c.arsiv_bakimi()
        self.assertFalse(os.path.exists(eski))

    def test_ayar_yazimi_eszamanli_bozulmaz(self):
        import threading
        import ag_ice_aktar as ia
        yol = os.path.join(self.t.name, "ayarlar.json")
        hatalar = []

        def yaz(n):
            for i in range(60):
                try:
                    ia._json_yaz(yol, {"is": n, "i": i})
                except OSError as e:
                    hatalar.append(e)
        isler = [threading.Thread(target=yaz, args=(n,)) for n in range(4)]
        [t.start() for t in isler]
        [t.join() for t in isler]
        self.assertEqual(hatalar, [])
        with open(yol, encoding="utf-8") as f:
            self.assertIn("is", json.load(f))
        self.assertEqual([f for f in os.listdir(self.t.name) if f.endswith(".tmp")], [])

    def test_ozet_goruldu_var_olmayan_haftayi_reddeder(self):
        import ag_ozet
        for h in ("2026-W99", "2026-W00", "2025-W53"):
            with self.assertRaises(ValueError):
                ag_ozet.goruldu(h)

    def test_bozuk_tarihli_yedek_bakimi_kesmez(self):
        os.makedirs(os.path.join(c.ARSIV, "yedek-dogrulama-oncesi-20260230-000000"))
        eski = eski_surum("ayse-yilmaz", c.ARSIV_GUN + 1)
        c.arsiv_bakimi()
        self.assertFalse(os.path.exists(eski))

    def test_ozel_yap_bom_kapanissiz_ve_mtime(self):
        d = os.path.join(c.ARSIV, "haric")
        os.makedirs(d)
        bom, kapanissiz = os.path.join(d, "bom.md"), os.path.join(d, "kapanissiz.md")
        with open(bom, "w", encoding="utf-8-sig") as f:
            f.write("---\nad: Ayşe\n---\ngövde\n")
        with open(kapanissiz, "w", encoding="utf-8") as f:
            f.write("---\nad: Mehmet\ngövde\n")
        eskit(bom, 10)
        once = os.path.getmtime(bom)
        c.arsiv_bakimi()
        self.assertEqual(ham(bom), "---\nad: Ayşe\nvisibility: private\n---\ngövde\n")   # tek frontmatter, BOM yok
        self.assertAlmostEqual(os.path.getmtime(bom), once, delta=2)   # süre sayacı sıfırlanmadı
        self.assertEqual(ham(kapanissiz), "---\nad: Mehmet\ngövde\n")   # bozuk dosyaya dokunulmadı

    def test_kapi_kopyasinda_ozet_ve_sonuclar_yok(self):
        import ag_kapi as kapi
        os.makedirs(os.path.join(c.VERI, "ozet"))
        with open(os.path.join(c.VERI, "ozet", "2026-W42.md"), "w", encoding="utf-8") as f:
            f.write("### 1. Ayşe Yılmaz\n- Adım: gizli not\n")
        with open(os.path.join(c.VERI, "sonuclar.md"), "w", encoding="utf-8") as f:
            f.write("| 1 | 2026-10-12 | ozet | ayse-yilmaz | gizli | bekliyor |  |  |\n")
        with kapi.kopya() as k:
            self.assertFalse(os.path.exists(os.path.join(k, "ozet")))
            self.assertFalse(os.path.exists(os.path.join(k, "sonuclar.md")))
            self.assertTrue(os.path.exists(os.path.join(k, "kisiler", "ayse-yilmaz.md")))


if __name__ == "__main__":
    unittest.main()
