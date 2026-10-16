"""Entegrasyon: tanıştırma yolu, brifing, sonuç döngüsü, haftalık özet ve bildirim uçları + arayüz + `kut.pyw --ozet`.
Uç testleri ayrı süreçte, geçici LOCALAPPDATA ve geçici (kurgusal) veriyle çalışır; zamanlayıcı çağrıları (schtasks/PowerShell) sahtedir:
gerçek Görev Zamanlayıcı'ya hiçbir görev kurulmaz. Şablon testleri metne bakar (tarayıcı gerekmez)."""
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

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOK = os.path.join(DEPO, "kut")
sys.path.insert(0, KOK)
import ag_giris  # noqa: E402


def sablon():
    with open(os.path.join(KOK, "ag_sablon.html"), encoding="utf-8") as f:
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


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SablonTest(unittest.TestCase):
    def test_js_soz_dizimi(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node yok")
        js = re.search(r"<script>\n(.*)</script>", sablon(), re.S).group(1)
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "sablon.js")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(js)
            r = subprocess.run([node, "--check", yol], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[:500])

    def test_yeni_kimlikler(self):
        h = sablon()
        for kimlik in ("o-brifing", "o-ozet", "oz-ac", "bf-ic", "hoz-ic"):
            self.assertIn(f'id="{kimlik}"', h, kimlik)
        for sekme in ("ulas", "sonuclar"):
            self.assertIn(f'data-pu="{sekme}"', h)
        for parca in ("id=\"d-yol\"", "id=\"d-brifing\"", "↗ Nasıl ulaşırım?", 'id="bil-acik"', 'id="bil-dene"', 'id="bil-adlar"', 'id="ul-form"', 'id="yol-takip"',
                      'id="bf-kopya"', 'id="bf-yazdir"', "Haftanın özeti", "Kut sana gelsin", "Kut sana gelir", "Temas olarak kaydet", "Deneme bildirimi gönder",
                      "Bildirimde adları göster", "Adlar kilit ekranında ve bildirim merkezinde görünebilir; Kut'un PIN kilidini aşar.",
                      "Bilgisayarında zamanlanmış bir görev kurulur; kapatınca kaldırılır."):
            self.assertIn(parca, h, parca)
        self.assertNotRegex(h, r'<[^>]*id="o-brifing"[^>]*hidden')

    def test_uymuyor_arayuzu(self):
        """Özet kartında görünür "Uymuyor" düğmesi + yatay kaydırma; Sonuçlar'da aynı gerekçe paneli; reddedilenler varsayılan gizli."""
        h = sablon()
        for parca in ('data-hoz-red=', 'class="kaydir-kap"', "function kaydirBagla(", "function redPanelHtml(", "function redPanelBagla(",
                      'data-red-gonder', "Neden uymuyor?", "Bir daha önerme", 'reddedildi: "Uymuyor"', "async function hozReddet(", 'id="so-red-goster"',
                      "uymayan öneri gizli", "touch-action:pan-y"):
            self.assertIn(parca, h, parca)
        g = islev_govdesi(h, "redPanelHtml")
        self.assertIn("esc(v[0])", g)   # gerekçe etiketi kaçışlı
        self.assertIn("esc(k)", g)
        self.assertIn('"reddedildi"]', h[h.index("const SO_DUGME"):h.index("const SO_EYLEM")])   # bekleyen kayıtta Uymuyor seçeneği
        self.assertIn('x.sonuc === "reddedildi" ? ""', islev_govdesi(h, "hozCiz"))                # reddedilen madde özette çizilmez

    def test_kisi_karti_dugmeleri_haric_kiside_yok(self):
        h = sablon()
        k = h[h.index("function kartCiz()"):h.index("function sekmeCiz()")]
        self.assertIn('${k.haric ? "" : `<button id="d-yol"', k)                              # hariç kişide ikisi de yok
        self.assertIn('${k.yakinlik <= 1 ? "vurgu" : "hayalet"}', k)                          # yakınlık 0–1'de vurgulu, 2–3'te ikincil
        self.assertIn("yolAc(k)", k)
        self.assertIn("brifingAc(k)", k)
        self.assertIn("k.haric", islev_govdesi(h, "yolAc"))
        self.assertIn("k.haric", islev_govdesi(h, "brifingAc"))

    def test_taslak_kutusuna_value_ile_yazilir_dinamik_metin_esc_ile(self):
        h = sablon()
        self.assertIn('ta.value = y.taslak || ""', islev_govdesi(h, "yolCiz"))
        self.assertIn("t.value = x ? x.taslak", islev_govdesi(h, "hozCiz"))
        for ad in ("yolCiz", "brifingCiz", "ulasHtml", "sonuclarHtml", "hozMaddeHtml", "hozBekleyenHtml", "bildirimHtml", "yolZincirHtml", "yolDetayHtml"):
            g = islev_govdesi(h, ad)
            self.assertNotRegex(g, r"\$\{(?:y|x|m|r|d|e|b|t|k|v|s)\.(?:taslak|ad|neden|adim|oneri|soru|metin|baslik|gerekce|etiket)\}", ad + " ham basım")
            self.assertIn("esc(", g, ad)
        self.assertNotIn("innerHTML = y.taslak", h)
        self.assertNotIn("innerHTML = x.taslak", h)

    def test_yol_vurgusu_odak_kodunu_yeniden_kullanir_ve_kapaninca_geri_doner(self):
        h = sablon()
        g = islev_govdesi(h, "gorunumUygula")
        self.assertIn("YOL_IDS.has(k.id)", g)                      # dolaylı (gizli) kişi yol üzerindeyse görünür
        self.assertIn('classList.toggle("yol-icinde"', g)
        self.assertIn('document.body.classList.toggle("yolda"', g)
        k = islev_govdesi(h, "yolKapat")
        self.assertIn("YOL_IDS.clear()", k)
        self.assertIn("filtrele()", k)                             # eski hal
        self.assertIn("yolKapat(true)", islev_govdesi(h, "kartCiz"))   # sağ panel yeniden çizilirse vurgu kalmaz
        self.assertIn("body.yolda .dugum:not(.yol-icinde)", h)
        self.assertIn("if (ODAK) odakCik();", islev_govdesi(h, "yolAc"))

    def test_brifing_yazdirma_yalniz_brifing(self):
        h = sablon()
        i = h.index("@media print{")
        css = h[i:h.index("/* haftalık özet: Kut sana gelir */")]
        self.assertIn("body>*:not(#o-brifing){display:none!important}", css)
        self.assertIn("window.print()", islev_govdesi(h, "brifingCiz"))
        self.assertIn("bf-yazdirma-gizle", css)

    def test_pencereler_esc_ile_kapanir_ve_odak_yonetilir(self):
        h = sablon()
        for kimlik in ("o-brifing", "o-ozet"):
            self.assertIn(f'<div class="ortu" id="{kimlik}"', h)       # .ortu: mevcut Esc / dış tıklama / ses gözlemcisi kalıbı
            self.assertIn('role="dialog" aria-modal="true"', h[h.index(f'id="{kimlik}"'):h.index(f'id="{kimlik}"') + 120])
        self.assertIn('ortuOdak("o-brifing"', h)
        self.assertIn('ortuOdak("o-ozet"', h)
        self.assertIn("onceki.focus(", islev_govdesi(h, "ortuOdak"))
        for a in ('aria-label="Nasıl ulaşırım? ${esc(k.ad)}"', 'aria-label="Görüşme brifingi: ${esc(k.ad)}"', 'aria-label="Özeti güncelle"', 'aria-label="Haftanın özeti"'):
            self.assertIn(a, h)

    def test_arayuz_sesi_mevcut_kaliplar(self):
        h = sablon()
        self.assertEqual(len(re.findall(r"ARAYUZ_SESLERI = \{", h)), 1)   # yeni ses eklenmedi
        bas = h.index("const ARAYUZ_SESLERI = {")
        blok = h[bas:h.index("\n};", bas)]
        self.assertEqual(sorted(re.findall(r"^\s+(\w+): \[", blok, re.M)), sorted(["tik", "sekme", "ac", "kapat", "ileri", "geri", "tur", "tamam"]))
        self.assertIn('arayuzSes("tamam")', islev_govdesi(h, "hozIsaretle"))

    def test_ozet_kendiliginden_acilis_kosullari(self):
        h = sablon()
        g = islev_govdesi(h, "hozBaslangic")
        for parca in ("DEMO", '"giriste"', '"sihirbazda"', "SIH.acik", "TUR.acik", ".ortu.acik", "kut-ozet-denendi"):
            self.assertIn(parca, g)
        a = islev_govdesi(h, "hozAc")
        self.assertIn("r.goruldu", a)                                    # görüldüyse kendiliğinden açılmaz
        self.assertIn('api("/api/ozet/goruldu"', islev_govdesi(h, "hozKapandi"))
        self.assertIn("return hozBaslangic();", h)                       # yalnız sihirbaz bitmiş kullanıcıda

    def test_sonuc_isaretleme_temas_kurali(self):
        h = sablon()
        self.assertIn('HOZ.temas && !TEMAS_SONUCLARI.includes(onceki) && TEMAS_SONUCLARI.includes(yeni)', h)   # Atla/Ertele → Yaptım temas ekler; Yaptım → İşe yaradı ikinci satır eklemez
        self.assertIn("checked", islev_govdesi(h, "temasKutusuHtml"))    # varsayılan işaretli
        self.assertIn("const HOZ = { o: null, temas: true,", h)        # kutu varsayılan işaretli

    def test_tur_adimi_ve_demo_yonlendirme(self):
        h = sablon()
        bas = h.index("const TUR_ADIMLARI = [")
        blok = h[bas:h.index("\n];", bas)]
        self.assertIn('{ id: "ulas", hedef: "#sag .yol-dugme"', blok)
        d = islev_govdesi(h, "demoApi")
        self.assertIn('y === "/api/yol" || y === "/api/brifing"', d)
        self.assertIn('"/api/demo/" + y.slice(5)', d)
        self.assertIn('throw new Error("Bu işlem örnekte kapalı', d)     # özet, sonuç, bildirim demoda kapalı

    def test_kisiye_puan_gibi_sayi_yok_bag_gucu_etiketi(self):
        h = sablon()
        u = islev_govdesi(h, "ulasHtml")
        self.assertNotIn("sıcaklık ${", u)
        self.assertIn("sicaklikYazi(t.sicaklik)", u)
        satir = h[h.index("const sicaklikYazi"):].split(chr(10))[0]
        for ifade in ("sıcak bağ", "ılık bağ", "soğuyan bağ"):
            self.assertIn(ifade, satir)
        self.assertNotIn("güç ${", h)                                  # "güç 72" yerine "bağ gücü"
        self.assertIn("bağ gücü ${", h)

    def test_demoda_ozet_sonuc_takip_gizli_ya_da_devre_disi(self):
        h = sablon()
        self.assertIn('if (DEMO) {   // örnekte özet ve sonuç defteri kapalı', h)
        self.assertIn('$("oz-ac").hidden = true;', h)
        self.assertIn('sb.disabled = true; sb.title = "Kendi ağında çalışır"', h)
        self.assertIn('DEMO ? `<button class="kucuk" id="yol-takip" disabled title="Kendi ağında çalışır', islev_govdesi(h, "yolDetayHtml"))

    def test_ulas_aramasi_sira_belirteci(self):
        g = islev_govdesi(sablon(), "ulasAra")
        self.assertIn("const sira = ++U.sira;", g)
        self.assertIn("if (sira !== U.sira) return;", g)
        self.assertLess(g.index('await api("/api/yol"'), g.index("if (sira !== U.sira) return;"))

    def test_yeni_css_demo_bolumunden_once(self):
        h = sablon()
        self.assertLess(h.index("/* ---- Tanıştırma yolu, brifing, sonuçlar"), h.index("/* ---- Demo önizlemesi"))
        css = h[h.index("/* ---- Tanıştırma yolu, brifing, sonuçlar"):h.index("/* ---- Demo önizlemesi")]
        self.assertNotRegex(css, r"box-shadow:0 0 \d+px")                # parıltı (glow) yok


def bootstrap(port, log, fail):
    return ("import sys, os, json, subprocess\n"
            f"sys.path.insert(0, {KOK!r})\n"
            "import ag_sunucu as s\nimport ag_bildirim as bd\nfrom http.server import ThreadingHTTPServer\n"
            f"LOG, FAIL = {log!r}, {fail!r}\n"
            "def sahte(args, **kw):\n"
            "    a = [str(x) for x in args]\n"
            "    open(LOG, 'a', encoding='utf-8').write(json.dumps(a) + '\\n')\n"
            "    if os.path.exists(FAIL) and '/Create' in a:\n"
            "        return subprocess.CompletedProcess(args, 1, b'', b'ERROR: Access is denied.')\n"
            "    return subprocess.CompletedProcess(args, 0, b'', b'')\n"
            "bd.subprocess.run = sahte\nbd._platform = lambda: 'windows'\nbd._destek = lambda: (True, '')\n"
            "bd._win_kimlik = lambda: bd.KUT_AUMID\nbd._win_kimlik_sil = lambda: None\n"   # gerçek kayıt defterine (HKCU) yazılmaz
            f"s.PORT = {port}\nThreadingHTTPServer(('127.0.0.1', {port}), s.Isleyici).serve_forever()\n")


class UcTest(unittest.TestCase):
    """Ayrı süreçte gerçek sunucu; zamanlayıcı sahte. Kurgusal kişiler: Ayşe Yılmaz, Mehmet Kaya (hariç), Deniz Demo, Elif Arslan."""

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="ku")
        cls.la = os.path.join(cls.d, "la")
        cls.veri = os.path.join(cls.d, "v")
        cls.log = os.path.join(cls.d, "zamanlayici.log")
        cls.hata_isareti = os.path.join(cls.d, "hata.isaret")
        os.makedirs(os.path.join(cls.la, "agim"))
        cls.port = bos_port()
        env = {**os.environ, "LOCALAPPDATA": cls.la, "AGIM_VERI": cls.veri, "PYTHONIOENCODING": "utf-8"}
        cls.p = subprocess.Popen([sys.executable, "-c", bootstrap(cls.port, cls.log, cls.hata_isareti)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(150):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        kod, cerez, _ = cls.istek("POST", "/api/kilit/kur", {"pin": "4321", "pin2": "4321"})
        assert kod == 200, kod
        cls.cerez = {"Cookie": cerez.split(";")[0]}
        sayfa = cls.istek("GET", "/", None, cls.cerez)[2].decode("utf-8")
        cls.anahtar = re.search(r'"anahtar":\s*"([^"]+)"', sayfa).group(1)
        cls.a = {**cls.cerez, "X-Ag-Anahtar": cls.anahtar, "Origin": f"http://127.0.0.1:{cls.port}"}
        for ad, tur, yak, kurum in (("Ayşe Yılmaz", "is", 3, "Kuzey Enerji"), ("Mehmet Kaya", "is", 0, "Gölge Holding"), ("Deniz Demo", "is", 0, "Kuzey Enerji"),
                                    ("Elif Arslan", "akademi", 2, "Kuzey Üniversitesi")):
            assert cls.post("/api/kisi", {"ad": ad, "tur": tur, "yakinlik": str(yak), "kurum": kurum})[0] == 200, ad
        with open(os.path.join(cls.veri, "haric.md"), "a", encoding="utf-8") as f:
            f.write("- Gölge Holding\n")
        for a, b in (("ayse-yilmaz", "deniz-demo"), ("ayse-yilmaz", "mehmet-kaya"), ("elif-arslan", "deniz-demo")):
            assert cls.post("/api/iliski", {"a": a, "b": b, "tip": "arkadas"})[0] == 200

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()
        cls.p.wait()
        time.sleep(0.3)
        shutil.rmtree(cls.d, ignore_errors=True)

    @classmethod
    def istek(cls, yontem, yol, govde=None, basliklar=None):
        h = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=60)
        h.request(yontem, yol, json.dumps(govde).encode() if govde is not None else None, {"Content-Type": "application/json", **(basliklar or {})})
        y = h.getresponse()
        r = (y.status, y.getheader("Set-Cookie"), y.read())
        h.close()
        return r

    @classmethod
    def post(cls, yol, govde, basliklar=None):
        k, _, v = cls.istek("POST", yol, govde, basliklar or cls.a)
        return k, (json.loads(v) if v else {})

    def get(self, yol, basliklar=None):
        k, _, v = self.istek("GET", yol, None, basliklar or self.a)
        return k, (json.loads(v) if v else {})

    def zamanlayici(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    # ---- kapılar ----
    YAZANLAR = ("/api/sonuc", "/api/sonuc/kaydet", "/api/bildirim", "/api/bildirim/dene", "/api/ozet/goruldu", "/api/ozet")
    HEPSI = ("/api/yol", "/api/brifing", "/api/ozet", "/api/ozet/goruldu", "/api/sonuc", "/api/sonuc/kaydet", "/api/bildirim", "/api/bildirim/dene")

    def test_kapilar(self):
        onceki = self.zamanlayici()
        for yol in self.HEPSI:
            self.assertEqual(self.post(yol, {}, self.cerez)[0], 403, yol)                                    # anahtar yok
            self.assertEqual(self.post(yol, {}, {**self.a, "X-Ag-Anahtar": "yanlis"})[0], 403, yol)
        for yol in ("/api/sonuclar", "/api/bildirim"):
            self.assertEqual(self.get(yol, self.cerez)[0], 403, yol)
            self.assertEqual(self.get(yol, {"Cookie": "x=y"})[0], 401, yol)                                   # geçersiz oturum: kilitli
        for yol in self.YAZANLAR:                                                                            # yabancı Origin
            self.assertEqual(self.post(yol, {}, {**self.a, "Origin": "http://evil.example"})[0], 403, yol)
        self.assertEqual(self.zamanlayici(), onceki)                                                         # hiçbiri zamanlayıcıya dokunmadı
        self.assertEqual(self.get("/api/yol")[0], 404)                                                       # POST uçları GET'te yok
        # kilitliyken (oturum kapalı, anahtar doğru) 401: en sonda ayrı test (kilit_kapali)

    def test_girdi_dogrulama(self):
        onceki = self.zamanlayici()
        for g in ({}, {"id": "../ben"}, {"id": "yok-kisi"}, {"id": 5}, {"id": "ayse-yilmaz", "ara": "x"}, {"ara": ""}, {"ara": "x" * 81}, {"ara": 5},
                  {"id": "elif-arslan", "amac": "a" * 121}, {"id": "elif-arslan", "amac": 7}, {"id": "elif-arslan", "bilinmeyen": 1}):
            self.assertEqual(self.post("/api/yol", g)[0], 400, g)
        for g in ({}, {"id": "../ben"}, {"id": "yok-kisi"}, {"id": "elif-arslan", "x": 1}):
            self.assertEqual(self.post("/api/brifing", g)[0], 400, g)
        for g in ({}, {"no": 0, "sonuc": "yaptim"}, {"no": "1", "sonuc": "yaptim"}, {"no": True, "sonuc": "yaptim"}, {"no": 999, "sonuc": "yaptim"}, {"no": 1, "sonuc": "belki"},
                  {"no": 1, "sonuc": "yaptim", "temas": "evet"}, {"no": 1, "sonuc": "yaptim", "not": "x" * 201}, {"no": 1, "sonuc": "yaptim", "kanal": "k" * 31}, {"no": 1, "sonuc": "yaptim", "zzz": 1}):
            self.assertEqual(self.post("/api/sonuc", g)[0], 400, g)
        for g in ({}, {"kaynak": "ozet", "kisi": "elif-arslan", "oneri": "x"}, {"kaynak": "yol", "kisi": "yok-kisi", "oneri": "x"}, {"kaynak": "yol", "kisi": "elif-arslan", "oneri": ""},
                  {"kaynak": "yol", "kisi": "elif-arslan", "oneri": "o" * 201}, {"kaynak": "yol", "kisi": "../x", "oneri": "x"}, {"kaynak": "yol", "kisi": "elif-arslan", "oneri": "x", "y": 1}):
            self.assertEqual(self.post("/api/sonuc/kaydet", g)[0], 400, g)
        self.assertEqual(self.post("/api/ozet", {"yenile": "evet"})[0], 400)
        self.assertEqual(self.post("/api/ozet", {"x": 1})[0], 400)
        for g in ({}, {"hafta": "bugun"}, {"hafta": 5}, {"hafta": "2026-W4"}):
            self.assertEqual(self.post("/api/ozet/goruldu", g)[0], 400, g)
        for g in ({"acik": "evet"}, {"siklik": "aylik"}, {"gun": 9}, {"gun": True}, {"saat": "25:00"}, {"adlar": 1}, {"zzz": 1}):
            self.assertEqual(self.post("/api/bildirim", g)[0], 400, g)
        self.assertEqual(self.post("/api/bildirim/dene", {"x": 1})[0], 400)
        self.assertEqual(self.zamanlayici(), onceki)                                                         # doğrulama hataları zamanlayıcıya hiç ulaşmadı

    # ---- mutlu yollar ----
    def test_yol_ve_ara(self):
        k, r = self.post("/api/yol", {"id": "deniz-demo", "amac": "enerji projesi"})
        self.assertEqual(k, 200)
        self.assertEqual(r["mod"], "yol")
        self.assertFalse(r["dogrudan"])
        y = r["yollar"][0]
        self.assertEqual([d["id"] for d in y["dugumler"]][-1], "deniz-demo")
        self.assertIn(y["ilk_adim"]["id"], ("ayse-yilmaz", "elif-arslan"))   # sıralama ag_yol testlerinin konusu; ikisi de deniz-demo'nun tanıdığı
        self.assertIn("enerji projesi", y["taslak"])
        self.assertNotIn("mehmet-kaya", json.dumps(r))
        k, r = self.post("/api/yol", {"id": "ayse-yilmaz"})                                               # yakınlık ≥ 1: doğrudan
        self.assertTrue(r["dogrudan"])
        k, r = self.post("/api/yol", {"ara": "Kuzey Enerji"})
        self.assertEqual(r["mod"], "ara")
        self.assertEqual([t["id"] for t in r["tanidiklarin"]], ["ayse-yilmaz"])
        self.assertEqual([h["hedef"]["id"] for h in r["hedefler"]], ["deniz-demo"])
        self.assertNotIn("mehmet-kaya", json.dumps(r))

    def test_brifing(self):
        k, r = self.post("/api/brifing", {"id": "ayse-yilmaz"})
        self.assertEqual(k, 200)
        self.assertEqual(r["brifing"]["kisi"]["id"], "ayse-yilmaz")
        self.assertTrue(r["markdown"].startswith("# Brifing: Ayşe Yılmaz"))
        self.assertNotIn("mehmet-kaya", json.dumps(r).lower().replace("mehmet kaya", "mehmet-kaya"))     # ortak tanıdıklarda hariç kişi yok
        self.assertNotIn("Mehmet", json.dumps(r, ensure_ascii=False))

    def test_haric_kisi_hicbir_yerde(self):
        self.assertEqual(self.post("/api/yol", {"id": "mehmet-kaya"})[0], 400)
        self.assertEqual(self.post("/api/brifing", {"id": "mehmet-kaya"})[0], 400)
        k, r = self.post("/api/sonuc/kaydet", {"kaynak": "yol", "kisi": "mehmet-kaya", "oneri": "Mehmet'e yaz"})
        self.assertEqual(k, 400)
        self.assertIn("hariç", r["hata"])
        self.assertNotIn("Mehmet", json.dumps(self.post("/api/ozet", {"yenile": True})[1], ensure_ascii=False))
        self.assertNotIn("Mehmet", json.dumps(self.get("/api/sonuclar")[1], ensure_ascii=False))

    def test_uymuyor_gerekceli_red(self):
        k, r = self.post("/api/sonuc/kaydet", {"kaynak": "yol", "kisi": "elif-arslan", "oneri": "Uymayan öneri denemesi"})
        no = r["no"]
        self.assertEqual(self.post("/api/sonuc", {"no": no, "sonuc": "reddedildi"})[0], 400)                       # neden zorunlu
        self.assertEqual(self.post("/api/sonuc", {"no": no, "sonuc": "reddedildi", "neden": "uydurma"})[0], 400)  # bilinmeyen neden
        self.assertEqual(self.post("/api/sonuc", {"no": no, "sonuc": "reddedildi", "neden": 3})[0], 400)
        k, r = self.post("/api/sonuc", {"no": no, "sonuc": "reddedildi", "neden": "yakin_degil", "not": "grup tanıdığı"})
        self.assertEqual((k, r["sonuc"], r["temas_eklendi"]), (200, "reddedildi", False))
        l = self.get("/api/sonuclar")[1]
        self.assertEqual(l["red_nedenleri"]["yakin_degil"][0], "O kadar yakın değiliz")
        self.assertEqual(next(x for x in l["kayitlar"] if x["no"] == no)["not"], "[yakin_degil] grup tanıdığı")
        self.assertEqual(l["istatistik"]["red_nedenleri"].get("yakin_degil"), 1)
        self.assertIn("red_nedenleri", self.post("/api/ozet", {})[1])
        self.assertEqual(self.post("/api/sonuc", {"no": no, "sonuc": "bekliyor"})[0], 200)   # geri al

    def test_sonuc_dongusu_ve_temas(self):
        k, r = self.post("/api/sonuc/kaydet", {"kaynak": "yol", "kisi": "elif-arslan", "oneri": "Elif üzerinden Deniz Demo ile tanış"})
        self.assertEqual(k, 200)
        no = r["no"]
        self.assertEqual(self.post("/api/sonuc/kaydet", {"kaynak": "yol", "kisi": "elif-arslan", "oneri": "Elif üzerinden Deniz Demo ile tanış"})[1]["no"], no)   # aynı hafta tekrar eklenmez
        k, r = self.post("/api/sonuc", {"no": no, "sonuc": "yaptim", "temas": True, "kanal": "telefon", "not": "Aradım"})
        self.assertEqual((k, r["sonuc"], r["temas_eklendi"]), (200, "yaptim", True))
        self.assertEqual(r["kayit"]["sonuc"], "yaptim")
        with open(os.path.join(self.veri, "kisiler", "elif-arslan.md"), encoding="utf-8") as f:
            self.assertIn("telefon · Kut önerisi: Elif üzerinden Deniz Demo ile tanış", f.read())
        k, r = self.post("/api/sonuc", {"no": no, "sonuc": "ise_yaradi", "temas": True})                  # ikinci karar yeni satır eklemez (aynı gün aynı satır)
        self.assertEqual(k, 200)
        l = self.get("/api/sonuclar")[1]
        self.assertIn(no, [x["no"] for x in l["kayitlar"]])
        self.assertEqual(l["etiketler"]["ise_yaradi"], "İşe yaradı")
        self.assertIn("son_8_hafta", l["istatistik"])
        self.assertEqual(next(x for x in l["kayitlar"] if x["no"] == no)["kisi_ad"], "Elif Arslan")

    def test_ozet(self):
        k, r = self.post("/api/ozet", {})
        self.assertEqual(k, 200)
        o = r["ozet"]
        self.assertRegex(o["hafta"], r"^\d{4}-W\d{2}$")
        for alan in ("selam", "maddeler", "sozler", "sonuc_bekleyen", "istatistik", "bos"):
            self.assertIn(alan, o)
        self.assertFalse(r["goruldu"])
        self.assertEqual(self.post("/api/ozet/goruldu", {"hafta": o["hafta"]})[0], 200)
        self.assertTrue(self.post("/api/ozet", {})[1]["goruldu"])
        self.assertTrue(os.path.exists(os.path.join(self.veri, "ozet", o["hafta"] + ".md")))

    def test_bildirim_gercek_zamanlayiciya_dokunmaz(self):
        self.assertFalse(os.path.exists(self.hata_isareti))
        k, d = self.get("/api/bildirim")
        self.assertEqual(k, 200)
        self.assertFalse(d["acik"])                                                                         # varsayılan kapalı
        self.assertFalse(d["adlar"])                                                                        # ve adsız
        self.assertTrue(d["destek"])
        k, d = self.post("/api/bildirim", {"acik": False, "saat": "08:30", "adlar": False})                 # kapalıyken yalnız ayar yazılır
        self.assertEqual(k, 200)
        self.assertEqual(d["saat"], "08:30")
        with open(os.path.join(self.la, "agim", "ayarlar.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["bildirim"]["saat"], "08:30")
        self.assertFalse(any("/Create" in c for c in self.zamanlayici()))                                  # görev kurulmadı
        k, d = self.post("/api/bildirim", {"acik": True, "gun": 2})
        self.assertEqual((k, d["acik"], d["kurulum"]), (200, True, "zamanlayici"))
        olusturma = [c for c in self.zamanlayici() if "/Create" in c]
        self.assertEqual(len(olusturma), 1)                                                                # yalnız SAHTE çağrı: gerçek schtasks'a gitmedi
        self.assertTrue(any(x in olusturma[0] for x in ("/SC", "/XML")))                                   # görev tanımı (zamanlama) sahte schtasks'a gitti
        self.assertEqual(self.post("/api/bildirim", {"acik": False})[1]["acik"], False)
        self.assertTrue(any("/Delete" in c for c in self.zamanlayici()))                                   # kapatınca kaldırılır
        k, r = self.post("/api/bildirim/dene", {})
        self.assertEqual((k, r["gosterildi"]), (200, True))
        gosterim = [c for c in self.zamanlayici() if "-EncodedCommand" in c]
        self.assertEqual(len(gosterim), 1)
        self.assertNotIn("Ayşe", json.dumps(gosterim))                                                     # deneme bildirimi içerik taşımaz

    def test_kurulum_hatasi_anlasilir_400(self):
        open(self.hata_isareti, "w").close()
        try:
            k, r = self.post("/api/bildirim", {"acik": True})
            self.assertEqual(k, 400)
            self.assertTrue(r["hata"])
            self.assertFalse(self.get("/api/bildirim")[1]["acik"])                                         # başarısız kurulumda ayar açık kalmaz
        finally:
            os.remove(self.hata_isareti)

    # ---- demo ----
    def test_demo_uclari_demo_anahtariyla_calisir(self):
        onceki = sorted(os.listdir(self.veri))
        k, _, v = self.istek("POST", "/api/demo/baslat", {}, self.a)
        self.assertEqual(k, 200)
        sayfa = self.istek("GET", "/demo", None, self.cerez)[2].decode("utf-8")
        demo = re.search(r'"anahtar":\s*"([^"]+)"', sayfa).group(1)
        self.assertNotEqual(demo, self.anahtar)
        d = {**self.a, "X-Ag-Anahtar": demo}
        for yol, g in (("/api/demo/yol", {"id": "selin-hoca"}), ("/api/demo/brifing", {"id": "selin-hoca"})):
            self.assertEqual(self.post(yol, g, self.a)[0], 403, yol)                                     # gerçek anahtarı reddeder
            self.assertEqual(self.post(yol, {"id": "../x"}, d)[0], 400, yol)
        k, r = self.post("/api/demo/yol", {"id": "selin-hoca"}, d)
        self.assertEqual(k, 200)
        self.assertTrue(r["dogrudan"])
        self.assertTrue(r["yollar"][0]["taslak"])
        k, r = self.post("/api/demo/yol", {"ara": "açık veri"}, d)
        self.assertEqual(k, 200)
        self.assertTrue(r["tanidiklarin"])
        k, r = self.post("/api/demo/brifing", {"id": "selin-hoca"}, d)
        self.assertEqual(k, 200)
        self.assertEqual(r["brifing"]["kisi"]["ad"], "Selin Hoca")
        self.assertTrue(r["brifing"]["gecmis"])                                                           # kurgusal geçmiş öneriler
        self.assertTrue(r["brifing"]["strateji"])                                                         # demo strateji okumasından
        for yol in ("/api/yol", "/api/brifing"):
            self.assertEqual(self.post(yol, {"id": "selin-hoca"}, d)[0], 403, yol)                       # demo anahtarı gerçek uçta geçmez
        for yol in ("/api/ozet", "/api/ozet/goruldu", "/api/sonuc", "/api/sonuc/kaydet", "/api/bildirim", "/api/bildirim/dene"):
            self.assertEqual(self.post(yol, {}, d)[0], 403, yol)
        self.assertEqual(self.post("/api/demo/kapat", {}, d)[0], 200)
        self.assertEqual(self.post("/api/demo/yol", {"id": "selin-hoca"}, d)[0], 403)                    # demo kapanınca anahtar geçersiz
        sonra = sorted(os.listdir(self.veri))
        self.assertEqual([a for a in sonra if a not in onceki], [])                                       # demo gerçek veri klasörüne hiçbir şey yazmadı

    def test_ozet_goruldu_hafta_gercekten_dogrulanir(self):
        for h in ("2026-W00", "2026-W54", "2025-W53", "2026-W99", "2026-w42", "26-W42", "2026-W4", "2026-W42 "):
            self.assertEqual(self.post("/api/ozet/goruldu", {"hafta": h})[0], 400, h)
        self.assertEqual(self.post("/api/ozet/goruldu", {"hafta": "2026-W53"})[0], 200)     # 2026'da 53 hafta var
        self.assertEqual(self.post("/api/ozet/goruldu", {"hafta": "2026-W42"})[0], 200)

    def test_bildirim_uclari_veri_kilidini_tutmaz(self):
        import ag_sunucu
        self.assertIn("/api/bildirim", ag_sunucu.KILITSIZ)
        self.assertIn("/api/bildirim/dene", ag_sunucu.KILITSIZ)

    def dosya(self, kid):
        return os.path.join(self.veri, "kisiler", kid + ".md")

    def test_uzak_kilit_yalniz_kutun_koydugu_private_i_kaldirir(self):
        # 1) private yok: Kut koyar, işaretler; açınca kaldırır
        self.assertEqual(self.post("/api/kisi/uzak", {"id": "deniz-demo", "kapali": True})[0], 200)
        m = open(self.dosya("deniz-demo"), encoding="utf-8").read()
        self.assertIn("remote_allowed: false", m)
        self.assertIn("visibility: private", m)
        self.assertIn("visibility_kut: true", m)
        self.assertEqual(self.post("/api/kisi/uzak", {"id": "deniz-demo", "kapali": False})[0], 200)
        m = open(self.dosya("deniz-demo"), encoding="utf-8").read()
        self.assertNotIn("visibility", m)
        self.assertNotIn("remote_allowed", m)
        # 2) kullanıcı private'ı elle koymuş: Kut işaret koymaz, açınca private kalır
        yol = self.dosya("elif-arslan")
        m = open(yol, encoding="utf-8").read()
        self.assertTrue(m.startswith("---" + chr(10)))
        open(yol, "w", encoding="utf-8", newline="").write("---" + chr(10) + "visibility: private" + chr(10) + m[4:])
        self.assertEqual(self.post("/api/kisi/uzak", {"id": "elif-arslan", "kapali": True})[0], 200)
        self.assertNotIn("visibility_kut", open(yol, encoding="utf-8").read())
        self.assertEqual(self.post("/api/kisi/uzak", {"id": "elif-arslan", "kapali": False})[0], 200)
        m = open(yol, encoding="utf-8").read()
        self.assertIn("visibility: private", m)
        self.assertNotIn("remote_allowed", m)

    def test_arsivleme_mtime_tasima_anindan_sayilir(self):
        self.assertEqual(self.post("/api/kisi", {"ad": "Eski Dosya", "tur": "cevre", "yakinlik": "1"})[0], 200)
        yol = self.dosya("eski-dosya")
        eski = time.time() - 200 * 86400
        os.utime(yol, (eski, eski))
        self.assertEqual(self.post("/api/kisi/arsivle", {"id": "eski-dosya"})[0], 200)
        klasor = os.path.join(self.veri, "arsiv", "cikarilan")
        ad = next(a for a in os.listdir(klasor) if a.startswith("eski-dosya-"))
        self.assertLess(time.time() - os.path.getmtime(os.path.join(klasor, ad)), 120)     # arşiv bakımı 90 günü taşıma anından sayar

    def test_zz_kilitliyken_401(self):
        kod, cerez, _ = self.istek("POST", "/api/kilit/kapat", {}, self.a)
        self.assertEqual(kod, 200)
        for yol in self.HEPSI:
            self.assertEqual(self.post(yol, {}, self.a)[0], 401, yol)
        for yol in ("/api/sonuclar", "/api/bildirim"):
            self.assertEqual(self.get(yol, self.a)[0], 401, yol)


class OzetBaslaticiTest(unittest.TestCase):
    """`kut.pyw --ozet`: sunucu açılmaz, çıkış kodu 0, bildirim yolu --sessiz ile kapalı; veri klasörü yoksa yeniden yaratılmaz."""

    def calistir(self, la, *args):
        env = {k: v for k, v in os.environ.items() if k not in ("AGIM_VERI", "KUT_ISKELETSIZ")}
        env.update(LOCALAPPDATA=la, PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, os.path.join(DEPO, "kut.pyw"), "--ozet", *args], env=env, capture_output=True, text=True, timeout=120)

    def test_arguman_ayristirma(self):
        self.assertEqual(ag_giris.veri_yolu(["--ozet", "--veri", "C:\\a b"]), "C:\\a b")
        self.assertEqual(ag_giris.veri_yolu(["--ozet", "--veri=D:\\x"]), "D:\\x")
        self.assertEqual(ag_giris.veri_yolu(["--ozet"]), "")

    def test_ayar_kapaliyken_hicbir_sey_yapmaz(self):
        with tempfile.TemporaryDirectory() as d:
            veri = os.path.join(d, "veri")
            os.makedirs(veri)
            r = self.calistir(os.path.join(d, "la"), "--veri", veri, "--sessiz")
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            self.assertFalse(os.path.exists(os.path.join(veri, "ozet")))             # kapalı: özet bile üretilmez

    def test_ozet_uretir_sunucu_acmaz_bildirmez(self):
        with tempfile.TemporaryDirectory() as d:
            la, veri = os.path.join(d, "la"), os.path.join(d, "veri")
            os.makedirs(os.path.join(la, "agim"))
            os.makedirs(veri)
            with open(os.path.join(la, "agim", "ayarlar.json"), "w", encoding="utf-8") as f:
                json.dump({"bildirim": {"acik": True, "siklik": "haftalik", "gun": 0, "saat": "09:00", "adlar": False, "veri": veri, "kurulum": "zamanlayici", "son": ""}}, f)
            r = self.calistir(la, "--veri", veri, "--sessiz")
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            self.assertTrue(any(a.endswith(".md") for a in os.listdir(os.path.join(veri, "ozet"))))   # özet hazır: Kut açılınca seni bekler
            self.assertFalse(os.path.exists(os.path.join(la, "agim", "sunucu.log")) and "hata" in open(os.path.join(la, "agim", "sunucu.log"), encoding="utf-8").read())

    def test_veri_klasoru_yoksa_yeniden_yaratilmaz_kod_2(self):
        with tempfile.TemporaryDirectory() as d:
            yok = os.path.join(d, "tasinmis")
            r = self.calistir(os.path.join(d, "la"), "--veri", yok, "--sessiz")
            self.assertEqual(r.returncode, 2, r.stderr[-500:])
            self.assertFalse(os.path.exists(yok))                                    # iskelet kurulmadı

    def test_varsayilan_veri_iskeleti_istenmeden_kurulmaz(self):
        """--veri verilmişse ag_cekirdek içe aktarılırken <depo>/veri iskeleti için yeni dosya oluşmaz (klasör zaten varsa içeriği değişmez)."""
        varsayilan = os.path.join(DEPO, "veri")
        onceki = sorted(os.listdir(varsayilan)) if os.path.isdir(varsayilan) else None
        with tempfile.TemporaryDirectory() as d:
            veri = os.path.join(d, "veri")
            os.makedirs(veri)
            self.assertEqual(self.calistir(os.path.join(d, "la"), "--veri", veri, "--sessiz").returncode, 0)
        self.assertEqual(sorted(os.listdir(varsayilan)) if os.path.isdir(varsayilan) else None, onceki)

    def test_spec_girisi_ag_giris(self):
        with open(os.path.join(DEPO, "paketleme", "kut.spec"), encoding="utf-8") as f:
            spec = f.read()
        self.assertIn("'ag_giris.py'", spec)                                          # Kut.exe --ozet de bu girişten geçer
        for m in ("ag_bildirim", "ag_ozet", "ag_sonuc", "ag_yol", "ag_brifing"):
            self.assertIn(f"'{m}'", spec)


if __name__ == "__main__":
    unittest.main()
