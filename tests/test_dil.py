"""Arayüz dili: Türkçe varsayılan ve birebir aynı; İngilizce sözlük katmanı (kut/dil_en.json, ag_dil.py, ag_sablon.html "Dil" bölümü).
Sözlük bütünlüğü, çeviri kuralları (Python ve tarayıcıdaki kopyası aynı sonucu verir), sayfaya gömme, /api/dil kapıları, model cevap dili, MCP çıktısı."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

KOK_DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOK = os.path.join(KOK_DEPO, "kut")
sys.path.insert(0, KOK)
import ag_dil  # noqa: E402
import ag_cekirdek as c  # noqa: E402

SABLON = os.path.join(KOK, "ag_sablon.html")
TR_HARF = re.compile(r"[çğışöüÇĞİŞÖÜ]")
# İngilizce değerde kalabilen Türkçe: kurgusal ad ve dosya/klasör adları (veri biçimi çevrilmez)
IZINLI = ("Dilara Tuna Örnek", "Ayşe", "gelen/whatsapp", "Türkçe")


def sablon():
    with open(SABLON, encoding="utf-8") as f:
        return f.read()


class SozlukTest(unittest.TestCase):
    def setUp(self):
        with open(ag_dil.SOZLUK_YOLU, encoding="utf-8") as f:
            self.ham = json.load(f)
        self.s = ag_dil.sozluk()

    def test_gecerli_ve_dolu(self):
        self.assertGreater(len(self.s), 1000)
        for k, v in self.s.items():
            self.assertTrue(k.strip() and v.strip(), k)
            self.assertEqual(k, k.strip(), k)
            self.assertEqual(re.sub(r"\s+", " ", k), k, k)   # anahtar arayüzün sadeleştirdiği biçimde

    def test_yer_tutucular_ve_etiketler_eslesir(self):
        for k, v in self.s.items():
            self.assertEqual(sorted(re.findall(r"\{\d+\}", k)), sorted(re.findall(r"\{\d+\}", v)), k)
            self.assertEqual(sorted(re.findall(r"<(/?\w+)", k)), sorted(re.findall(r"<(/?\w+)", v)), k)

    def test_ingilizce_degerde_turkce_harf_yok(self):
        for k, v in self.s.items():
            for i in IZINLI:
                v = v.replace(i, "")
            self.assertIsNone(TR_HARF.search(v), k)

    def test_veri_bicimi_anahtarlari_sozlukte_yok(self):
        # Markdown bölüm başlıkları ve alan adları çevrilmez (dosyalar her iki dilde aynı kalır)
        for k in ("## Temas", "## Sözler", "## Senin beyanların", "yakinlik", "tur", "ad"):
            self.assertNotIn(k, self.s)


class CeviriKuralTest(unittest.TestCase):
    def test_turkcede_hicbir_sey_degismez(self):
        for x in ("Kaydet", "3 kişi", "Güzel bir gün", "{0} kişi", "", None):
            self.assertEqual(ag_dil.cevir(x, "tr"), x)
        self.assertEqual(ag_dil.t("Son {0} günde kayıtlı temas yok.", 7, dil="tr"), "Son 7 günde kayıtlı temas yok.")
        self.assertEqual(ag_dil.satirlar("- Kurum: X\n## Açık sözler", "tr"), "- Kurum: X\n## Açık sözler")

    def test_birebir_kalip_ve_bosluk(self):
        self.assertEqual(ag_dil.cevir("Kaydet", "en"), "Save")
        self.assertEqual(ag_dil.cevir("  Kaydet\n", "en"), "  Save\n")
        self.assertEqual(ag_dil.cevir("3 kişi", "en"), "3 people")
        self.assertEqual(ag_dil.t("Son {0} günde kayıtlı temas yok.", 7, dil="en"), "No recorded interactions in the last 7 days.")

    def test_kisa_kalip_kullanici_metnini_cevirmez(self):
        # "{0} gün" yalnız sayı yakalar: kullanıcının notu ("Güzel bir gün") çevrilmez
        self.assertEqual(ag_dil.cevir("Güzel bir gün", "en"), "Güzel bir gün")
        self.assertEqual(ag_dil.cevir("12 gün", "en"), "12 days")
        self.assertEqual(ag_dil.cevir("Deniz Demo", "en"), "Deniz Demo")

    def test_birlesik_ve_cok_cumleli(self):
        self.assertEqual(ag_dil.cevir("puan 1.7 · 5 eşleşme", "en"), "score 1.7 · 5 matches")
        self.assertEqual(ag_dil.cevir("Birlikte çalışıyor · Hackathon ekibi", "en"), "Work together · Hackathon ekibi")
        self.assertEqual(ag_dil.cevir("0–2: Ortak alan yok", "en"), "0–2: No shared field")
        self.assertEqual(
            ag_dil.cevir("Selin Hoca (Kuzeyova Üniversitesi) ile yakınlığınız 2; son temas 17 gün önce. Sonraki adımın: Makaleyi göndermek (2 gün kaldı).", "en"),
            "Your closeness with Selin Hoca (Kuzeyova Üniversitesi): 2; last contact 17 days ago. Your next step: Makaleyi göndermek (2 days left).")
        self.assertEqual(
            ag_dil.cevir("Mert Kurgusal – Ayla Kurgu arasında: rakip. Birini diğerine referans gösterme, ikisini aynı işe birlikte çağırmadan önce düşün.", "en"),
            "Between Mert Kurgusal and Ayla Kurgu: rival. Don't cite one as a reference to the other; think twice before inviting both to the same thing.")

    def test_markdown_satirlari(self):
        self.assertEqual(ag_dil.satirlar("# Selin Hoca\n- Kurum: Kuzeyova\n## Açık sözler", "en"), "# Selin Hoca\n- Organization: Kuzeyova\n## Open promises")

    def test_cerez(self):
        self.assertEqual(ag_dil.cerezden("a=1; kut_dil=en; b=2"), "en")
        self.assertIsNone(ag_dil.cerezden("kut_dil=de"))
        self.assertIsNone(ag_dil.cerezden(None))


class SayfaTest(unittest.TestCase):
    def test_turkce_sayfa_sozluk_tasimaz(self):
        h = c.sayfa({"turler": {}}, None, None)
        self.assertIn('<html lang="tr"', h)
        self.assertIn("const DIL = null;", h)
        self.assertNotIn("Kaydet\": \"Save", h)
        self.assertEqual(c.sayfa({"turler": {}}, None, None, dil="tr"), h)

    def test_ingilizce_sayfa_sozlugu_gomer(self):
        h = c.sayfa({"turler": {}}, None, None, dil="en")
        self.assertIn('<html lang="en"', h)
        m = re.search(r"const DIL = (\{.*?\});\n", h)
        self.assertTrue(m)
        d = json.loads(m.group(1).replace("<\\/", "</"))
        self.assertEqual(d["dil"], "en")
        self.assertEqual(d["sozluk"]["Kaydet"], "Save")
        self.assertNotIn("</script", m.group(1))   # gömülü sözlük betik etiketini kapatamaz

    def test_turkce_yolda_kod_degismez(self):
        h = sablon()
        self.assertEqual(h.count('"tr-TR"'), 1)                     # tarih yereli yalnız YEREL'de
        self.assertIn('const YEREL = DIL ? "en-GB" : "tr-TR";', h)
        self.assertIn("if (CEVIRI) {", h)                             # gözlemci yalnız İngilizcede kurulur
        self.assertIn("if (!CEVIRI || s == null) return s;", h)       # Türkçede cevir kimliktir
        # kullanıcı verisi çipleri çevrilmez
        self.assertRegex(h, r'id="alanChips" data-cevirme')
        self.assertRegex(h, r'id="neredenChips" data-cevirme')

    def test_dil_secimi_arayuzde(self):
        h = sablon()
        self.assertIn("function dilHtml()", h)
        self.assertIn('api("/api/dil", { dil: d })', h)
        self.assertIn("kut_dil=${d}; path=/; max-age=315360000; SameSite=Strict", h)
        self.assertIn('id="kilit-dil"', h)
        # ilk açılış: PIN yokken ve dil seçilmemişken önce iki bayraklı dil seçimi; seçim çerezde, kilit açılınca ayarlar.json'a eşitlenir
        self.assertIn('id="kilit-dilsec"', h)
        self.assertIn('data-dil="tr"', h)
        self.assertIn('data-dil="en"', h)
        self.assertIn("const dilSor = kur && !cerezDil();", h)
        self.assertIn('cerezDil() !== MOD.dil_ayar) api("/api/dil"', h)

    def test_tarayici_kurallari_python_ile_ayni(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node yok")
        h = sablon()
        bas = h.index("const CUMLE_SINIRI")
        son = h.index("const tx = ")
        ornekler = ["Kaydet", "  Kaydet ", "3 kişi", "Güzel bir gün", "puan 1.7 · 5 eşleşme", "0–2: Ortak alan yok",
                    "Birlikte çalışıyor · Hackathon ekibi", "Deniz Demo", "Jüri kriterlerini sormak (2 gün gecikti)",
                    "Selin Hoca (Kuzeyova Üniversitesi) ile yakınlığınız 2; son temas 17 gün önce. Sonraki adımın: Makaleyi göndermek (2 gün kaldı).",
                    "Mert Kurgusal – Ayla Kurgu arasında: rakip. Birini diğerine referans gösterme, ikisini aynı işe birlikte çağırmadan önce düşün.",
                    "<b>Zaten tanışıyorsun.</b> Aracı gerekmez · yakınlık: Görüştük · son temas 3 gün önce.",
                    "Kanıt: unvan\nSayılmaz: hobi\n0–2: Ortak alan yok"]
        kod = ("const DIL = " + json.dumps({"dil": "en", "sozluk": ag_dil.sozluk()}, ensure_ascii=False) + ";\n" + h[bas:son] +
               "\nconsole.log(JSON.stringify(" + json.dumps(ornekler, ensure_ascii=False) + ".map(x => cevir(x))));")
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "dil.js")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(kod)
            r = subprocess.run([node, yol], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr[:500])
        js = json.loads(r.stdout)
        py = [ag_dil.cevir(x, "en") for x in ornekler]
        self.assertEqual(js, py)
        self.assertEqual(js[3], "Güzel bir gün")
        self.assertEqual(js[7], "Deniz Demo")


class ModelDiliTest(unittest.TestCase):
    def test_turkcede_istem_aynen_kalir(self):
        import ag_model
        with mock.patch.object(ag_dil, "etkin", return_value="tr"):
            self.assertEqual(ag_model.dil_yonergesi("sistem"), "sistem")
            self.assertEqual(ag_model.dil_yonergesi(""), "")

    def test_ingilizcede_yonerge_eklenir(self):
        import ag_model
        with mock.patch.object(ag_dil, "etkin", return_value="en"):
            self.assertEqual(ag_model.dil_yonergesi("sistem"), "sistem\n\n" + ag_model.DIL_YONERGESI)
            self.assertEqual(ag_model.dil_yonergesi(""), ag_model.DIL_YONERGESI)
        self.assertIn("## Temas", ag_model.DIL_YONERGESI)   # veri biçimi korunur


class McpDilTest(unittest.TestCase):
    def test_arac_adlari_ayni_aciklamalar_ingilizce(self):
        import ag_mcp
        self.assertEqual([a["name"] for a in ag_mcp.ARACLAR], ["kisi_ara", "kisi_karti", "bu_hafta", "son_gorusmeler", "brifing"])
        for a in ag_mcp.ARACLAR:
            self.assertIsNone(TR_HARF.search(a["description"]), a["name"])

    def test_satirlar_mcp_metni(self):
        with mock.patch.object(ag_dil, "etkin", return_value="en"):
            self.assertEqual(ag_dil.satirlar("Eşleşen kişi yok."), "No matching people.")


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DilApiTest(unittest.TestCase):
    """Ayrı süreçte sunucu, geçici LOCALAPPDATA: /api/dil kapıları, kalıcılık, sayfa dili (ayar ve çerez)."""
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.TemporaryDirectory()
        la = os.path.join(cls.d.name, "la")
        cls.ayar = os.path.join(la, "agim", "ayarlar.json")
        cls.port = bos_port()
        env = {**os.environ, "LOCALAPPDATA": la, "AGIM_VERI": os.path.join(cls.d.name, "veri"), "PYTHONIOENCODING": "utf-8"}
        kod = ("import sys;sys.path.insert(0,%r);import ag_sunucu as s;from http.server import ThreadingHTTPServer;s.PORT=%d;"
               "ThreadingHTTPServer(('127.0.0.1',%d),s.Isleyici).serve_forever()") % (KOK, cls.port, cls.port)
        cls.p = subprocess.Popen([sys.executable, "-c", kod], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()
        cls.p.wait()
        cls.d.cleanup()

    def istek(self, yontem, yol, govde=None, basliklar=None):
        h = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        b = json.dumps(govde).encode() if govde is not None else None
        h.request(yontem, yol, b, {"Content-Type": "application/json", **(basliklar or {})})
        y = h.getresponse()
        r = (y.status, y.getheader("Set-Cookie"), y.read())
        h.close()
        return r

    def ayarlar(self):
        with open(self.ayar, encoding="utf-8") as f:
            return json.load(f)

    def test_kapilar_kalicilik_ve_sayfa_dili(self):
        yol = "/api/dil"
        self.assertEqual(self.istek("POST", yol, {"dil": "en"})[0], 403)                   # kilitli ve anahtarsız
        kilitli = self.istek("GET", "/", None, {"Cookie": "kut_dil=en"})[2].decode("utf-8")
        self.assertIn('<html lang="en"', kilitli)                                           # kilit ekranı çerezle İngilizce, diske yazmadan
        self.assertNotIn("dil", self.ayarlar() if os.path.exists(self.ayar) else {})
        kod, cerez, _ = self.istek("POST", "/api/kilit/kur", {"pin": "4321", "pin2": "4321"})
        self.assertEqual(kod, 200)
        cerez = {"Cookie": cerez.split(";")[0]}
        sayfa = self.istek("GET", "/", None, cerez)[2].decode("utf-8")
        self.assertIn('<html lang="tr"', sayfa)                                             # varsayılan Türkçe
        self.assertIn("const DIL = null;", sayfa)
        self.assertRegex(sayfa, r'"dil_ayar":\s*null')
        anahtar = re.search(r'"anahtar":\s*"([^"]+)"', sayfa).group(1)
        a = {**cerez, "X-Ag-Anahtar": anahtar}
        self.assertEqual(self.istek("POST", yol, {"dil": "en"}, cerez)[0], 403)            # anahtarsız
        self.assertEqual(self.istek("POST", yol, {"dil": "en"}, {**a, "Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.istek("POST", yol, {"dil": "de"}, a)[0], 400)
        self.assertEqual(self.istek("POST", yol, {}, a)[0], 400)
        self.assertNotIn("dil", self.ayarlar())
        kod, _, v = self.istek("POST", yol, {"dil": "en"}, {**a, "Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(kod, 200)
        self.assertEqual(json.loads(v)["dil"], "en")
        self.assertEqual(self.ayarlar()["dil"], "en")
        self.assertIn("kilit", self.ayarlar())                                              # diğer ayarlar korunur
        sayfa = self.istek("GET", "/", None, cerez)[2].decode("utf-8")
        self.assertIn('<html lang="en"', sayfa)
        self.assertIn('"Kaydet": "Save"', sayfa)
        tr = self.istek("GET", "/", None, {"Cookie": cerez["Cookie"] + "; kut_dil=tr"})[2].decode("utf-8")
        self.assertIn('<html lang="tr"', tr)                                                # tarayıcının seçimi önce gelir
        self.assertEqual(self.istek("POST", yol, {"dil": "tr"}, a)[0], 200)
        self.assertEqual(self.ayarlar()["dil"], "tr")


if __name__ == "__main__":
    unittest.main()
