"""Arayüz davranışı: kişiselleştirilmiş karşılama, akıllı sihirbaz, arayüz sesleri ve "Arayüz sesleri" ayarı.
Arayüz testleri şablon metnine bakar (tarayıcı gerekmez; saf işlevler node varsa gerçekten çalıştırılır);
API testleri ayrı süreçte, geçici LOCALAPPDATA ile çalışır (gerçek veri ve gerçek sunucuya dokunmaz)."""
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
    i = h.index("function " + ad + "(")
    j = h.index("{", i)
    d = 0
    for k in range(j, len(h)):
        d += h[k] == "{"
        d -= h[k] == "}"
        if d == 0:
            return h[j:k + 1]
    raise AssertionError(ad)


class AcilisSesiBagimsizTest(unittest.TestCase):
    """Açılıştaki Kut sesi hiçbir ayarla kapanmaz: yeni arayüz sesi ayarının hiçbir dalı ona dokunmaz."""
    def test_girisSesi_arayuz_ayarina_bakmaz(self):
        h = sablon()
        g = islev_govdesi(h, "girisSesi")
        for yasak in ("ARAYUZ", "arayuz", "arayuzSes", "arayuz_sesi", "/api/arayuz"):
            self.assertNotIn(yasak, g, f"girisSesi {yasak} içeremez")
        self.assertIn("setTimeout(girisSesi, 60)", islev_govdesi(h, "girisOynat"))   # açılış koşulsuz çağırır
        self.assertNotIn("ARAYUZ", islev_govdesi(h, "girisOynat"))
        self.assertNotIn("ARAYUZ", islev_govdesi(h, "girisBitir"))

    def test_acilis_sesi_hicbir_yerel_anahtarla_kapanmaz(self):
        h = sablon()
        self.assertNotIn(chr(34) + "kut-ses" + chr(34), h)                                   # eski kapatma anahtarı kalmadı
        g = islev_govdesi(h, "girisSesi")
        self.assertNotIn("localStorage", g)
        self.assertTrue(g.lstrip("{").lstrip().startswith("const A = SES;"))   # ilk iş sesi çalmaktır; önünde atlama yok

    def test_profil_adimi_ad_ve_foto_varsa_hazir(self):
        h = sablon()
        satir = next(x for x in h.splitlines() if 'id: "profil"' in x)
        self.assertIn("hazir: () => !!ilkAd() && !!BEN.foto,", satir)    # bilinen: "adın ve fotoğrafın" ile tutarlı

    def test_arayuz_ayari_yalniz_arayuz_sesinde_okunur(self):
        h = sablon()
        giris = h.index("function girisSesi(")
        giris_son = giris + len(islev_govdesi(h, "girisSesi"))
        okuyanlar = [m.start() for m in re.finditer(r"ARAYUZ\.ses", h)]
        self.assertTrue(okuyanlar)
        for i in okuyanlar:
            self.assertFalse(giris <= i <= giris_son, "girisSesi ayara bakamaz")
        # ayarı okuyan işlevler yalnız arayüz sesi işlevleridir
        for ad in ("arayuzSes", "arayuzSesHtml", "sihSes"):
            self.assertIn("ARAYUZ.ses", islev_govdesi(h, ad))
        self.assertNotIn("girisSesi", islev_govdesi(h, "arayuzSes"))

    def test_acilis_sesi_sunucu_ayariyla_degismez(self):
        with open(os.path.join(KOK, "ag_sunucu.py"), encoding="utf-8") as f:
            py = f.read()
        self.assertNotIn("girisSesi", py)
        with open(os.path.join(KOK, "ag_cekirdek.py"), encoding="utf-8") as f:
            sablon_py = f.read()
        self.assertNotIn("arayuz_sesi", sablon_py)


class ArayuzSesleriTest(unittest.TestCase):
    def test_sesler_webaudio_ve_kisa(self):
        h = sablon()
        bas = h.index("const ARAYUZ_SESLERI = {")
        blok = h[bas:h.index("\n};", bas)]
        for ad in ("tik", "sekme", "ac", "kapat", "ileri", "geri", "tur", "tamam"):
            self.assertRegex(blok, rf"\b{ad}: \[\d+,")
        # tamam akoru dışındaki sesler 30–120 ms
        for ad, uz in re.findall(r"\b(\w+): \[\d+, \(A, t, o\) => [^\n]*?(?:, ){2}t, (\.\d+),", blok):
            if ad != "tamam":
                self.assertTrue(.03 <= float(uz) <= .12, (ad, uz))
        for ad in ("tik", "sekme", "ac", "kapat", "ileri", "geri", "tur"):
            satir = next(x for x in blok.splitlines() if re.match(rf"\s*{ad}:", x))
            for uz in re.findall(r"t(?: \+ \.\d+)?, (\.\d+), \.\d+\)", satir):
                self.assertLessEqual(float(uz), .12, (ad, uz))
        motor = blok + islev_govdesi(h, "ton") + islev_govdesi(h, "arayuzSes")
        for yasak in ("new Audio(", "fetch(", ".mp3", ".wav", ".ogg", "decodeAudioData"):   # dış ses dosyası ve ağ yok
            self.assertNotIn(yasak, motor)

    def test_autoplay_hiz_siniri_ve_mevcut_baglam(self):
        h = sablon()
        g = islev_govdesi(h, "arayuzSes")
        self.assertIn('A.state !== "running"', g)            # etkileşim öncesi çalmaz
        self.assertIn("const A = SES", g)                    # açılış sesinin AudioContext'i yeniden kullanılır
        self.assertNotIn("new AudioContext", g)
        self.assertIn("ARAYUZ.son[ad]", g)                   # aynı ses için hız sınırı
        self.assertIn("ARAYUZ.zamanlar.length >= 4", g)      # yağmur sınırı
        self.assertIn("document.hidden", g)
        k = islev_govdesi(h, "arayuzSesleriniKur")
        self.assertIn('["pointerdown", "keydown"]', k)       # bağlam ilk kullanıcı etkileşiminde kurulur
        self.assertIn("once: true", k)

    def test_kancalar(self):
        h = sablon()
        self.assertIn("new MutationObserver", islev_govdesi(h, "arayuzSesleriniKur"))   # pencere aç/kapa
        self.assertIn('arayuzSes(simdi ? "ac" : "kapat")', h)
        self.assertIn('[data-sekme],[data-pu]', h)                                       # sekme değişimi
        self.assertIn('arayuzSes(d > 0 ? "ileri" : "geri")', islev_govdesi(h, "sihIlerle"))   # sihirbaz geçişi
        self.assertIn('arayuzSes(yon < 0 ? "geri" : "tur")', islev_govdesi(h, "turGit"))      # sahne ışığı adımı
        self.assertIn('arayuzSes("tamam")', islev_govdesi(h, "turBitir"))                    # kapanış akoru

    def test_ayar_penceresinde_anahtar(self):
        h = sablon()
        self.assertIn("arayuzSesHtml()", islev_govdesi(h, "ayarCiz"))
        self.assertIn('id="ay-arayuz-ses"', h)
        self.assertIn('api("/api/arayuz/ses", { acik: hedef })', islev_govdesi(h, "arayuzSesBagla"))
        self.assertIn("MOD.arayuz_sesi !== false", h)         # varsayılan açık
        self.assertIn('id="sih-arayuz-ses"', islev_govdesi(h, "sihSes"))


class KarsilamaVeSihirbazTest(unittest.TestCase):
    def test_metinler_esc_ile_basilir(self):
        h = sablon()
        self.assertIn("${esc(karsilamaSatiri())}", islev_govdesi(h, "sihHos"))
        self.assertIn("esc(bil.join", islev_govdesi(h, "sihHos"))
        self.assertIn("textContent = typeof a.baslik", islev_govdesi(h, "sihGoster"))   # ad başlığa textContent ile girer
        self.assertIn("insertAdjacentHTML", islev_govdesi(h, "sihGoster"))
        self.assertIn("${esc(a.hazirMetin)}", islev_govdesi(h, "sihGoster"))
        self.assertNotIn("${BEN.", h[h.index("function sihHos("):h.index("function sihYz(")])

    def test_akilli_adimlar(self):
        h = sablon()
        bas = h.index("const SIH_ADIMLARI = [")
        blok = h[bas:h.index("\n];", bas)]
        self.assertEqual(re.findall(r'\{ id: "(\w+)"', blok), ["hos", "profil", "yz", "ses", "kasa", "okul"])
        for kim in ("profil", "yz", "ses", "kasa", "okul"):
            satir = next(x for x in blok.splitlines() if f'id: "{kim}"' in x)
            self.assertIn("hazir: () =>", satir, kim)
            self.assertIn("bilinen:", satir, kim)
        self.assertNotIn("hazir:", next(x for x in blok.splitlines() if 'id: "hos"' in x))
        self.assertIn("MOD.bilinen.yz", blok)
        self.assertIn("MOD.bilinen.kasa", blok)
        self.assertIn("SESD.oku && SESD.yaz", blok)
        # akıllı kurulum hazır adımları çıkarır; tam kurulum hepsini tutar
        k = islev_govdesi(h, "sihKur")
        self.assertIn("SIH.tam ? gor : gor.filter(a => !hazir(a))", k)
        self.assertIn("Bunları zaten biliyorum:", h)
        self.assertIn("sihirbazAc(true)", h)                 # Ayarlar → tam sihirbaz
        self.assertIn("Hazır olanları da gez", h)
        self.assertIn("✓ Hazır:", islev_govdesi(h, "sihGoster"))

    def test_foto_istegi_yalniz_yoksa_ve_tamamlanma_mantigi_bozulmadi(self):
        h = sablon()
        g = islev_govdesi(h, "sihProfil")
        self.assertIn("fotoVar", g)
        self.assertIn("Fotoğraf ekle", g)
        self.assertIn('api("/api/sihirbaz", { durum: "bitti" })', h)
        self.assertIn("MOD.sihirbaz.bitti", h)
        self.assertIn("kut-tur-bekliyor", h)

    def test_metinler_ve_saat_dilimleri(self):
        h = sablon()
        for dilim in ("sabah", "ogle", "aksam", "gece"):
            self.assertRegex(h, rf"\b{dilim}: \[\"")
        self.assertIn("Merhaba, ben de seni bekliyordum.", h)
        self.assertIn("donusKarsilama()", islev_govdesi(h, "donusKarsila"))
        self.assertIn("sessionStorage.getItem(\"kut-karsilama\")", islev_govdesi(h, "donusKarsila"))

    def test_saf_islevler_node_ile(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node yok")
        h = sablon()
        parcalar = [h[h.index("const KARSILAMA = {"):h.index("function gunDilimi(")]]
        for ad in ("gunDilimi", "ilkAd", "dogumGunuMu", "karsilamaSatiri", "donusKarsilama", "kapanisSatiri"):
            parcalar.append("function " + ad + "(" + h.split("function " + ad + "(", 1)[1].split("\n}\n", 1)[0] + "\n}\n")
        parcalar.insert(1, h[h.index("const gunNo ="):h.index("\n", h.index("const gunNo ="))])
        kod = ("let BEN = {};\n" + "\n".join(parcalar) + """
const sonuc = {};
const saat = s => new Date(2026, 5, 10, s, 0, 0);
sonuc.dilim = [3, 5, 10, 11, 16, 17, 21, 22, 23].map(s => gunDilimi(saat(s)));
BEN = { ad: "Ece Nur Aksoy" }; sonuc.ad = ilkAd();
BEN = { ad: "Ben" }; sonuc.adsiz = ilkAd();
BEN = {}; sonuc.bos = ilkAd();
BEN = { ad: "Ece" }; sonuc.donus = donusKarsilama(saat(9)); sonuc.kapanis = kapanisSatiri();
BEN = {}; sonuc.donusAdsiz = donusKarsilama(saat(9));
BEN = { ad: "Ece", dogum_gunu: "2001-06-10" }; sonuc.dg = dogumGunuMu(saat(9)); sonuc.dgSatir = donusKarsilama(saat(9));
BEN = { ad: "Ece", dogum_gunu: "2001-06-11" }; sonuc.dgYok = dogumGunuMu(saat(9));
BEN = { dogum_gunu: "06-10" }; sonuc.dgKisa = dogumGunuMu(saat(9));
BEN = {}; for (const [k, l] of Object.entries(KARSILAMA)) sonuc["k_" + k] = l.length;
sonuc.satir = karsilamaSatiri(saat(14));
console.log(JSON.stringify(sonuc));
""")
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "k.js")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(kod)
            r = subprocess.run([node, yol], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr[:500])
        s = json.loads(r.stdout)
        self.assertEqual(s["dilim"], ["gece", "sabah", "sabah", "ogle", "ogle", "aksam", "aksam", "gece", "gece"])
        self.assertEqual(s["ad"], "Ece")
        self.assertEqual(s["adsiz"], "")
        self.assertEqual(s["bos"], "")
        self.assertTrue(s["donus"].startswith("Günaydın, Ece. "))
        self.assertTrue(s["donusAdsiz"].startswith("Günaydın. "))
        self.assertIn("Ece", s["kapanis"])
        self.assertTrue(s["dg"])
        self.assertIn("Doğum günün kutlu olsun, Ece", s["dgSatir"])
        self.assertFalse(s["dgYok"])
        self.assertTrue(s["dgKisa"])
        for k in ("sabah", "ogle", "aksam", "gece"):
            self.assertGreaterEqual(s["k_" + k], 3)
        self.assertTrue(s["satir"])


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ArayuzAyarApiTest(unittest.TestCase):
    """Ayrı süreçte sunucu, geçici LOCALAPPDATA: /api/arayuz/ses kapıları, varsayılan, kalıcılık, sihirbaz ucunun bozulmaması."""
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

    def ayarlar(self):
        with open(self.ayar, encoding="utf-8") as f:
            return json.load(f)

    def test_kapilar_varsayilan_kalicilik_sihirbaz_ve_dogum_gunu(self):
        yol = "/api/arayuz/ses"
        self.assertEqual(self.istek("POST", yol, {"acik": False})[0], 403)                 # kilitli ve anahtarsız
        kod, cerez, _ = self.istek("POST", "/api/kilit/kur", {"pin": "4321", "pin2": "4321"})
        self.assertEqual(kod, 200)
        cerez = {"Cookie": cerez.split(";")[0]}
        sayfa = self.istek("GET", "/", None, cerez)[2].decode("utf-8")
        anahtar = re.search(r'"anahtar":\s*"([^"]+)"', sayfa).group(1)
        self.assertRegex(sayfa, r'"arayuz_sesi":\s*true')                                  # varsayılan AÇIK
        self.assertRegex(sayfa, r'"bilinen":\s*\{"yz":\s*false,\s*"kasa":\s*false\}')      # yeni kurulum: bilinen yok
        self.assertRegex(sayfa, r'"sihirbaz":\s*\{"bitti":\s*false\}')
        a = {**cerez, "X-Ag-Anahtar": anahtar, "Origin": f"http://127.0.0.1:{self.port}"}
        self.assertEqual(self.istek("POST", yol, {"acik": False}, cerez)[0], 403)          # anahtar yok
        self.assertEqual(self.istek("POST", yol, {"acik": False}, {**a, "Origin": "http://evil.example"})[0], 403)   # yabancı kaynak
        self.assertEqual(self.istek("GET", yol, None, a)[0], 404)                          # yazan uç yalnız POST
        for kotu in ({}, {"acik": "hayir"}, {"acik": 0}, {"acik": None}):
            self.assertEqual(self.istek("POST", yol, kotu, a)[0], 400, kotu)
        self.assertNotIn("arayuz", self.ayarlar())                                         # reddedilenler hiçbir şey yazmadı
        kod, _, v = self.istek("POST", yol, {"acik": False}, a)
        self.assertEqual(kod, 200)
        self.assertFalse(json.loads(v)["acik"])
        self.assertEqual(self.ayarlar()["arayuz"], {"ses": False})
        self.assertIn("kilit", self.ayarlar())                                             # diğer ayarlar korunur
        self.assertRegex(self.istek("GET", "/", None, cerez)[2].decode("utf-8"), r'"arayuz_sesi":\s*false')   # sayfa yenilenince kalıcı
        self.assertEqual(self.istek("POST", yol, {"acik": True}, a)[0], 200)
        self.assertRegex(self.istek("GET", "/", None, cerez)[2].decode("utf-8"), r'"arayuz_sesi":\s*true')
        # sihirbaz ucu bozulmadı ve ses ayarını silmez
        self.assertEqual(self.istek("POST", "/api/sihirbaz", {"durum": "bitti"}, a)[0], 200)
        self.assertTrue(self.ayarlar()["sihirbaz"]["bitti"])
        self.assertEqual(self.ayarlar()["arayuz"], {"ses": True})
        self.assertEqual(self.istek("POST", "/api/sihirbaz", {"durum": "belki"}, a)[0], 400)
        self.assertEqual(self.istek("POST", "/api/sihirbaz", {"durum": "sifirla"}, a)[0], 200)
        self.assertFalse(self.ayarlar()["sihirbaz"]["bitti"])
        # yapay zekâ sağlayıcısı açıkça seçilince sihirbaz bunu "bilinen" sayar
        ay = self.ayarlar()
        ay["saglayici"] = "claude"
        with open(self.ayar, "w", encoding="utf-8") as f:
            json.dump(ay, f)
        self.assertRegex(self.istek("GET", "/", None, cerez)[2].decode("utf-8"), r'"bilinen":\s*\{"yz":\s*true')

        # doğum günü profilde saklanır (karşılama için)
        self.assertEqual(self.istek("POST", "/api/ben", {"ad": "Gizem Tolunay", "dogum_gunu": "2001-06-10"}, a)[0], 200)
        sayfa = self.istek("GET", "/", None, cerez)[2].decode("utf-8")
        self.assertIn('"dogum_gunu": "2001-06-10"', sayfa.replace('"dogum_gunu":"2001', '"dogum_gunu": "2001'))
        self.assertRegex(sayfa, r'"ad":\s*"Gizem Tolunay"')
        # biçim dışı doğum günü reddedilir; geçerli (YYYY-AA-GG, AA-GG, boş) kabul edilir
        for kotu in ("2001-13-10", "yarın", "2001-06-10\nasistan: x", "06/10", "2001-06-1", "x" * 500):
            self.assertEqual(self.istek("POST", "/api/ben", {"dogum_gunu": kotu}, a)[0], 400, kotu)
        self.assertEqual(self.istek("POST", "/api/ben", {"dogum_gunu": "06-10"}, a)[0], 200)
        self.assertEqual(self.istek("POST", "/api/ben", {"dogum_gunu": ""}, a)[0], 200)
        # kilitliyken (çerezsiz istek) sayfada ad, doğum günü ve bilinen yok
        kilitli = self.istek("GET", "/")[2].decode("utf-8")
        self.assertNotIn("Gizem Tolunay", kilitli)
        self.assertIn("Gizem Tolunay", self.istek("GET", "/", None, cerez)[2].decode("utf-8"))
        self.assertNotIn('"bilinen"', kilitli)
        self.assertNotIn('"arayuz_sesi"', kilitli)


if __name__ == "__main__":
    unittest.main()
