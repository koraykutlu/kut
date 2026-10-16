import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date
from unittest import mock

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
sys.path.insert(0, KOK)
import ag_ajanda as aj  # noqa: E402
import ag_cekirdek as c  # noqa: E402
import ag_hedef as hd  # noqa: E402
import ag_kesif as ks  # noqa: E402
import ag_strateji as st  # noqa: E402

BUGUN = date(2026, 10, 15)


def kur(self):
    """Geçici veri klasörü: kişiler (sonraki adım, ihmal, söz, temas), hariç kişi, hedefler, strateji okuması, keşif kararları ve önbelleği."""
    self.eski = c.VERI
    self.d = tempfile.TemporaryDirectory()
    c.veri_klasoru(os.path.join(self.d.name, "veri"))
    self.kesif = mock.patch.object(ks, "KLASOR", os.path.join(self.d.name, "kesif"))
    self.kesif.start()
    os.makedirs(ks.KLASOR, exist_ok=True)
    with open(c.HARIC, "a", encoding="utf-8") as f:
        f.write("\n- Gizli Parti\n")
    c.kisi_yaz("ayse", {"ad": "Ayşe Demir", "tur": "yakin", "yakinlik": 3, "son_temas": "2026-10-05", "sonraki_adim": "Kitabı götür", "sonraki_tarih": "2026-10-17"},
               "## Sözler\n- [ ] 2026-10-01 · ben → o · kitabı göndermek (son: 2026-10-14)\n- [x] 2026-09-20 · o → ben · staj ilanı (son: 2026-09-30) (tamam: 2026-09-28)\n"
               "- [-] 2026-09-01 · ben → o · iptal olan söz (iptal: 2026-09-05)\n- [ ] 2026-09-01 · o → ben · eski tarihsiz söz\n\n"
               "## Temas\n- 05.10.2026 · whatsapp · konuştuk\n- 01.10.2026 · yüz yüze · kahve\n")
    c.kisi_yaz("mehmet", {"ad": "Mehmet Kaya", "tur": "is", "yakinlik": 2, "son_temas": "2026-08-01"}, "## Temas\n- 01.08.2026 · mail · selam\n")
    c.kisi_yaz("veli", {"ad": "Veli Can", "tur": "cevre", "yakinlik": 3, "son_temas": "2026-10-10"}, "")
    c.kisi_yaz("gizli", {"ad": "Gizli Kisi", "tur": "siyaset", "yakinlik": 3, "kurum": "Gizli Parti", "son_temas": "2026-09-01", "sonraki_adim": "ara", "sonraki_tarih": "2026-10-16"},
               "## Sözler\n- [ ] 2026-10-01 · ben → o · gizli söz (son: 2026-10-16)\n\n## Temas\n- 02.10.2026 · telefon · gizli temas\n")
    self.staj = hd.kaydet({"baslik": "Staj bul", "tur": "kariyer", "son_tarih": "2026-10-20", "olcut": "3 görüşme"})
    hd.ilerleme_ekle(self.staj, "Başvuru gönderildi", "2026-10-12")
    hd.kaydet({"baslik": "Bitmiş hedef", "tur": "proje", "durum": "tamam", "son_tarih": "2026-10-10"})
    hd.kaydet({"baslik": "Bırakılan hedef", "tur": "proje", "durum": "birakildi", "son_tarih": "2026-10-18"})
    hamle = lambda **k: {"hedef": self.staj, "tur": "ag", "baslik": "x", "neden_simdi": "n", "gormedigin": "g", "kim": "", "kim_uzerinden": "", "ilk_adim": "Ayşe'ye yaz",
                         "son_tarih": "", "taslak": "", "kanit": ["kisiler/ayse.md"], "guven": "orta", "sonuc": "", "sonuc_not": "", **k}
    j = {"tarih": "2026-10-12T09:00", "model": "deneme", "ozet": "özet", "hedefler": [], "sorular": [], "hamleler": [
        hamle(baslik="Ayşe üzerinden tanışma", kim="ayse", son_tarih="2026-10-16"),
        hamle(baslik="Yapılan hamle", son_tarih="2026-10-13", sonuc="yaptim", sonuc_tarih="2026-10-13"),
        hamle(baslik="Gizli kişiye hamle", kim="gizli", son_tarih="2026-10-16"),
        hamle(baslik="Tarihsiz hamle")]}
    st._yaz(j, "2026-10-12-0900.md")
    self.etk = "etkinlik:aaaaaaaaaaaa"
    ks.karar_yaz(self.etk, "katilacagim")
    ks.karar_yaz("etkinlik:bbbbbbbbbbbb", "ilgileniyorum")
    ks.karar_yaz("etkinlik:cccccccccccc", "ilgilenmiyorum")
    ks.karar_yaz("etkinlik:dddddddddddd", "katilacagim")   # önbellekte yok → tarihsiz
    with open(os.path.join(ks.KLASOR, "etkinlikler.json"), "w", encoding="utf-8") as f:
        json.dump({"tarih": "2026-10-14T10:00", "etkinlikler": [
            {"anahtar": self.etk, "ad": "Fintech Buluşması", "baslangic": "2026-10-18T18:00", "yer": "Kadıköy · İstanbul", "url": "https://x.test/e/1", "cevrimici": False, "duzenleyen": "Topluluk"},
            {"anahtar": "etkinlik:bbbbbbbbbbbb", "ad": "Geçmiş Konuşma", "baslangic": "2026-10-10T10:00", "yer": "Online", "url": "javascript:alert(1)", "cevrimici": True},
            {"anahtar": "etkinlik:cccccccccccc", "ad": "İstenmeyen", "baslangic": "2026-10-19T10:00"}]}, f)


def sok(self):
    self.kesif.stop()
    c.veri_klasoru(self.eski)
    self.d.cleanup()


class ToplayiciTest(unittest.TestCase):
    def setUp(self):
        kur(self)

    def tearDown(self):
        sok(self)

    def al(self, bas="2026-10-01", bit="2026-10-31"):
        return aj.ajanda(bas, bit, BUGUN)

    def bul(self, r, **kosul):
        return [o for o in r["ogeler"] if all(o.get(k) == v for k, v in kosul.items())]

    def test_oge_sekli(self):
        r = self.al()
        self.assertEqual(r["bugun"], "2026-10-15")
        for o in r["ogeler"]:
            self.assertIn(o["tur"], aj.TURLER)
            self.assertIn(o["durum"], aj.DURUMLAR)
            self.assertRegex(o["tarih"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(o["baslik"])
            for a in ("id", "hedef", "kisi", "alt", "ayrinti"):
                self.assertIn(a, o)
        self.assertEqual(len({o["id"] for o in r["ogeler"]}), len(r["ogeler"]), "öğe kimlikleri benzersiz olmalı")
        self.assertEqual([o["tarih"] for o in r["ogeler"]], sorted(o["tarih"] for o in r["ogeler"]))

    def test_hamle(self):
        r = self.al()
        a = self.bul(r, tur="hamle", baslik="Ayşe üzerinden tanışma")[0]
        self.assertEqual((a["tarih"], a["durum"], a["hedef"], a["kisi"]), ("2026-10-16", "yaklasan", self.staj, "ayse"))
        self.assertEqual(a["ayrinti"]["ilk_adim"], "Ayşe'ye yaz")
        self.assertEqual(a["ayrinti"]["hedef_baslik"], "Staj bul")
        y = self.bul(r, tur="hamle", baslik="Yapılan hamle")[0]
        self.assertEqual((y["tarih"], y["durum"]), ("2026-10-13", "tamam"))
        self.assertEqual(y["ayrinti"]["sonuc"], "Yaptım")
        self.assertFalse(self.bul(r, baslik="Tarihsiz hamle"), "tarihsiz hamle takvime girmez")

    def test_hedef(self):
        r = self.al()
        son = self.bul(r, tur="hedef", alt="son_tarih", hedef=self.staj)[0]
        self.assertEqual((son["tarih"], son["durum"]), ("2026-10-20", "yaklasan"))
        ilerleme = self.bul(r, tur="hedef", alt="ilerleme")[0]
        self.assertEqual((ilerleme["tarih"], ilerleme["durum"]), ("2026-10-12", "tamam"))
        self.assertIn("Başvuru gönderildi", ilerleme["baslik"])
        bitmis = [o for o in self.bul(r, tur="hedef", alt="son_tarih") if o["baslik"] == "Bitmiş hedef"][0]
        self.assertEqual(bitmis["durum"], "tamam")
        self.assertFalse([o for o in r["ogeler"] if o["baslik"] == "Bırakılan hedef"], "bırakılan hedef takvimde yok")

    def test_soz(self):
        r = self.al()
        acik = self.bul(r, tur="soz", kisi="ayse", alt="son_tarih")[0]
        self.assertEqual((acik["tarih"], acik["durum"]), ("2026-10-14", "gecikmis"))
        self.assertIn("kitabı göndermek", acik["baslik"])
        self.assertEqual(acik["ayrinti"]["yon"], "verdiğin söz")
        tamam = self.bul(r, tur="soz", alt="tamam")
        self.assertEqual(tamam, [])   # 28 Eylül ekim aralığı dışında
        r2 = self.al("2026-09-01", "2026-09-30")
        t = self.bul(r2, tur="soz", alt="tamam")[0]
        self.assertEqual((t["tarih"], t["durum"]), ("2026-09-28", "tamam"))
        self.assertFalse([o for o in r2["ogeler"] if "iptal olan" in o["baslik"]], "iptal edilen söz görünmez")
        tarihsiz = self.bul(r, tur="soz", alt="tarihsiz")[0]   # 44 gündür açık, 21 gün eşiği aşıldı → bugüne konur
        self.assertEqual((tarihsiz["tarih"], tarihsiz["durum"]), ("2026-10-15", "gecikmis"))

    def test_kisi_sonraki_adim_ve_ihmal(self):
        r = self.al()
        s = self.bul(r, tur="kisi", alt="sonraki_adim", kisi="ayse")[0]
        self.assertEqual((s["tarih"], s["durum"]), ("2026-10-17", "yaklasan"))
        self.assertEqual(s["ayrinti"]["sonraki_adim"], "Kitabı götür")
        self.assertFalse(self.bul(r, tur="kisi", alt="ihmal", kisi="ayse"), "sonraki tarihi olan kişide ihmal öğesi çıkmaz")
        veli = self.bul(r, tur="kisi", alt="ihmal", kisi="veli")[0]   # yakınlık 3: 14 gün → 10 Ekim + 14
        self.assertEqual((veli["tarih"], veli["durum"], veli["ayrinti"]["esik_gun"]), ("2026-10-24", "yaklasan", 14))
        mehmet = aj.ajanda("2026-08-01", "2026-09-30", BUGUN)
        m = [o for o in mehmet["ogeler"] if o["alt"] == "ihmal" and o["kisi"] == "mehmet"][0]   # yakınlık 2: 30 gün → 31 Ağustos, gecikmiş
        self.assertEqual((m["tarih"], m["durum"]), ("2026-08-31", "gecikmis"))

    def test_etkinlik(self):
        r = self.al()
        e = self.bul(r, tur="etkinlik", baslik="Fintech Buluşması")[0]
        self.assertEqual((e["tarih"], e["durum"]), ("2026-10-18", "yaklasan"))
        self.assertEqual(e["ayrinti"]["karar"], "katilacagim")
        self.assertEqual(e["ayrinti"]["yer"], "Kadıköy · İstanbul")
        self.assertEqual(e["ayrinti"]["saat"], "18:00")
        self.assertEqual(e["ayrinti"]["anahtar"], self.etk)
        g = self.bul(r, tur="etkinlik", baslik="Geçmiş Konuşma")[0]
        self.assertEqual(g["durum"], "tamam")
        self.assertNotIn("url", g["ayrinti"], "http(s) olmayan adres taşınmaz")
        self.assertFalse(self.bul(r, baslik="İstenmeyen"), "ilgilenmiyorum denen etkinlik görünmez")
        self.assertEqual(r["tarihsiz_etkinlik"], 1)

    def test_temas(self):
        r = self.al()
        t = self.bul(r, tur="temas", kisi="ayse")
        self.assertEqual(sorted(o["tarih"] for o in t), ["2026-10-01", "2026-10-05"])
        self.assertTrue(all(o["durum"] == "tamam" and o["alt"] == "gecmis" for o in t))
        self.assertEqual(self.bul(r, tur="temas", tarih="2026-10-05")[0]["ayrinti"]["kanal"], "whatsapp")

    def test_haric_kisi_hicbir_ogede_yok(self):
        r = aj.ajanda("2026-08-01", "2026-12-31", BUGUN)
        kaynak = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("Gizli", kaynak)
        self.assertNotIn("gizli", kaynak)
        self.assertFalse([o for o in r["ogeler"] + r["gecikmisler"] if o["kisi"] == "gizli"])

    def test_gecikmisler_aralik_oncesinden_tasinir(self):
        r = aj.ajanda("2026-10-15", "2026-10-31", BUGUN)
        idler = {o["id"] for o in r["gecikmisler"]}
        self.assertTrue(any(i.startswith("kisi:mehmet:ihmal") for i in idler))
        self.assertTrue(all(o["durum"] == "gecikmis" and o["tarih"] < "2026-10-15" for o in r["gecikmisler"]))
        self.assertEqual(r["gecikmis_toplam"], len(r["gecikmisler"]))

    def test_bos_veri_hata_vermez(self):
        with tempfile.TemporaryDirectory() as bos:
            c.veri_klasoru(os.path.join(bos, "veri"))
            with mock.patch.object(ks, "KLASOR", os.path.join(bos, "yok")):
                r = aj.ajanda("2026-10-01", "2026-10-31", BUGUN)
        self.assertEqual((r["ogeler"], r["gecikmisler"], r["tarihsiz_etkinlik"]), ([], [], 0))

    def test_haric_vekil_ve_ad_hamlede_suzulur(self):
        """haric.md sonradan genişlerse eski okumadaki vekil hamlesi ve metinde hariç kişinin adı geçen hamle görünmez."""
        with open(os.path.join(ks.KLASOR, "vekil-dizin.json"), "w", encoding="utf-8") as f:
            json.dump({"imza": "x", "veri": {"Ali Veli": {"bilgi": {"parti": "Gizli Parti"}}, "Can Su": {"bilgi": {"parti": "Açık Parti"}}}}, f)
        hamle = lambda **k: {"hedef": self.staj, "tur": "vekil", "baslik": "x", "kim": "", "ilk_adim": "", "son_tarih": "2026-10-17", "sonuc": "", "neden_simdi": "", "gormedigin": "", "kim_uzerinden": "", "taslak": "", "kanit": [], "guven": "orta", "sonuc_not": "", **k}
        st._yaz({"tarih": "2026-10-14T09:00", "model": "deneme", "ozet": "", "hedefler": [], "sorular": [], "hamleler": [
            hamle(baslik="Hariç vekil", kim="vekil:" + c.slug("Ali Veli")),
            hamle(baslik="Açık vekil", kim="vekil:" + c.slug("Can Su")),
            hamle(baslik="Bilinmeyen vekil", kim="vekil:" + c.slug("Yok Kimse")),
            hamle(baslik="Ada göre", ilk_adim="Gizli Kisi ile tanış")]}, "2026-10-14-0900.md")
        r = self.al()
        basliklar = {o["baslik"] for o in self.bul(r, tur="hamle")}
        self.assertIn("Açık vekil", basliklar)
        self.assertFalse({"Hariç vekil", "Bilinmeyen vekil", "Ada göre"} & basliklar)

    def test_kisiler_okunamazsa_hamle_gosterilmez(self):
        with mock.patch.object(c, "kisileri_oku", side_effect=OSError):
            r = self.al()
        self.assertFalse(self.bul(r, tur="hamle"))

    def test_bozuk_onbellek_ve_strateji(self):
        with open(os.path.join(ks.KLASOR, "etkinlikler.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        with open(os.path.join(st.klasor(), "2026-10-14-0900.md"), "w", encoding="utf-8") as f:
            f.write("içinde json bloğu yok")
        r = self.al()
        self.assertFalse(self.bul(r, tur="etkinlik"))
        self.assertTrue(self.bul(r, tur="hamle"), "bozuk okuma atlanır, öncekiler gelir")

    def test_ajanda_yazmaz(self):
        def goruntu():
            return sorted((os.path.join(k, f), os.path.getmtime(os.path.join(k, f))) for k, _, fs in os.walk(self.d.name) for f in fs)
        once = goruntu()
        self.al()
        self.assertEqual(goruntu(), once, "toplayıcı hiçbir dosyaya yazmamalı")


class AralikTest(unittest.TestCase):
    def test_gecerli(self):
        b, t = aj.aralik("2026-10-01", "2026-10-31", BUGUN)
        self.assertEqual((b.isoformat(), t.isoformat()), ("2026-10-01", "2026-10-31"))

    def test_varsayilan_bugunun_ayi(self):
        b, t = aj.aralik("", "", BUGUN)
        self.assertEqual((b.isoformat(), t.isoformat()), ("2026-10-01", "2026-10-31"))
        self.assertEqual(aj.aralik(None, None, date(2026, 2, 10))[1].isoformat(), "2026-02-28")

    def test_gecersiz_girdiler(self):
        for bas, bit in (("2026-10-01", ""), ("", "2026-10-31"), ("20261001", "20261031"), ("2026-13-01", "2026-13-02"), ("2026-02-30", "2026-03-01"),
                         ("01.10.2026", "31.10.2026"), ("2026-10-01", "2026-10-31; DROP"), ("x", "y"), ("2026-10-31", "2026-10-01"),
                         ("2026-W41-1", "2026-10-31"), ("2025-01-01", "2026-12-31"), ("2026-10-01 ", "2026-10-31\n2026")):
            with self.assertRaises(ValueError, msg=(bas, bit)):
                aj.aralik(bas, bit, BUGUN)

    def test_sinir(self):
        aj.aralik("2026-01-01", "2027-02-04", BUGUN)   # 399 gün
        with self.assertRaises(ValueError):
            aj.aralik("2026-01-01", "2027-03-01", BUGUN)


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class UcTest(unittest.TestCase):
    """Ayrı süreçte gerçek sunucu (geçici veri): kilit denetimi, anahtar, tarih doğrulaması, cevap şekli."""
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.TemporaryDirectory()
        cls.port = bos_port()
        cls.veri = os.path.join(cls.d.name, "veri")
        env = {**os.environ, "LOCALAPPDATA": os.path.join(cls.d.name, "la"), "AGIM_VERI": cls.veri, "PYTHONIOENCODING": "utf-8"}
        kod = ("import sys;sys.path.insert(0,%r);import ag_sunucu as s;from http.server import ThreadingHTTPServer;s.PORT=%d;"
               "ThreadingHTTPServer(('127.0.0.1',%d),s.Isleyici).serve_forever()") % (KOK, cls.port, cls.port)
        cls.p = subprocess.Popen([sys.executable, "-c", kod], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        os.makedirs(os.path.join(cls.veri, "hedefler"), exist_ok=True)
        with open(os.path.join(cls.veri, "hedefler", "deneme.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nbaslik: Deneme hedefi\ndurum: aktif\ntur: proje\nson_tarih: 2026-10-20\noncelik: 2\n---\n# Deneme hedefi\n\n## İlerleme\n")
        s, b, _ = cls.istek("POST", "/api/kilit/kur", json.dumps({"pin": "4321", "pin2": "4321"}).encode(), {"Content-Type": "application/json"})
        cls.cerez = b["set-cookie"].split(";")[0]
        _, _, sayfa = cls.istek("GET", "/", None, {"Cookie": cls.cerez})
        cls.anahtar = re.search(rb'"anahtar":\s*"([^"]+)"', sayfa).group(1).decode()

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()
        cls.p.wait()
        cls.d.cleanup()

    @classmethod
    def istek(cls, yontem, yol, govde=None, basliklar=None):
        h = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=10)
        h.putrequest(yontem, yol)
        for k, d in (basliklar or {}).items():
            h.putheader(k, d)
        if govde is not None:
            h.putheader("Content-Length", str(len(govde)))
        h.endheaders(govde)
        y = h.getresponse()
        veri = y.read()
        r = (y.status, dict((k.lower(), d) for k, d in y.getheaders()), veri)
        h.close()
        return r

    def ajanda(self, sorgu, cerez=True, anahtar=True):
        basl = {}
        if cerez:
            basl["Cookie"] = self.cerez
        if anahtar:
            basl["X-Ag-Anahtar"] = self.anahtar
        return self.istek("GET", "/api/ajanda" + sorgu, None, basl)

    def test_kilitliyken_veri_yok(self):
        kod, _, govde = self.ajanda("?bas=2026-10-01&bit=2026-10-31", cerez=False)
        self.assertEqual(kod, 401)
        self.assertNotIn(b"Deneme hedefi", govde)

    def test_anahtarsiz_reddedilir(self):
        kod, _, govde = self.ajanda("?bas=2026-10-01&bit=2026-10-31", anahtar=False)
        self.assertEqual(kod, 403)
        self.assertNotIn(b"Deneme hedefi", govde)

    def test_basarili_cevap(self):
        kod, b, govde = self.ajanda("?bas=2026-10-01&bit=2026-10-31")
        self.assertEqual(kod, 200, govde)
        self.assertIn("frame-ancestors 'none'", b.get("content-security-policy", ""))
        j = json.loads(govde)
        self.assertEqual((j["bas"], j["bit"]), ("2026-10-01", "2026-10-31"))
        self.assertTrue([o for o in j["ogeler"] if o["tur"] == "hedef" and o["tarih"] == "2026-10-20" and o["hedef"] == "deneme"])
        self.assertTrue({"ogeler", "gecikmisler", "gecikmis_toplam", "tarihsiz_etkinlik", "bugun"} <= set(j))

    def test_tarih_girdisi_dogrulanir(self):
        for sorgu in ("?bas=2026-10-01", "?bas=abc&bit=2026-10-31", "?bas=2026-10-31&bit=2026-10-01", "?bas=2020-01-01&bit=2026-12-31",
                      "?bas=2026-10-01&bit=2026-10-31%27%3B--", "?bas=20261001&bit=20261031"):
            kod, _, govde = self.ajanda(sorgu)
            self.assertEqual(kod, 400, (sorgu, govde))
            self.assertIn("hata", json.loads(govde))

    def test_yazan_yontem_yok(self):
        kod, _, _ = self.istek("POST", "/api/ajanda", b"{}", {"Content-Type": "application/json", "Cookie": self.cerez, "X-Ag-Anahtar": self.anahtar})
        self.assertIn(kod, (403, 404, 405))


if __name__ == "__main__":
    unittest.main()
