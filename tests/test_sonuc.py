"""Sonuç döngüsü (ag_sonuc): sonuclar.md okuma/yazma, tekrar engeli, işaretleme + temas, öğrenme kuralları (ayar), istatistik.
Kurgusal adlar; geçici veri klasörü, gerçek veriye dokunulmaz."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_cekirdek as c  # noqa: E402
import ag_sonuc as sn  # noqa: E402

BUGUN = date(2026, 10, 19)   # pazartesi, 2026-W43


def kayit(no, kisi, sonuc, gun_once=0, kapanis_gun_once=None, kaynak="ozet", oneri="Selam yaz", **ek):
    """Bellekte kayıt (ayar/istatistik/bekleyenler saf işlevleri için)."""
    t = BUGUN - timedelta(days=gun_once)
    kap = "" if sonuc == "bekliyor" else (BUGUN - timedelta(days=gun_once if kapanis_gun_once is None else kapanis_gun_once)).isoformat()
    return {"no": no, "tarih": t.isoformat(), "kaynak": kaynak, "kisi": kisi, "oneri": oneri, "sonuc": sonuc, "not": "", "kapanis": kap, **ek}


class SonucTabanTest(unittest.TestCase):
    def setUp(self):
        self.eski = c.VERI
        self.t = tempfile.TemporaryDirectory()
        self.veri = os.path.join(self.t.name, "veri")
        c.veri_klasoru(self.veri)
        c.ben_yaz({"ad": "Umut"})

    def tearDown(self):
        c.veri_klasoru(self.eski)
        self.t.cleanup()

    def dosya(self):
        return os.path.join(self.veri, "sonuclar.md")

    def metin(self):
        with open(self.dosya(), encoding="utf-8") as f:
            return f.read()

    def yaz(self, metin):
        with open(self.dosya(), "w", encoding="utf-8", newline="") as f:
            f.write(metin)

    def kisi(self, kid, ad, govde=None, **alan):
        c.kisi_yaz(kid, {"ad": ad, "tur": "cevre", "yakinlik": "2", **alan}, govde if govde is not None else f"# {ad}\n\n## Temas\n- (henüz yok)\n")

    def kisi_oku(self, kid):
        return c.kisi_oku(os.path.join(c.KISILER, kid + ".md"))


class DosyaTest(SonucTabanTest):
    def test_dosya_yoksa_bos_liste(self):
        self.assertEqual(sn.oku(), [])
        self.assertFalse(os.path.exists(self.dosya()))

    def test_ilk_kayit_basliklarla_dosyayi_kurar(self):
        no = sn.kaydet("ozet", "selin-hoca", "Açık veri çağrısı için yaz", BUGUN)
        self.assertEqual(no, 1)
        m = self.metin()
        self.assertTrue(m.startswith("---\nvisibility: private\n---\n# Kut önerileri ve sonuçları\nKut'un önerdiği adımlar ve senin kararın."))
        self.assertIn("| no | tarih | kaynak | kisi | oneri | sonuc | not | kapanis |\n|---|---|---|---|---|---|---|---|\n", m)
        self.assertIn("| 1 | 2026-10-19 | ozet | selin-hoca | Açık veri çağrısı için yaz | bekliyor |  |  |\n", m)
        self.assertTrue(m.endswith("|\n"))
        self.assertEqual(sn.oku(), [{"no": 1, "tarih": "2026-10-19", "kaynak": "ozet", "kisi": "selin-hoca", "oneri": "Açık veri çağrısı için yaz",
                                     "sonuc": "bekliyor", "not": "", "kapanis": ""}])

    def test_numaralar_artar_ve_sira_korunur(self):
        a = sn.kaydet("ozet", "ayse-yilmaz", "Bir", BUGUN)
        b = sn.kaydet("yol", "mehmet-kaya", "İki", BUGUN)
        d = sn.kaydet("brifing", "", "Üç", BUGUN)
        self.assertEqual((a, b, d), (1, 2, 3))
        self.assertEqual([r["oneri"] for r in sn.oku()], ["Bir", "İki", "Üç"])
        self.assertEqual(self.metin().count("\n| "), 4)   # başlık satırı + 3 kayıt

    def test_tekrar_engeli_ayni_hafta_ayni_anahtar(self):
        no = sn.kaydet("ozet", "ayse-yilmaz", "Kısa bir selam yaz", BUGUN)
        self.assertEqual(sn.kaydet("ozet", "ayse-yilmaz", "Kısa bir selam yaz", BUGUN + timedelta(days=3)), no)   # aynı hafta (cuma)
        self.assertEqual(sn.kaydet("ozet", "ayse-yilmaz", "  kisa BİR selam   yaz ", BUGUN), no)                 # sadeleştirilmiş eşleşme
        self.assertEqual(len(sn.oku()), 1)

    def test_tekrar_engeli_baska_hafta_kaynak_kisi_oneri_ayri_kayittir(self):
        no = sn.kaydet("ozet", "ayse-yilmaz", "Kısa bir selam yaz", BUGUN)
        digerleri = {sn.kaydet("ozet", "ayse-yilmaz", "Kısa bir selam yaz", BUGUN + timedelta(days=7)),   # sonraki ISO hafta
                     sn.kaydet("ozet", "ayse-yilmaz", "Kısa bir selam yaz", BUGUN - timedelta(days=1)),   # önceki hafta (pazar)
                     sn.kaydet("yol", "ayse-yilmaz", "Kısa bir selam yaz", BUGUN),
                     sn.kaydet("ozet", "mehmet-kaya", "Kısa bir selam yaz", BUGUN),
                     sn.kaydet("ozet", "ayse-yilmaz", "Başka öneri", BUGUN)}
        self.assertEqual(len(digerleri | {no}), 6)

    def test_tekrar_engeli_yil_sonu_iso_haftasi(self):
        a = sn.kaydet("ozet", "ayse-yilmaz", "X", date(2026, 12, 31))   # 2026-W53
        self.assertEqual(sn.kaydet("ozet", "ayse-yilmaz", "X", date(2027, 1, 3)), a)   # pazar, aynı ISO hafta
        self.assertNotEqual(sn.kaydet("ozet", "ayse-yilmaz", "X", date(2027, 1, 4)), a)

    def test_kaydet_dogrulama(self):
        for kaynak, kisi, oneri in (("bilinmez", "a", "x"), ("ozet", "Büyük Harf", "x"), ("ozet", "../kaçış", "x"), ("ozet", "ayse", "   "), ("ozet", "ayse", "|\n|")):
            if kaynak == "ozet" and oneri == "|\n|":
                continue   # yalnız ayraç: temizlenince "/ /" kalır, boş değil
            with self.assertRaises(ValueError, msg=(kaynak, kisi, oneri)):
                sn.kaydet(kaynak, kisi, oneri, BUGUN)
        self.assertFalse(os.path.exists(self.dosya()))

    def test_hucre_temizligi(self):
        no = sn.kaydet("elle", "ayse-yilmaz", "ilk | ikinci\nüçüncü\r\ndördüncü\t beşinci", BUGUN)
        (r,) = sn.oku()
        self.assertEqual(r["oneri"], "ilk / ikinci üçüncü dördüncü beşinci")
        self.assertEqual(len(self.metin().strip().splitlines()), 9)   # başlık, açıklama, boş, tablo başlığı, ayırıcı + tek kayıt satırı
        uzun = sn.kaydet("elle", "ayse-yilmaz", "u" * 500, BUGUN)
        self.assertEqual(len(next(x for x in sn.oku() if x["no"] == uzun)["oneri"]), sn.HUCRE_AZAMI)
        sir = sn.kaydet("elle", "ayse-yilmaz", "api_key=sk-abcdef1234567890ABCDEF12 ile bağlan", BUGUN)
        oneri = next(x for x in sn.oku() if x["no"] == sir)["oneri"]
        self.assertNotIn("sk-abcdef", oneri)
        self.assertIn("[gizlendi]", oneri)
        self.assertEqual(no, 1)

    def test_not_hucresi_da_temizlenir(self):
        no = sn.kaydet("ozet", "ayse-yilmaz", "Yaz", BUGUN)
        sn.isaretle(no, "yaptim", "iyi | geçti\nçok", bugun=BUGUN)
        self.assertEqual(sn.oku()[0]["not"], "iyi / geçti çok")

    def test_elle_duzenlenmis_dosya_korunur(self):
        self.yaz("# Benim önerilerim\n\nBurası benim notum: bu satırlar kalsın.\n\n"
                 "| no | tarih | kaynak | kisi | oneri | sonuc | not | kapanis |\n|---|---|---|---|---|---|---|---|\n"
                 "| 1 | 2026-10-12 | ozet | selin-hoca | Açık veri çağrısı için yaz | bekliyor |  |  |\n"
                 "bozuk bir satır, tablo değil\n"
                 "| 7 | yarın | ozet | ayse-yilmaz | tarihi bozuk | bekliyor |  |  |\n"
                 "| x | 2026-10-12 | ozet | ayse-yilmaz | numarası bozuk | bekliyor |  |  |\n"
                 "| 2 | 2026-10-13 | bilinmez | mehmet-kaya | Elle eklediğim | İşe yaradı | güzel | 2026-10-14 |\n"
                 "\nAltta serbest metin kalsın.\n")
        self.assertEqual([r["no"] for r in sn.oku()], [1, 2])
        self.assertEqual(sn.oku()[1]["sonuc"], "ise_yaradi")         # etiketle yazılmış sonuç tanınır
        self.assertEqual(sn.oku()[1]["kaynak"], "elle")              # bilinmeyen kaynak 'elle'
        yeni = sn.kaydet("yol", "mehmet-kaya", "Yeni", BUGUN)
        self.assertEqual(yeni, 8)                                    # bozuk satırın no'su (7) bile yeniden kullanılmaz
        m = self.metin()
        self.assertTrue(m.startswith("---\nvisibility: private\n---\n# Benim önerilerim\n\nBurası benim notum: bu satırlar kalsın.\n"))
        self.assertIn("bozuk bir satır, tablo değil\n", m)
        self.assertIn("| x | 2026-10-12 | ozet | ayse-yilmaz | numarası bozuk | bekliyor |  |  |\n", m)
        self.assertTrue(m.endswith("\nAltta serbest metin kalsın.\n"))
        satirlar = m.split("\n")
        self.assertEqual(satirlar[satirlar.index("| 2 | 2026-10-13 | bilinmez | mehmet-kaya | Elle eklediğim | İşe yaradı | güzel | 2026-10-14 |") + 1], "| 8 | 2026-10-19 | yol | mehmet-kaya | Yeni | bekliyor |  |  |")

    def test_isaretle_yerinde_gunceller_gerisine_dokunmaz(self):
        self.yaz("# Başlık\naçıklama\n\n| no | tarih | kaynak | kisi | oneri | sonuc | not | kapanis |\n|---|---|---|---|---|---|---|---|\n"
                 "| 1 | 2026-10-12 | ozet | a | Bir | bekliyor |  |  |\n| bozuk\n| 2 | 2026-10-12 | ozet | b | İki | bekliyor |  |  |\n\nSon not\n")
        sn.isaretle(2, "atlandi", bugun=BUGUN)
        self.assertEqual(self.metin(), "---\nvisibility: private\n---\n# Başlık\naçıklama\n\n| no | tarih | kaynak | kisi | oneri | sonuc | not | kapanis |\n|---|---|---|---|---|---|---|---|\n"
                                       "| 1 | 2026-10-12 | ozet | a | Bir | bekliyor |  |  |\n| bozuk\n| 2 | 2026-10-12 | ozet | b | İki | atlandi |  | 2026-10-19 |\n\nSon not\n")

    def test_tablosuz_dosyaya_tablo_eklenir(self):
        self.yaz("# Notlarım\nsadece metin\n")
        sn.kaydet("elle", "", "Bir not", BUGUN)
        m = self.metin()
        self.assertTrue(m.startswith("---\nvisibility: private\n---\n# Notlarım\nsadece metin\n"))
        self.assertIn("| no | tarih |", m)
        self.assertEqual(len(sn.oku()), 1)

    def test_bom_ve_crlf_okunur(self):
        self.yaz("﻿# B\r\n\r\n| no | tarih | kaynak | kisi | oneri | sonuc | not | kapanis |\r\n|---|---|---|---|---|---|---|---|\r\n"
                 "| 1 | 2026-10-12 | ozet | a | Bir | yaptim |  | 2026-10-13 |\r\n")
        self.assertEqual([(r["no"], r["sonuc"]) for r in sn.oku()], [(1, "yaptim")])
        sn.kaydet("ozet", "a", "İki", BUGUN)
        self.assertEqual([r["no"] for r in sn.oku()], [1, 2])
        self.assertNotIn("\r", self.metin())

    def test_eksik_ve_fazla_hucre(self):
        self.yaz("| 1 | 2026-10-12 | ozet | a | Eksik hücreli |\n| 2 | 2026-10-12 | ozet | a | Fazla | bekliyor | n | | ekstra |\n| 3 | 2026-10-12 | ozet | a | Sonuç tanınmıyor | bilmem |  |  |\n")
        self.assertEqual([(r["no"], r["sonuc"]) for r in sn.oku()], [(1, "bekliyor")])

    def test_ozel_gorunurluk_frontmatter(self):
        sn.kaydet("ozet", "a", "Bir", BUGUN)
        self.assertTrue(self.metin().startswith("---\nvisibility: private\n---\n"))
        sn.kaydet("ozet", "a", "İki", BUGUN)
        sn.isaretle(1, "yaptim", bugun=BUGUN)
        self.assertEqual(self.metin().count("visibility: private"), 1)          # her yazışta tekrar eklenmez
        self.assertEqual([r["no"] for r in sn.oku()], [1, 2])                    # frontmatter okumayı bozmaz

    def test_frontmattersiz_eski_dosya_ilk_yazista_ozel_yapilir(self):
        self.yaz("# Eski\nelle yazılmış açıklama\n\n| no | tarih | kaynak | kisi | oneri | sonuc | not | kapanis |\n|---|---|---|---|---|---|---|---|\n"
                 "| 1 | 2026-10-12 | ozet | a | Bir | bekliyor |  |  |\n")
        self.assertEqual([r["no"] for r in sn.oku()], [1])                       # frontmattersız dosya okunur
        sn.kaydet("ozet", "a", "İki", BUGUN)
        self.assertTrue(self.metin().startswith("---\nvisibility: private\n---\n# Eski\nelle yazılmış açıklama\n"))

    def test_mevcut_frontmatter_korunur_visibility_eklenir(self):
        self.yaz("\ufeff---\netiket: x\n---\n# Eski\n\n| no | tarih | kaynak | kisi | oneri | sonuc | not | kapanis |\n|---|---|---|---|---|---|---|---|\n"
                 "| 1 | 2026-10-12 | ozet | a | Bir | bekliyor |  |  |\n")
        self.assertEqual([r["no"] for r in sn.oku()], [1])                       # BOM + frontmatter okunur
        sn.kaydet("ozet", "a", "İki", BUGUN)
        self.assertTrue(self.metin().startswith("---\netiket: x\nvisibility: private\n---\n# Eski\n"))
        self.yaz("---\nvisibility: public\n---\n| 1 | 2026-10-12 | ozet | a | Bir | bekliyor |  |  |\n")
        sn.kaydet("ozet", "a", "Üç", BUGUN)
        self.assertTrue(self.metin().startswith("---\nvisibility: public\n---\n"))   # kullanıcının açık seçimi ezilmez

    def test_yazma_atomik_hata_dosyayi_bozmaz(self):
        sn.kaydet("ozet", "a", "Bir", BUGUN)
        once = self.metin()
        with mock.patch("ag_sonuc.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                sn.kaydet("ozet", "a", "İki", BUGUN)
        self.assertEqual(self.metin(), once)
        self.assertEqual([f for f in os.listdir(self.veri) if f.endswith(".tmp") or f.endswith(".kilit")], [])   # geçici dosya ve kilit kalmadı

    def test_kilit_dosyasi_birakilmaz_ve_bayati_kirilir(self):
        sn.kaydet("ozet", "a", "Bir", BUGUN)
        self.assertFalse(os.path.exists(self.dosya() + ".kilit"))
        kilit = self.dosya() + ".kilit"
        with open(kilit, "w") as f:
            f.write("")
        eski = time.time() - 3600
        os.utime(kilit, (eski, eski))   # çöken süreçten kalma bayat kilit
        bas = time.monotonic()
        sn.kaydet("ozet", "a", "İki", BUGUN)
        self.assertLess(time.monotonic() - bas, 3)
        self.assertFalse(os.path.exists(kilit))

    def test_eszamanli_yazanlar_kayit_kaybetmez(self):
        hatalar = []

        def calis(i):
            try:
                sn.kaydet("ozet", "a", f"Öneri {i}", BUGUN)
            except Exception as e:   # noqa: BLE001
                hatalar.append(e)
        isler = [threading.Thread(target=calis, args=(i,)) for i in range(24)]
        for t in isler:
            t.start()
        for t in isler:
            t.join()
        self.assertEqual(hatalar, [])
        nolar = [r["no"] for r in sn.oku()]
        self.assertEqual(sorted(nolar), list(range(1, 25)))

    def test_veri_klasoru_degisince_yol_degisir(self):
        sn.kaydet("ozet", "a", "Bir", BUGUN)
        baska = os.path.join(self.t.name, "baska")
        c.veri_klasoru(baska)
        self.assertEqual(sn.oku(), [])
        self.assertEqual(sn.yol(), os.path.join(os.path.abspath(baska), "sonuclar.md"))


class IsaretleTest(SonucTabanTest):
    def setUp(self):
        super().setUp()
        self.kisi("selin-hoca", "Selin Hoca", "# Selin Hoca\n\n## Temas\n- 01.09.2026 · whatsapp · Tez konusu\n", son_temas="2026-09-01")
        self.no = sn.kaydet("ozet", "selin-hoca", "Açık veri çağrısı için yaz", BUGUN)

    def test_sonuc_dogrulanir(self):
        for kotu in ("bitti", "", None, "YAPTIM"):
            with self.assertRaises(ValueError, msg=kotu):
                sn.isaretle(self.no, kotu, bugun=BUGUN)
        with self.assertRaises(ValueError):
            sn.isaretle(99, "yaptim", bugun=BUGUN)
        with self.assertRaises(ValueError):
            sn.isaretle("abc", "yaptim", bugun=BUGUN)
        self.assertEqual(sn.oku()[0]["sonuc"], "bekliyor")

    def test_kapanis_ve_not(self):
        s = sn.isaretle(self.no, "ertelendi", "haftaya", bugun=BUGUN + timedelta(days=2))
        self.assertEqual(s, {"no": self.no, "sonuc": "ertelendi", "temas_eklendi": False})
        r = sn.oku()[0]
        self.assertEqual((r["sonuc"], r["kapanis"], r["not"]), ("ertelendi", "2026-10-21", "haftaya"))
        sn.isaretle(str(self.no), "yaptim", bugun=BUGUN + timedelta(days=3))   # no metin olarak da gelebilir; not verilmediyse eski not kalır
        r = sn.oku()[0]
        self.assertEqual((r["sonuc"], r["kapanis"], r["not"]), ("yaptim", "2026-10-22", "haftaya"))
        sn.isaretle(self.no, "bekliyor", bugun=BUGUN + timedelta(days=4))
        r = sn.oku()[0]
        self.assertEqual((r["sonuc"], r["kapanis"]), ("bekliyor", ""))

    def test_temas_eklenir_ve_son_temas_ilerler(self):
        self.assertEqual(self.kisi_oku("selin-hoca")["son_temas"], "2026-09-01")
        s = sn.isaretle(self.no, "ise_yaradi", temas=True, kanal="whatsapp", bugun=BUGUN)
        self.assertTrue(s["temas_eklendi"])
        k = self.kisi_oku("selin-hoca")
        self.assertIn("- 19.10.2026 · whatsapp · Kut önerisi: Açık veri çağrısı için yaz", k["govde"])
        self.assertIn("- 01.09.2026 · whatsapp · Tez konusu", k["govde"])   # eski satır korundu
        self.assertEqual(k["son_temas"], "2026-10-19")
        self.assertEqual(k["ad"], "Selin Hoca")

    def test_temas_surum_kopyasi_alinir(self):
        surumler = lambda: [f for f in os.listdir(os.path.join(c.ARSIV, "surum"))] if os.path.isdir(os.path.join(c.ARSIV, "surum")) else []
        self.assertEqual(surumler(), [])
        sn.isaretle(self.no, "yaptim", temas=True, bugun=BUGUN)
        self.assertEqual(len([f for f in surumler() if f.startswith("selin-hoca-")]), 1)

    def test_ayni_temas_iki_kez_eklenmez(self):
        self.assertTrue(sn.isaretle(self.no, "yaptim", temas=True, kanal="whatsapp", bugun=BUGUN)["temas_eklendi"])
        self.assertFalse(sn.isaretle(self.no, "ise_yaradi", temas=True, kanal="whatsapp", bugun=BUGUN)["temas_eklendi"])
        self.assertEqual(self.kisi_oku("selin-hoca")["govde"].count("Kut önerisi"), 1)
        # başka gün aynı öneri: yeni bir temas günü
        self.assertTrue(sn.isaretle(self.no, "ise_yaradi", temas=True, kanal="whatsapp", bugun=BUGUN + timedelta(days=1))["temas_eklendi"])
        self.assertEqual(self.kisi_oku("selin-hoca")["govde"].count("Kut önerisi"), 2)

    def test_son_temas_geri_gitmez(self):
        c.kisi_yaz("selin-hoca", {**{k: v for k, v in self.kisi_oku("selin-hoca").items() if k != "govde"}, "son_temas": "2026-10-25"}, "# S\n\n## Temas\n- (henüz yok)\n")
        sn.isaretle(self.no, "yaptim", temas=True, bugun=BUGUN)
        self.assertEqual(self.kisi_oku("selin-hoca")["son_temas"], "2026-10-25")
        self.assertIn("Kut önerisi", self.kisi_oku("selin-hoca")["govde"])

    def test_temas_istenmediyse_ya_da_sonuc_uygun_degilse_eklenmez(self):
        for sonuc, temas in (("yaptim", False), ("atlandi", True), ("ertelendi", True), ("bekliyor", True)):
            s = sn.isaretle(self.no, sonuc, temas=temas, bugun=BUGUN)
            self.assertFalse(s["temas_eklendi"], (sonuc, temas))
        self.assertNotIn("Kut önerisi", self.kisi_oku("selin-hoca")["govde"])
        self.assertEqual(self.kisi_oku("selin-hoca")["son_temas"], "2026-09-01")

    def test_haric_kisiye_temas_eklenmez_sonuc_kaydedilir(self):
        with open(c.HARIC, "a", encoding="utf-8") as f:
            f.write("- Örnek Parti\n")
        self.kisi("deniz-demo", "Deniz Demo", kurum="Örnek Parti")
        no = sn.kaydet("ozet", "deniz-demo", "Selam yaz", BUGUN)
        once = self.kisi_oku("deniz-demo")["govde"]
        s = sn.isaretle(no, "yaptim", temas=True, bugun=BUGUN)
        self.assertEqual((s["sonuc"], s["temas_eklendi"]), ("yaptim", False))
        self.assertEqual(self.kisi_oku("deniz-demo")["govde"], once)
        self.assertEqual(next(r for r in sn.oku() if r["no"] == no)["sonuc"], "yaptim")

    def test_olmayan_ya_da_kisisiz_kayitta_temas_yok_sonuc_var(self):
        no1 = sn.kaydet("ozet", "kimse-yok", "Yaz", BUGUN)
        no2 = sn.kaydet("elle", "", "Genel not", BUGUN)
        for no in (no1, no2):
            s = sn.isaretle(no, "ise_yaramadi", temas=True, bugun=BUGUN)
            self.assertEqual((s["sonuc"], s["temas_eklendi"]), ("ise_yaramadi", False))
        self.assertFalse(os.path.exists(os.path.join(c.KISILER, "kimse-yok.md")))   # kişi dosyası açılmaz

    def test_merkez_kisiye_temas_yazilmaz(self):
        no = sn.kaydet("elle", c.ben_id(), "Kendine not", BUGUN)
        self.assertFalse(sn.isaretle(no, "yaptim", temas=True, bugun=BUGUN)["temas_eklendi"])

    def test_kanal_ve_oneri_satir_bicimini_bozamaz(self):
        no = sn.kaydet("ozet", "selin-hoca", "iki · parça öneri", BUGUN)
        sn.isaretle(no, "yaptim", temas=True, kanal="yüz yüze · kahve\nyeni satır", bugun=BUGUN)
        satir = [l for l in self.kisi_oku("selin-hoca")["govde"].splitlines() if "iki - parça" in l]
        self.assertEqual(satir, ["- 19.10.2026 · yüz yüze - kahve yeni satır · Kut önerisi: iki - parça öneri"])
        sn.isaretle(self.no, "yaptim", temas=True, bugun=BUGUN)   # kanal verilmezse 'diğer'
        self.assertIn("- 19.10.2026 · diğer · Kut önerisi: Açık veri çağrısı için yaz", self.kisi_oku("selin-hoca")["govde"])


class AyarTest(unittest.TestCase):
    """Öğrenme kuralları: her kural ayrı, saf (dosya yok)."""

    def ayar(self, kayitlar, kid="a"):
        return sn.ayar(kid, BUGUN, kayitlar)

    def test_kayit_yoksa_varsayilan(self):
        self.assertEqual(sn.ayar("a", BUGUN, []), {"bekle_gun": 0, "carpan": 1.0, "neden": "", "sure": 0, "bitis": ""})

    def test_bekleyen_kayit_karar_sayilmaz(self):
        a = self.ayar([kayit(1, "a", "bekliyor", 3), kayit(2, "a", "bekliyor", 1)])
        self.assertEqual((a["bekle_gun"], a["carpan"]), (0, 1.0))

    def test_baska_kisinin_kaydi_etkilemez(self):
        a = self.ayar([kayit(1, "b", "atlandi", 1), kayit(2, "b", "atlandi", 0)], "a")
        self.assertEqual((a["bekle_gun"], a["carpan"]), (0, 1.0))

    def test_son_iki_atlandi_28_gun(self):
        a = self.ayar([kayit(1, "a", "atlandi", 10), kayit(2, "a", "atlandi", 2)])
        self.assertEqual((a["sure"], a["bekle_gun"], a["bitis"]), (28, 26, "2026-11-14"))   # son kapanıştan (17 Ekim) itibaren
        self.assertIn("26 gün", a["neden"])
        self.assertEqual(a["carpan"], 1.0)

    def test_28_gun_dolunca_bekleme_biter(self):
        kayitlar = [kayit(1, "a", "atlandi", 40), kayit(2, "a", "atlandi", 28)]
        a = self.ayar(kayitlar)
        self.assertEqual((a["bekle_gun"], a["neden"]), (0, ""))
        self.assertEqual(sn.ayar("a", BUGUN - timedelta(days=1), kayitlar)["bekle_gun"], 1)   # bir gün önce hâlâ bekliyordu

    def test_tek_atlandi_beklemez(self):
        self.assertEqual(self.ayar([kayit(1, "a", "yaptim", 20), kayit(2, "a", "atlandi", 1)])["bekle_gun"], 0)

    def test_son_uc_karisik_21_gun(self):
        a = self.ayar([kayit(1, "a", "atlandi", 9), kayit(2, "a", "ertelendi", 6), kayit(3, "a", "atlandi", 3)])
        self.assertEqual((a["sure"], a["bekle_gun"]), (21, 18))
        a = self.ayar([kayit(1, "a", "ertelendi", 9), kayit(2, "a", "atlandi", 6), kayit(3, "a", "ertelendi", 3)])
        self.assertEqual((a["sure"], a["bekle_gun"]), (21, 18))

    def test_atlandi_atlandi_en_uzun_kural_kazanir(self):
        a = self.ayar([kayit(1, "a", "ertelendi", 9), kayit(2, "a", "atlandi", 6), kayit(3, "a", "atlandi", 3)])
        self.assertEqual(a["sure"], 28)

    def test_uc_kayittan_biri_baska_sonuc_ise_21_gun_yok(self):
        a = self.ayar([kayit(1, "a", "atlandi", 9), kayit(2, "a", "yaptim", 6), kayit(3, "a", "ertelendi", 3)])
        self.assertEqual((a["sure"], a["bekle_gun"]), (7, 4))   # yalnız "son karar ertelendi" kuralı

    def test_tek_ertelendi_7_gun_kapanistan(self):
        a = self.ayar([kayit(1, "a", "ertelendi", 5, kapanis_gun_once=2)])
        self.assertEqual((a["sure"], a["bekle_gun"], a["bitis"]), (7, 5, "2026-10-24"))
        self.assertIn("5 gün", a["neden"])
        self.assertEqual(self.ayar([kayit(1, "a", "ertelendi", 12)])["bekle_gun"], 0)

    def test_ertelendiden_sonra_yaptim_beklemeyi_kaldirir(self):
        self.assertEqual(self.ayar([kayit(1, "a", "ertelendi", 3), kayit(2, "a", "yaptim", 1)])["bekle_gun"], 0)

    def test_son_iki_ise_yaramadi_carpan_yarim(self):
        a = self.ayar([kayit(1, "a", "ise_yaramadi", 30), kayit(2, "a", "ise_yaramadi", 10)])
        self.assertEqual(a["carpan"], 0.5)
        self.assertEqual(a["bekle_gun"], 0)
        self.assertEqual(a["neden"], "Son iki deneme işe yaramadı; farklı bir yol dene (ortak tanıdık, yüz yüze).")

    def test_ise_yaramadi_arasina_yaptim_ya_da_atlandi_girse_de_sonuclu_say(self):
        a = self.ayar([kayit(1, "a", "ise_yaramadi", 40), kayit(2, "a", "yaptim", 30), kayit(3, "a", "ise_yaramadi", 20)])
        self.assertEqual(a["carpan"], 0.5)

    def test_tek_ise_yaramadi_ya_da_arada_ise_yaradi_olursa_carpan_yok(self):
        self.assertEqual(self.ayar([kayit(1, "a", "ise_yaramadi", 10)])["carpan"], 1.0)
        self.assertEqual(self.ayar([kayit(1, "a", "ise_yaramadi", 40), kayit(2, "a", "ise_yaradi", 30), kayit(3, "a", "ise_yaramadi", 20)])["carpan"], 1.0)

    def test_son_ise_yaradi_carpan_1_15(self):
        a = self.ayar([kayit(1, "a", "ise_yaramadi", 40), kayit(2, "a", "ise_yaradi", 5)])
        self.assertEqual((a["carpan"], a["bekle_gun"]), (1.15, 0))
        self.assertEqual(a["neden"], "Son deneme işe yaradı; ritmi koru.")

    def test_ise_yaradi_sonrasi_atlandi_carpani_kaldirir(self):
        self.assertEqual(self.ayar([kayit(1, "a", "ise_yaradi", 9), kayit(2, "a", "atlandi", 2)])["carpan"], 1.0)

    def test_eski_sonuclar_carpani_etkilemez(self):
        self.assertEqual(self.ayar([kayit(1, "a", "ise_yaramadi", 300), kayit(2, "a", "ise_yaramadi", 200)])["carpan"], 1.0)
        self.assertEqual(self.ayar([kayit(1, "a", "ise_yaradi", 200)])["carpan"], 1.0)

    def test_bekleme_ve_carpan_birlikte_nedenleri_birlestirir(self):
        a = self.ayar([kayit(1, "a", "ise_yaramadi", 20), kayit(2, "a", "ise_yaramadi", 10), kayit(3, "a", "atlandi", 4), kayit(4, "a", "atlandi", 1)])
        self.assertEqual((a["bekle_gun"], a["carpan"]), (27, 0.5))
        self.assertIn("dinlendiriyorum", a["neden"])
        self.assertIn("farklı bir yol dene", a["neden"])

    def test_sira_kapanisa_gore(self):
        # no sırası ile kapanış sırası farklı: en son KARAR geçerli
        kayitlar = [kayit(1, "a", "ise_yaradi", 2), kayit(2, "a", "atlandi", 20)]
        self.assertEqual(self.ayar(kayitlar)["carpan"], 1.15)

    def test_dosyadan_okur(self):
        with tempfile.TemporaryDirectory() as t:
            eski = c.VERI
            c.veri_klasoru(os.path.join(t, "veri"))
            try:
                n1 = sn.kaydet("ozet", "a", "Bir", BUGUN - timedelta(days=14))
                n2 = sn.kaydet("ozet", "a", "İki", BUGUN - timedelta(days=7))
                sn.isaretle(n1, "atlandi", bugun=BUGUN - timedelta(days=13))
                sn.isaretle(n2, "atlandi", bugun=BUGUN - timedelta(days=6))
                self.assertEqual(sn.ayar("a", BUGUN)["bekle_gun"], 22)
            finally:
                c.veri_klasoru(eski)


class SorguTest(unittest.TestCase):
    def test_kisi_gecmisi_en_yeni_once(self):
        k = [kayit(1, "a", "yaptim", 20), kayit(2, "b", "yaptim", 5), kayit(3, "a", "bekliyor", 2), kayit(4, "a", "atlandi", 2)]
        self.assertEqual([r["no"] for r in sn.kisi_gecmisi("a", k)], [4, 3, 1])
        self.assertEqual(sn.kisi_gecmisi("yok", k), [])

    def test_bekleyenler_bekliyor_3_gun_yaptim_5_gun(self):
        k = [kayit(1, "a", "bekliyor", 2),                       # henüz erken
             kayit(2, "a", "bekliyor", 3),                       # sorulur
             kayit(3, "b", "yaptim", 9, kapanis_gun_once=4),     # kapanıştan 4 gün: erken
             kayit(4, "b", "yaptim", 9, kapanis_gun_once=5),     # sorulur
             kayit(5, "c", "ise_yaradi", 20),                    # karar verilmiş
             kayit(6, "c", "atlandi", 20),
             kayit(7, "c", "bekliyor", 60),                      # çok eski: artık sorulmaz
             kayit(8, "c", "yaptim", 80, kapanis_gun_once=60)]
        b = sn.bekleyenler(BUGUN, k)
        self.assertEqual([(r["no"], r["asama"], r["gun"]) for r in b], [(4, "yaptim", 5), (2, "bekliyor", 3)])   # en eski önce

    def test_bekleyenler_en_cok_10_en_eskiler(self):
        k = [kayit(i, "a", "bekliyor", 3 + i) for i in range(1, 16)]
        b = sn.bekleyenler(BUGUN, k)
        self.assertEqual(len(b), 10)
        self.assertEqual([r["no"] for r in b], list(range(15, 5, -1)))

    def test_bekleyenler_girdiyi_degistirmez(self):
        k = [kayit(1, "a", "bekliyor", 5)]
        sn.bekleyenler(BUGUN, k)
        self.assertNotIn("gun", k[0])


class IstatistikTest(unittest.TestCase):
    def test_bos(self):
        s = sn.istatistik(BUGUN, [])
        self.assertEqual(s, {"son_8_hafta": {"toplam": 0, "yapilan": 0, "ise_yarayan": 0, "oran": None}, "kaynaklara_gore": {}, "red_nedenleri": {}})

    def test_son_8_hafta_penceresi(self):
        k = [kayit(1, "a", "ise_yaradi", 0), kayit(2, "a", "yaptim", 55), kayit(3, "a", "ise_yaradi", 56), kayit(4, "a", "ise_yaradi", 200),
             kayit(5, "a", "atlandi", 10), kayit(6, "a", "ise_yaramadi", 3), kayit(7, "a", "bekliyor", 1), kayit(8, "a", "ertelendi", 2)]
        s = sn.istatistik(BUGUN, k)["son_8_hafta"]
        # pencerede: 1, 2, 5, 6, 7, 8
        self.assertEqual(s, {"toplam": 6, "yapilan": 3, "ise_yarayan": 1, "oran": 0.5})

    def test_oran_sonuclanan_uzerinden(self):
        k = [kayit(i, "a", "ise_yaradi", i) for i in range(1, 4)] + [kayit(10, "a", "ise_yaramadi", 1), kayit(11, "a", "yaptim", 1), kayit(12, "a", "atlandi", 1)]
        s = sn.istatistik(BUGUN, k)["son_8_hafta"]
        self.assertEqual((s["ise_yarayan"], s["oran"]), (3, 0.75))   # 3 / (3 + 1); yaptim ve atlandi oranda yok

    def test_oran_yoksa_none(self):
        self.assertIsNone(sn.istatistik(BUGUN, [kayit(1, "a", "yaptim", 1)])["son_8_hafta"]["oran"])

    def test_kaynaklara_gore(self):
        k = [kayit(1, "a", "ise_yaradi", 1, kaynak="ozet"), kayit(2, "a", "atlandi", 1, kaynak="ozet"), kayit(3, "a", "yaptim", 1, kaynak="yol")]
        g = sn.istatistik(BUGUN, k)["kaynaklara_gore"]
        self.assertEqual(set(g), {"ozet", "yol"})
        self.assertEqual(g["ozet"], {"toplam": 2, "yapilan": 1, "ise_yarayan": 1, "oran": 1.0})
        self.assertEqual(g["yol"], {"toplam": 1, "yapilan": 1, "ise_yarayan": 0, "oran": None})

    def test_strateji_sonuclari_katilir(self):
        k = [kayit(1, "a", "ise_yaradi", 1)]
        h = [{"sonuc": "ise_yaradi", "sonuc_tarih": "2026-10-15"}, {"sonuc": "yapmadim", "sonuc_tarih": "2026-10-15"},
             {"sonuc": "yaptim", "sonuc_tarih": "2026-10-16"}, {"sonuc": "gecersiz", "sonuc_tarih": "2026-10-16"},
             {"sonuc": "ise_yaramadi", "sonuc_tarih": "2026-01-01"},      # pencere dışı
             {"sonuc": "", "sonuc_tarih": ""}, {"baslik": "sonuçsuz"}, {"sonuc": "yaptim", "sonuc_tarih": "bozuk"}]
        s = sn.istatistik(BUGUN, k, h)
        self.assertEqual(s["kaynaklara_gore"]["strateji"], {"toplam": 3, "yapilan": 2, "ise_yarayan": 1, "oran": 1.0})
        self.assertEqual(s["son_8_hafta"], {"toplam": 4, "yapilan": 3, "ise_yarayan": 2, "oran": 1.0})
        self.assertEqual(sn.istatistik(BUGUN, k)["son_8_hafta"]["toplam"], 1)   # strateji verilmezse katılmaz


if __name__ == "__main__":
    unittest.main()


class UymuyorTest(SonucTabanTest):
    """"Uymuyor": öneriyi gerekçesiyle reddetme (16 Ekim 2026, Umut'un isteği)."""
    def setUp(self):
        super().setUp()
        self.kisi("naz-kurgu", "Naz Kurgu", yakinlik="1")
        self.no = sn.kaydet("ozet", "naz-kurgu", "Kısa bir selam yaz", BUGUN)

    def test_neden_zorunlu_ve_not_bicimi(self):
        for kotu in ("", "bilinmez", None):
            with self.assertRaises(ValueError):
                sn.isaretle(self.no, "reddedildi", bugun=BUGUN, neden=kotu)
        sn.isaretle(self.no, "reddedildi", "  grup   sohbetinden  ", bugun=BUGUN, neden="yakin_degil")
        r = sn.oku()[0]
        self.assertEqual((r["sonuc"], r["not"], r["kapanis"]), ("reddedildi", "[yakin_degil] grup sohbetinden", BUGUN.isoformat()))
        self.assertEqual(sn.red_nedeni(r), "yakin_degil")
        self.assertIn("| reddedildi |", self.metin())

    def test_temas_eklenmez(self):
        r = sn.isaretle(self.no, "reddedildi", temas=True, bugun=BUGUN, neden="gerek_yok")
        self.assertFalse(r["temas_eklendi"])
        self.assertNotIn("Kut önerisi", self.kisi_oku("naz-kurgu")["govde"])

    def test_bekleme_gerekceye_gore(self):
        for neden, gun in (("yakin_degil", 365), ("istemiyorum", 365), ("gerek_yok", 60), ("zamani_degil", 30), ("yanlis", 90), ("diger", 45)):
            k = [kayit(1, "a", "reddedildi", 10, **{"not": f"[{neden}] x"})]
            a = sn.ayar("a", BUGUN, k)
            self.assertEqual((a["sure"], a["bekle_gun"]), (gun, gun - 10), neden)
            self.assertIn(sn.RED_NEDENLERI[neden][0], a["neden"])
        self.assertEqual(sn.ayar("a", BUGUN, [kayit(1, "a", "reddedildi", 31, **{"not": "[zamani_degil]"})])["bekle_gun"], 0)   # süre doldu

    def test_sonra_baska_sonuca_cevrilince_gerekce_kalkar(self):
        sn.isaretle(self.no, "reddedildi", "yanlış kişi", bugun=BUGUN, neden="yanlis")
        sn.isaretle(self.no, "yaptim", bugun=BUGUN)
        r = sn.oku()[0]
        self.assertEqual((r["sonuc"], r["not"], sn.red_nedeni(r)), ("yaptim", "yanlış kişi", ""))
        self.assertEqual(sn.ayar("naz-kurgu", BUGUN)["bekle_gun"], 0)

    def test_istatistik_gerekceleri_sayar(self):
        k = [kayit(1, "a", "reddedildi", 3, **{"not": "[yakin_degil]"}), kayit(2, "b", "reddedildi", 5, **{"not": "[yakin_degil] grup"}),
             kayit(3, "c", "reddedildi", 4, **{"not": "[zamani_degil]"}), kayit(4, "d", "reddedildi", 90, **{"not": "[yanlis]"}), kayit(5, "e", "yaptim", 1)]
        self.assertEqual(sn.istatistik(BUGUN, k)["red_nedenleri"], {"yakin_degil": 2, "zamani_degil": 1})

    def test_bu_hafta_ihmal_satiri_duser_sonraki_adim_kalir(self):
        self.kisi("can-ornek", "Can Örnek", yakinlik="1", son_temas="2026-01-01")
        self.kisi("lale-deneme", "Lale Deneme", yakinlik="1", son_temas="2026-01-01", sonraki_adim="Sunucu kurulumunu sor",
                  sonraki_tarih=date.today().isoformat())
        for kid in ("can-ornek", "lale-deneme"):
            no = sn.kaydet("ozet", kid, "Kısa bir selam yaz")
            sn.isaretle(no, "reddedildi", neden="yakin_degil")
        ids = {x["id"] for x in c.veri_hazirla(foto_gom=False)["bu_hafta"]}
        self.assertNotIn("can-ornek", ids)       # Kut'un ihmal önerisi dinlenir
        self.assertIn("lale-deneme", ids)         # kullanıcının kendi sonraki adımı kalır

