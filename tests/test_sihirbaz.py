"""İlk açılış sihirbazı, özellik turu (sahne ışığı), Pusula'nın öne çıkarılması ve Ayarlar penceresi.
Arayüz testleri şablon metnine bakar (tarayıcı gerekmez); API testleri ayrı süreçte, geçici LOCALAPPDATA ile çalışır."""
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

KOK_DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOK = os.path.join(KOK_DEPO, "kut")
SABLON = os.path.join(KOK, "ag_sablon.html")


def sablon():
    with open(SABLON, encoding="utf-8") as f:
        return f.read()


def islev_govdesi(h, ad):
    """`function ad(` ile başlayan işlevin gövdesi (süslü parantez dengesiyle; dizge içindeki parantezler sorun çıkarmayacak kadar dengeli)."""
    i = h.index("function " + ad + "(")
    j = h.index("{", i)
    d = 0
    for k in range(j, len(h)):
        d += h[k] == "{"
        d -= h[k] == "}"
        if d == 0:
            return h[j:k + 1]
    raise AssertionError(ad)


class TurAdimlariTest(unittest.TestCase):
    def adimlar(self):
        h = sablon()
        bas = h.index("const TUR_ADIMLARI = [")
        son = h.index("\n];", bas)
        return re.findall(r'^\s*\{ id: "(\w+)", hedef: "([^"]+)"', h[bas:son], re.M), h[bas:son]

    def test_adimlar_dizisi_ve_secicileri(self):
        adimlar, blok = self.adimlar()
        kimlikler = [a for a, _ in adimlar]
        # tanıtım sırası: harita, kart, doğrula, bu hafta, sor, pusula, içe aktar, kilit (ayar da araya girer)
        sira = ["harita", "kart", "dogrula", "hafta", "sor", "pusula", "ice", "kilit"]
        self.assertEqual([k for k in kimlikler if k in sira], sira)
        self.assertEqual(len(kimlikler), len(set(kimlikler)))
        # dizideki her `{ id:` satırı bir hedef seçici taşır (seçicisiz adım olmaz)
        self.assertEqual(blok.count("{ id:"), len(adimlar))
        self.assertEqual(blok.count("hedef:"), len(adimlar))
        h = sablon()
        for kim, secici in adimlar:
            ilk = secici.split()[0]
            self.assertTrue(ilk.startswith("#"), (kim, secici))
            self.assertIn(f'id="{ilk[1:]}"', h, f"{kim}: {secici} şablonda yok")
        self.assertIn('class="satir"', h)   # "#sohbet .satir"

    def test_hedef_yoksa_sessiz_atlama_ve_klavye_mantigi(self):
        h = sablon()
        self.assertIn("function turOlc(", h)
        self.assertIn("document.querySelector(a.hedef)", h)
        self.assertIn("if (!e || e.closest(\"[hidden]\")) return null;", h)   # hedef yok/gizli → adım listeden düşer
        self.assertIn("TUR_ADIMLARI.filter(", h)
        for tus in ("ArrowRight", "ArrowLeft", "Escape"):
            self.assertIn(f'k === "{tus}"', islev_govdesi(h, "turTus"))

    def test_sahne_isigi_katmani(self):
        h = sablon()
        self.assertIn("box-shadow:0 0 0 9999px", h)      # delik efekti
        self.assertIn("getBoundingClientRect()", islev_govdesi(h, "turOlc"))
        self.assertIn('addEventListener("resize", turKonumla)', h)   # pencere boyutu değişince yeniden hesap
        self.assertIn("prefers-reduced-motion:reduce", h)
        # marka dili: örtü ve kart keskin köşeli, cam/gölge/gradyan yok
        css = h[h.index("#tur{position:fixed"):h.index("@keyframes tur-belir")]
        self.assertNotIn("backdrop-filter", css)
        self.assertNotIn("gradient", css)
        self.assertNotIn("border-radius:", css.replace("border-radius:0", ""))

    def test_sablon_js_soz_dizimi(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node yok")
        h = sablon()
        js = re.search(r"<script>\n(.*)</script>", h, re.S).group(1)
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "sablon.js")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(js)
            r = subprocess.run([node, "--check", yol], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[:400])


class SihirbazArayuzTest(unittest.TestCase):
    def test_kurulum_adimlari(self):
        h = sablon()
        bas = h.index("const SIH_ADIMLARI = [")
        blok = h[bas:h.index("\n];", bas)]
        self.assertEqual(re.findall(r'\{ id: "(\w+)"', blok), ["hos", "profil", "yz", "ses", "kasa", "okul"])
        self.assertIn("goster: () => VAULT.etkin", blok)   # kasa yoksa adım atlanır
        # mevcut mantıkların çağrıldığı yerler
        self.assertIn('api("/api/saglayici")', h)
        self.assertIn("onclick = seskAc", h)
        self.assertIn("kasaKisiHtml()", islev_govdesi(h, "sihKasaCiz"))
        self.assertIn('api("/api/kaynaklar", { id: "okul"', h)
        self.assertIn('$("b-ice").click()', h)

    def test_tamamlanma_ayari_yazilir_ve_yeniden_acilir(self):
        h = sablon()
        self.assertIn('api("/api/sihirbaz", { durum: "bitti" })', h)
        self.assertIn("MOD.sihirbaz.bitti", h)
        self.assertIn('id="ay-sihirbaz"', h)           # Ayarlar → Kurulum ve tanıtım
        self.assertIn("Kurulum ve tanıtımı aç", h)

    def test_kullanici_metni_esc_ile_basilir(self):
        h = sablon()
        for ad in ("sihProfil", "sihOkul"):
            g = islev_govdesi(h, ad)
            self.assertIn("${esc(", g)
            self.assertNotIn("${BEN.", g)   # ham basım yok


class PusulaOneCikarTest(unittest.TestCase):
    def test_pusula_dugmesi_gizli_degil(self):
        h = sablon()
        d = re.search(r'<button[^>]*id="b-pusula"[^>]*>', h).group(0)
        self.assertNotIn("hidden", d)
        self.assertNotIn("hayalet", d)
        self.assertIn("◎ Pusula", h)
        self.assertNotIn('$("b-pusula").hidden', h)      # JS de gizli bırakmaz

    def test_sol_panelin_en_ustunde_pusula_karti(self):
        h = sablon()
        sol = h[h.index('<aside id="sol">'):]
        ilk = re.search(r'<details class="blok[^"]*" [^>]*id="([^"]+)"', sol).group(1)
        self.assertEqual(ilk, "pu-blok")
        self.assertNotRegex(sol[:sol.index("</aside>")], r'id="hd-blok"')
        blok = re.search(r'<details[^>]*id="pu-blok"[^>]*>', h).group(0)
        self.assertNotIn("hidden", blok)
        g = islev_govdesi(h, "pusulaKartCiz")
        for parca in ("İlk hedefini yaz", "Bu haftanın stratejisini çıkar", "ilk_adim", "kanit", "hamleler"):
            self.assertIn(parca, g)
        # strateji uzak modele gider: kart onay ister, mevcut uç ve kapılar kullanılır
        b = islev_govdesi(h, "stratejiBaslat")
        self.assertIn("confirm(", b)
        self.assertIn('"/api/strateji/baslat"', b)

    def test_pusula_penceresi_yalniz_hedef_kesif_strateji(self):
        h = sablon()
        pencere = h[h.index('id="o-pusula"'):h.index('id="o-ayarlar"')]
        self.assertNotIn('data-pu="kaynaklar"', pencere)
        for sekme in ("hamleler", "hedefler", "vekil", "etkinlik"):
            self.assertIn(f'data-pu="{sekme}"', pencere)
        self.assertNotIn("kaynaklar: kaynakHtml", h)
        self.assertNotIn("Pusula → Kaynaklar", h)

    def test_ayarlar_penceresi_kaynak_kartlarini_icerir(self):
        h = sablon()
        self.assertIn('id="o-ayarlar"', h)
        self.assertRegex(h, r'<button[^>]*id="b-ayar"[^>]*aria-label="Ayarlar"[^>]*><svg class="ik"')
        self.assertIn("kaynakHtml()", islev_govdesi(h, "ayarCiz"))
        kaynak = islev_govdesi(h, "kaynakHtml")
        for kart in ("guncHtml()", "sesKartHtml()", "kasaKisiHtml()", "Okul bağdaştırıcısı", "K.kaynaklar.map(kart)"):
            self.assertIn(kart, kaynak)
        bagla = islev_govdesi(h, "ayarBagla")
        for b in ("guncBagla(ic)", "sesBagla(ic)", "kasaBagla(ic", "#kay-okul", "data-kaynak"):
            self.assertIn(b, bagla)
        self.assertNotIn("guncBagla(ic)", islev_govdesi(h, "pusulaBagla"))   # Pusula artık kaynak bağlamaz

    def test_eski_ifade_hicbir_yerde_kalmadi(self):
        dosyalar = [os.path.join(KOK_DEPO, "AGENTS.md"), os.path.join(KOK_DEPO, "README.md"), SABLON]
        dosyalar += [os.path.join(KOK, a) for a in os.listdir(KOK) if a.endswith(".py")]
        for yol in dosyalar:
            with open(yol, encoding="utf-8") as f:
                self.assertNotIn("Pusula → Kaynaklar", f.read(), yol)
                f.seek(0)
                self.assertNotIn("Pusula → **Kaynaklar**", f.read(), yol)


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SihirbazApiTest(unittest.TestCase):
    """Ayrı süreçte sunucu, geçici LOCALAPPDATA: /api/sihirbaz kilit + anahtar + yerel Origin kapıları, kalıcılık, sayfaya yansıma."""
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
        veri = y.read()
        r = (y.status, y.getheader("Set-Cookie"), veri)
        h.close()
        return r

    def test_uc_kapilar_kalicilik_ve_sayfa(self):
        yol = "/api/sihirbaz"
        self.assertEqual(self.istek("POST", yol, {"durum": "bitti"})[0], 403)            # kilitli ve anahtarsız
        kod, cerez, _ = self.istek("POST", "/api/kilit/kur", {"pin": "4321", "pin2": "4321"})
        self.assertEqual(kod, 200)
        cerez = {"Cookie": cerez.split(";")[0]}
        sayfa = self.istek("GET", "/", None, cerez)[2].decode("utf-8")
        anahtar = re.search(r'"anahtar":\s*"([^"]+)"', sayfa).group(1)
        self.assertRegex(sayfa, r'"sihirbaz":\s*\{"bitti":\s*false\}')                     # PIN sonrası ilk açılış: sihirbaz bekliyor
        a = {**cerez, "X-Ag-Anahtar": anahtar}
        self.assertEqual(self.istek("POST", yol, {"durum": "bitti"}, cerez)[0], 403)      # oturum var, anahtar yok
        self.assertEqual(self.istek("POST", yol, {"durum": "bitti"}, {"X-Ag-Anahtar": anahtar})[0], 401)   # anahtar var, oturum yok
        self.assertEqual(self.istek("POST", yol, {"durum": "bitti"}, {**a, "Origin": "http://evil.example"})[0], 403)   # yabancı kaynak
        self.assertEqual(self.istek("GET", yol, None, a)[0], 404)                          # yazan uç yalnız POST
        self.assertEqual(self.istek("POST", yol, {"durum": "belki"}, a)[0], 400)
        self.assertEqual(self.istek("POST", yol, {}, a)[0], 400)
        self.assertNotIn("sihirbaz", self.ayarlar())                                       # reddedilen istek hiçbir şey yazmadı
        kod, _, v = self.istek("POST", yol, {"durum": "bitti"}, {**a, "Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(kod, 200)
        self.assertTrue(json.loads(v)["bitti"])
        self.assertTrue(self.ayarlar()["sihirbaz"]["bitti"])
        self.assertIn("kilit", self.ayarlar())                                             # diğer ayarlar korunur
        self.assertRegex(self.istek("GET", "/", None, cerez)[2].decode("utf-8"), r'"sihirbaz":\s*\{"bitti":\s*true\}')
        # yeniden açma: "sifirla"
        self.assertEqual(self.istek("POST", yol, {"durum": "sifirla"}, a)[0], 200)
        self.assertFalse(self.ayarlar()["sihirbaz"]["bitti"])

    def ayarlar(self):
        with open(self.ayar, encoding="utf-8") as f:
            return json.load(f)


if __name__ == "__main__":
    unittest.main()
