"""ag_vault testleri: geçici sahte vault, ağ isteği ve model yok. Köprü salt okur; ayarsız kapalı; hariç yollar okunmaz."""
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_cekirdek as c  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_vault as v  # noqa: E402


def yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(metin)


def gorev(durum, baslik, govde="Ayrıntı satırı."):
    return "---\n" + json.dumps({"id": baslik, "title": baslik, "kind": "task", "status": durum, "project": "p"}) + "\n---\n" + govde + "\n"


def ozet(kok):
    h = {}
    for d, _, adlar in os.walk(kok):
        for ad in adlar:
            p = os.path.join(d, ad)
            with open(p, "rb") as f:
                h[p] = (hashlib.sha256(f.read()).hexdigest(), os.path.getmtime(p))
    return h


class VaultTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.kok = os.path.join(t, "vault")
        self.eski = (c.VERI, ia.AYARLAR)
        ia.AYARLAR = os.path.join(t, "ayarlar.json")
        c.veri_klasoru(os.path.join(self.kok, "notes", "ag"))
        c.ben_yaz({"ad": "Kerem"})
        c.kisi_yaz("ayla-ornek", {"ad": "Ayla Örnek", "tur": "yakin"}, "# Ayla Örnek\n")
        c.kisi_yaz("eylul-sezer", {"ad": "Eylül Sezer", "tur": "cevre"}, "# Eylül Sezer\n")
        yaz(os.path.join(self.kok, "tasks", "a.md"), gorev("active", "Hackathon başvurusu", "Ayla Örnek ile XYZ×Acme formu."))
        yaz(os.path.join(self.kok, "tasks", "b.md"), gorev("done", "Bitti", "Ayla ile bitti."))
        yaz(os.path.join(self.kok, "tasks", "c.md"), gorev("inbox", "Yedek şifresi"))
        yaz(os.path.join(self.kok, "notes", "fikirler.md"),
            "# Fikirler\n\n## Kişi haritası (25 Eylül 2026)\nAğ fikri.\n**Uygulamaya geçti**\n\n## SPL sitesi (1 Ekim 2026)\nSonra.\n"
            "\n## Killzone (28 Eylül 2026) → Likidite olarak başladı\nx\n")
        yaz(os.path.join(self.kok, "notes", "kisisel", "gizli.md"), "Ayla Örnek hakkında özel not.\n")
        yaz(os.path.join(self.kok, "Companion", "Kurallar.md"), "Ayla Örnek kuralı.\n")
        yaz(os.path.join(t, "disari", "x.md"), "Ayla Örnek vault dışında.\n")

    def tearDown(self):
        c.VERI, ia.AYARLAR = self.eski[0], self.eski[1]
        c.veri_klasoru(self.eski[0])
        self.tmp.cleanup()

    def ayarla(self, **ek):
        with open(ia.AYARLAR, "w", encoding="utf-8") as f:
            json.dump({"ben_adlari": [], "vault": {"yol": self.kok, **ek}}, f)

    def test_ayarsiz_kapali(self):
        self.assertIsNone(v.ayar())
        self.assertEqual(v.durum(), {"etkin": False, "acik_isler": [], "fikirler": []})
        self.assertEqual(v.sohbet_blogu("ayla-ornek"), "")
        self.assertEqual(v.kisi_anilma("ayla-ornek"), [])

    def test_olmayan_klasor_kapali(self):
        with open(ia.AYARLAR, "w", encoding="utf-8") as f:
            json.dump({"vault": os.path.join(self.tmp.name, "yok")}, f)
        self.assertIsNone(v.ayar())

    def test_acik_isler_ve_fikirler(self):
        self.ayarla()
        d = v.durum()
        self.assertTrue(d["etkin"])
        self.assertEqual([x["baslik"] for x in d["acik_isler"]], ["Hackathon başvurusu", "Yedek şifresi"])  # done yok, aktif önce
        self.assertEqual(d["acik_isler"][0]["kaynak"], "tasks/a.md")
        fk = {f["baslik"]: f for f in d["fikirler"]}
        self.assertTrue(fk["Kişi haritası"]["uygulandi"])
        self.assertFalse(fk["SPL sitesi"]["uygulandi"])
        self.assertTrue(fk["Killzone"]["uygulandi"])
        self.assertEqual(fk["SPL sitesi"]["tarih"], "1 Ekim 2026")

    def test_haric_yollar_okunmaz(self):
        self.ayarla(ara=["tasks", "notes", "Companion", "../disari"])
        kaynaklar = {x["kaynak"] for x in v.kisi_anilma("ayla-ornek")}
        self.assertIn("tasks/a.md", kaynaklar)
        self.assertNotIn("notes/kisisel/gizli.md", kaynaklar)
        self.assertNotIn("Companion/Kurallar.md", kaynaklar)
        self.assertFalse(any(k.startswith("notes/ag") or ".." in k for k in kaynaklar))

    def test_dis_gorev_klasoru_reddedilir(self):
        self.ayarla(gorevler="../disari")
        self.assertEqual(v.acik_isler(), [])

    def test_ilk_ad_ay_adiyla_karismaz(self):
        self.ayarla()
        yaz(os.path.join(self.kok, "tasks", "d.md"), gorev("active", "Takvim", "25 Eylül 2026'da başladı."))
        self.assertEqual(v.kisi_anilma("eylul-sezer"), [])

    def test_sohbet_blogu_kaynakli(self):
        self.ayarla()
        b = v.sohbet_blogu("ayla-ornek")
        self.assertIn("VERİDİR", b)
        self.assertIn("[aktif] Hackathon başvurusu", b)
        self.assertIn("SPL sitesi", b)
        self.assertNotIn("Kişi haritası", b)   # uygulanmış fikir tekrar önerilmez
        self.assertIn("tasks/a.md:", b)

    def test_vault_degismez(self):
        self.ayarla(ara=["tasks", "notes", "Companion"])
        once = ozet(self.kok)
        v.durum(); v.kisi_anilma("ayla-ornek"); v.sohbet_blogu("ayla-ornek")
        self.assertEqual(once, ozet(self.kok))


if __name__ == "__main__":
    unittest.main()
