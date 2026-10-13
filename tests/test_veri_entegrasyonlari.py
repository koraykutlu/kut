"""Veri entegrasyonları testleri: takvim (.ics), LinkedIn CSV, ders listesi yapıştırma. Yalnız kurgusal veri; ağ ve model yok."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import io
import json
import os
import sys
import tempfile
import time
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_cekirdek as c  # noqa: E402
import ag_ders_yapistir as dy  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_ice_ortak as ort  # noqa: E402
import ag_kaynak as kn  # noqa: E402
import ag_linkedin as li  # noqa: E402
import ag_sunucu as sunucu  # noqa: E402
import ag_takvim as tk  # noqa: E402


def zip_yap(dosyalar):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for ad, veri in dosyalar.items():
            z.writestr(ad, veri)
    return b.getvalue()


def olay(uid, bas, ozet="Haftalık görüşme", kisiler=(), ek=(), organizer=None):
    s = ["BEGIN:VEVENT", f"UID:{uid}", bas, f"SUMMARY:{ozet}", "DESCRIPTION:GIZLI-ACIKLAMA-123", "LOCATION:GIZLI-KONUM-456"]
    if organizer:
        s.append(f"ORGANIZER;CN={organizer[0]}:mailto:{organizer[1]}")
    for ad, eposta, *d in kisiler:
        durum = d[0] if d else "ACCEPTED"
        cn = f'CN="{ad}";' if ad else ""
        s.append(f"ATTENDEE;{cn}PARTSTAT={durum}:mailto:{eposta}")
    s += list(ek) + ["BEGIN:VALARM", "TRIGGER:-PT10M", "ATTENDEE:mailto:alarm@ornek.test", "END:VALARM", "END:VEVENT"]
    return "\r\n".join(s)


def takvim(*olaylar, ad="ben@ornek.test"):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-CALNAME:" + ad + "\r\n" + "\r\n".join(olaylar) + "\r\nEND:VCALENDAR\r\n").encode("utf-8")


BEN = ("Kerem Test", "ben@ornek.test")
ADA = ("Deneme, Ada", "ada.deneme@ornek.test")
DENIZ = ("Deniz Örnek", "deniz@ornek.test")
EYLUL = ("Eylül Kurgu", "eylul.kurgu@ornek.test")


class Taban(unittest.TestCase):
    def setUp(self):
        ort._bekleyen.clear()
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.eski = (c.VERI, ia.AYARLAR)
        ia.AYARLAR = os.path.join(t, "ayarlar.json")
        c.veri_klasoru(os.path.join(t, "ag-veri"))
        c.ben_yaz({"ad": "Kerem Test"})
        with open(ia.AYARLAR, "w", encoding="utf-8") as f:
            json.dump({"ben_adlari": ["Kerem Test"]}, f)
        self.kisi_ac("ada-deneme", "Ada Deneme", aliases=["Ada D."])
        self.kisi_ac("deniz-ornek", "Deniz Örnek", eposta="deniz@ornek.test")

    def tearDown(self):
        c.VERI, ia.AYARLAR = self.eski
        c.veri_klasoru(self.eski[0])
        self.tmp.cleanup()

    def kisi_ac(self, kid, ad, **alan):
        a = {"ad": ad, "foto": "", "tur": "cevre", "yakinlik": "1"}
        a.update(alan)
        c.kisi_yaz(kid, a, c.yeni_govde(ad, "deneme"))

    def kisi(self, kid):
        return c.kisi_oku(os.path.join(c.KISILER, kid + ".md"))

    def dosyalar(self):
        s = {}
        for d, _, adlar in os.walk(c.VERI):
            for ad in adlar:
                with open(os.path.join(d, ad), "rb") as f:
                    s[os.path.join(d, ad)] = f.read()
        return s

    def tum_metin(self):
        return "\n".join(v.decode("utf-8", "replace") for v in self.dosyalar().values())


# ================= takvim =================
class TakvimTest(Taban):
    def test_satir_katlama_ve_kacis(self):
        metin = "BEGIN:VEVENT\r\nSUMMARY:Uzun baslik\r\n  devam eder\\, virgullu\r\nDTSTART:20250310T090000\r\nEND:VEVENT\r\n"
        ham, _ = tk.olaylari_oku("BEGIN:VCALENDAR\r\n" + metin + "END:VCALENDAR")
        o = tk.olay_coz(ham[0])
        self.assertEqual(o["baslik"], "Uzun baslik devam eder, virgullu")

    def test_zaman_bicimleri(self):
        d, tum = tk.zaman_coz("20250310", {"VALUE": "DATE"})
        self.assertEqual((str(d), tum), ("2025-03-10", True))
        d, tum = tk.zaman_coz("20250310T093000", {"TZID": "Europe/Istanbul"})   # duvar saati: zoneinfo gerekmez
        self.assertEqual((d.isoformat(), tum), ("2025-03-10T09:30:00", False))
        d, _ = tk.zaman_coz("20250310T120000Z", {})   # UTC: sistem saatine çevrilir, tarih en çok bir gün oynar
        self.assertIn(str(d.date()), ("2025-03-10", "2025-03-11"))

    def test_ozellik_tirnakli_cn_iki_nokta_ve_virgul(self):
        adi, p, v = tk.ozellik_coz('ATTENDEE;CN="Deneme, Ada: Dr";PARTSTAT=ACCEPTED:mailto:ada@ornek.test')
        self.assertEqual((adi, p["CN"], v), ("ATTENDEE", "Deneme, Ada: Dr", "mailto:ada@ornek.test"))

    def test_rrule_haftalik_exdate_gecmis(self):
        ham, _ = tk.olaylari_oku(takvim(olay("seri", "DTSTART:20250107T100000", kisiler=[BEN, ADA],
                                              ek=["RRULE:FREQ=WEEKLY;BYDAY=TU;COUNT=4", "EXDATE:20250114T100000"])).decode())
        ol, ist = tk.olaylari_ac(ham)
        self.assertEqual(sorted(str(o["tarih"]) for o in ol), ["2025-01-07", "2025-01-21", "2025-01-28"])
        self.assertEqual(ist["tekrar_acilan"], 2)

    def test_rrule_gelecek_uretilmez_ve_ust_sinir(self):
        # sonsuz günlük seri: yalnız geçmiş, en çok TEKRAR_AZAMI
        ham, _ = tk.olaylari_oku(takvim(olay("gunluk", "DTSTART:20240101T090000", kisiler=[BEN, ADA], ek=["RRULE:FREQ=DAILY"])).decode())
        simdi = tk.datetime(2025, 6, 1, 12, 0)
        ol, _ = tk.olaylari_ac(ham, simdi)
        self.assertEqual(len(ol), tk.TEKRAR_AZAMI)
        self.assertEqual(max(o["tarih"] for o in ol).isoformat(), "2025-06-01")
        self.assertTrue(all(o["tarih"] <= simdi.date() for o in ol))

    def test_rrule_aylik_sira_ve_yillik(self):
        ham, _ = tk.olaylari_oku(takvim(
            olay("ay", "DTSTART:20250101T100000", kisiler=[BEN, ADA], ek=["RRULE:FREQ=MONTHLY;BYDAY=2TU;COUNT=3"]),
            olay("yil", "DTSTART;VALUE=DATE:20230215", kisiler=[BEN, DENIZ], ek=["RRULE:FREQ=YEARLY"])).decode())
        ol, _ = tk.olaylari_ac(ham, tk.datetime(2025, 12, 31))
        ay = sorted(str(o["tarih"]) for o in ol if o["uid"] == "ay")
        self.assertEqual(ay, ["2025-01-14", "2025-02-11", "2025-03-11"])
        yil = sorted(str(o["tarih"]) for o in ol if o["uid"] == "yil")
        self.assertEqual(yil, ["2023-02-15", "2024-02-15", "2025-02-15"])

    def test_recurrence_id_gecersiz_kilar_ve_iptal(self):
        ham, _ = tk.olaylari_oku(takvim(
            olay("seri", "DTSTART:20250107T100000", kisiler=[BEN, ADA], ek=["RRULE:FREQ=WEEKLY;COUNT=3"]),
            olay("seri", "DTSTART:20250115T100000", ozet="Kaydırılan", kisiler=[BEN, ADA], ek=["RECURRENCE-ID:20250114T100000"]),
            olay("iptal", "DTSTART:20250201T100000", kisiler=[BEN, ADA], ek=["STATUS:CANCELLED"])).decode())
        ol, ist = tk.olaylari_ac(ham, tk.datetime(2025, 12, 31))
        self.assertEqual(sorted(str(o["tarih"]) for o in ol), ["2025-01-07", "2025-01-15", "2025-01-21"])
        self.assertEqual(ist["iptal"], 1)

    def test_uid_ve_tarih_tekrar_sayilmaz(self):
        ham, _ = tk.olaylari_oku(takvim(olay("ayni", "DTSTART:20250310T100000", kisiler=[BEN, ADA]),
                                        olay("ayni", "DTSTART:20250310T100000", kisiler=[BEN, ADA])).decode())
        ol, _ = tk.olaylari_ac(ham, tk.datetime(2025, 12, 31))
        self.assertEqual(len(ol), 1)

    def prova(self, ics=None, **secenek):
        ics = ics or takvim(
            olay("u1", "DTSTART;TZID=Europe/Istanbul:20250310T100000", ozet="Proje gözden geçirme", kisiler=[BEN, ADA, DENIZ], organizer=BEN),
            olay("u2", "DTSTART;VALUE=DATE:20250320", ozet="Atölye", kisiler=[BEN, ADA]),
            olay("u3", "DTSTART:20250402T080000Z", ozet="Doktor randevusu", kisiler=[BEN, EYLUL]),
            olay("u4", "DTSTART:20250405T080000Z", ozet="Tanışma", kisiler=[BEN, EYLUL, ("", "bilinmeyen@ornek.test")]),
            olay("u5", "DTSTART:20990101T080000Z", ozet="Gelecek", kisiler=[BEN, ADA]),
            olay("u6", "DTSTART:20250411T080000Z", ozet="Reddettim", kisiler=[("Kerem Test", "ben@ornek.test", "DECLINED"), ADA]))
        return tk.onizle("takvim.ics", ics, secenek)

    def test_onizleme_yazmaz_sayar_ve_kendini_cikarir(self):
        once = self.dosyalar()
        r = self.prova()
        self.assertEqual(self.dosyalar(), once)   # hiçbir dosya (kişi, çıkarım, ayar) değişmedi
        o = r["ozet"]
        self.assertEqual((o["etkinlik"], o["kisi_eslesen"], o["yeni_oneri"]), (4, 2, 2))   # u1,u2,u3,u4; gelecek ve reddedilen sayılmaz
        self.assertEqual(o["gelecek_atlanan"], 1)
        self.assertNotIn("ben@ornek.test", json.dumps(r["yeni"]))   # kendi adresin öneri olmaz
        ids = {e["id"]: e for e in r["eslesenler"]}
        self.assertEqual(ids["ada-deneme"]["n"], 2)       # ad + alias eşleşmesi ("Deneme, Ada" ≈ "Ada Deneme")
        self.assertEqual(ids["deniz-ornek"]["n"], 1)      # e-posta eşleşmesi
        self.assertIn("ben@ornek.test", r["ben"]["eposta"])

    def test_aciklama_ve_konum_hic_alinmaz(self):
        r = self.prova(baslik=True)
        tk.uygula(r["token"], {"yeni": [{"k": y["k"], "ad": y["ad"]} for y in r["yeni"]]})
        self.assertNotIn("GIZLI-ACIKLAMA", self.tum_metin())
        self.assertNotIn("GIZLI-KONUM", self.tum_metin())
        self.assertNotIn("alarm@ornek.test", json.dumps(r) + self.tum_metin())   # VALARM içi özellikler okunmaz

    def test_baslik_varsayilan_kapali_ve_hassas(self):
        r = self.prova()
        self.assertFalse(r["ozet"]["baslik"])
        tk.uygula(r["token"], {})
        temas = c.bolum_oku(self.kisi("ada-deneme")["govde"], "Temas")
        self.assertIn("10.03.2025 · takvim · toplantı", temas)
        self.assertNotIn("Proje gözden geçirme", self.tum_metin())
        # açık: kısaltılır; sağlık gibi hassas konu yine "toplantı"
        self.assertEqual(tk.baslik_kisalt("Doktor randevusu"), "toplantı")
        self.assertEqual(tk.baslik_kisalt("Maaş görüşmesi"), "toplantı")
        self.assertEqual(tk.baslik_kisalt("Proje gözden geçirme"), "Proje gözden geçirme")
        uzun = tk.baslik_kisalt("Çok uzun bir toplantı başlığı https://meet.ornek.test/abc ve devamı burada " * 2)
        self.assertLessEqual(len(uzun), tk.BASLIK_AZAMI + 1)
        self.assertNotIn("https", uzun)

    def test_baslik_acikken_kisaltilmis_baslik_yazilir(self):
        r = self.prova(baslik=True)
        self.assertTrue(r["ozet"]["baslik"])
        tk.uygula(r["token"], {"baslik": True})
        self.assertIn("10.03.2025 · takvim · Proje gözden geçirme", c.bolum_oku(self.kisi("deniz-ornek")["govde"], "Temas"))
        self.assertTrue(ia.ayarlar()["takvim_baslik"])   # tercih hatırlanır
        self.assertTrue(tk.onizle("t.ics", takvim(olay("x", "DTSTART:20250310T100000", kisiler=[BEN, DENIZ])), {})["ozet"]["baslik"])

    def test_buyuk_toplanti_sinyal_degil(self):
        buyuk = [(f"Kisi {i}", f"k{i}@ornek.test") for i in range(18)]
        ics = takvim(olay("b1", "DTSTART:20250310T100000", ozet="Tüm şirket", kisiler=[BEN, ADA] + buyuk),
                     olay("b2", "DTSTART:20250311T100000", ozet="Küçük", kisiler=[BEN, DENIZ]))
        r = tk.onizle("t.ics", ics, {})
        self.assertEqual((r["ozet"]["buyuk_atlanan"], r["ozet"]["etkinlik"], r["ozet"]["yeni_oneri"]), (1, 1, 0))
        self.assertEqual([e["id"] for e in r["eslesenler"]], ["deniz-ornek"])
        r = tk.onizle("t.ics", ics, {"buyuk_dahil": True})   # isteğe bağlı: sayılır
        self.assertEqual((r["ozet"]["buyuk_atlanan"], r["ozet"]["etkinlik"]), (0, 2))
        r = tk.onizle("t.ics", ics, {"buyuk_esik": 30})
        self.assertEqual(r["ozet"]["buyuk_atlanan"], 0)

    def test_uygula_idempotent_son_temas_ileri_ve_yeni_kisi_secimli(self):
        c.kisi_yaz("ada-deneme", {**self.kisi("ada-deneme"), "son_temas": "2025-12-01"}, c.yeni_govde("Ada Deneme", "deneme"))
        r = self.prova()
        self.assertEqual(len(c.kisileri_oku()), 2)
        s1 = tk.uygula(r["token"], {})
        self.assertEqual(s1["yeni"], [])                  # seçilmeyen yeni kişi eklenmez (doğrudan eklenmez)
        self.assertEqual(len(c.kisileri_oku()), 2)
        self.assertEqual(self.kisi("ada-deneme")["son_temas"], "2025-12-01")   # yalnız ileri: geriye gitmedi
        self.assertEqual(self.kisi("deniz-ornek")["son_temas"], "2025-03-10")
        ilk = self.kisi("ada-deneme")["govde"]
        s2 = tk.uygula(r["token"], {})
        self.assertEqual((s2["satir"], self.kisi("ada-deneme")["govde"]), (0, ilk))   # ikinci yükleme hiçbir şey yazmaz
        # aynı dosyayı yeniden önizle + uygula: yine yazılacak satır yok
        self.assertEqual(self.prova()["ozet"]["temas_satiri"], 0)
        # seçimli yeni kişi
        r = self.prova()
        eylul = next(y for y in r["yeni"] if y["eposta"] == "eylul.kurgu@ornek.test")
        self.assertEqual(eylul["n"], 2)
        s3 = tk.uygula(r["token"], {"yeni": [{"k": eylul["k"], "ad": "Eylül Kurgu"}]})
        self.assertEqual(len(s3["yeni"]), 1)
        k = self.kisi(s3["yeni"][0])
        self.assertEqual((k["yakinlik"], k["tur"], k["eposta"], k["son_temas"]), ("0", "cevre", "eylul.kurgu@ornek.test", "2025-04-05"))
        self.assertEqual(k["govde"].count(" · takvim · "), 2)
        tk.uygula(r["token"], {"yeni": [{"k": eylul["k"], "ad": "Eylül Kurgu"}]})   # tekrar: ikinci dosya/satır açılmaz
        self.assertEqual(len([x for x in c.kisileri_oku() if x["ad"] == "Eylül Kurgu"]), 1)
        self.assertEqual(self.kisi(s3["yeni"][0])["govde"].count(" · takvim · "), 2)

    def test_ad_eslesmesi_eposta_onerisi_dogrulaya_duser(self):
        r = self.prova()
        self.assertEqual(r["ozet"]["eposta_onerisi"], 1)   # Ada'nın e-postası yok, ad eşleşti → öneri
        self.assertNotIn("eposta", self.kisi("ada-deneme"))
        tk.uygula(r["token"], {})
        self.assertNotIn("ada.deneme@ornek.test", self.kisi("ada-deneme").get("eposta", ""))   # doğrudan yazılmaz
        sor = [x for x in c.cikarimlari_oku() if x["alan"] == "eposta" and x["kisi"] == "ada-deneme"]
        self.assertEqual((len(sor), sor[0]["deger"], sor[0]["durum"]), (1, "ada.deneme@ornek.test", "bekliyor"))

    def test_kendi_adresi_ayardan_ve_otomatik(self):
        # X-WR-CALNAME yok; ayarda da yok: her toplantıda görünen tek adres kendin sayılır
        olaylar = [olay(f"o{i}", f"DTSTART:2025030{i}T100000", kisiler=[BEN, [ADA, DENIZ, EYLUL][i % 3]]) for i in range(1, 7)]
        ics = takvim(*olaylar, ad="Takvimim")
        r = tk.onizle("t.ics", ics, {})
        self.assertIn("ben@ornek.test", r["ben"]["otomatik"])
        self.assertNotIn("ben@ornek.test", json.dumps(r["yeni"]))
        # tek karşıdaki kişiyle yapılan 1:1 ağırlıklı takvimde belirsizse kimseyi 'ben' sayma, uyar
        olaylar = [olay(f"p{i}", f"DTSTART:2025030{i}T100000", kisiler=[BEN, ADA]) for i in range(1, 7)]
        r = tk.onizle("t.ics", takvim(*olaylar, ad="Takvimim"), {})
        self.assertEqual(r["ben"]["otomatik"], [])
        self.assertTrue(any("ayırt edemedim" in u for u in r["uyari"]))
        r = tk.onizle("t.ics", takvim(*olaylar, ad="Takvimim"), {"ben": ["ben@ornek.test"]})   # yazılan adres
        self.assertEqual(r["ozet"]["kisi_eslesen"], 1)
        tk.uygula(r["token"], {})
        self.assertIn("ben@ornek.test", ia.ayarlar()["ben_epostalari"])

    def test_takvim_adi_e_posta_ise_kendin_sayilir(self):
        olaylar = [olay(f"p{i}", f"DTSTART:2025030{i}T100000", kisiler=[BEN, ADA]) for i in range(1, 7)]
        r = tk.onizle("t.ics", takvim(*olaylar), {})   # X-WR-CALNAME: ben@ornek.test; 1:1 ağırlıklı olsa da belirsizlik uyarısı çıkmaz
        self.assertEqual(r["ben"]["otomatik"], ["ben@ornek.test"])
        self.assertEqual(r["uyari"], [])
        self.assertEqual(r["ozet"]["kisi_eslesen"], 1)

    def test_zip_icinde_ics(self):
        z = zip_yap({"Takvim/ben@ornek.test.ics": takvim(olay("z1", "DTSTART:20250310T100000", kisiler=[BEN, DENIZ])), "Takvim/not.txt": b"x"})
        r = tk.onizle("takeout.zip", z, {})
        self.assertEqual(r["ozet"]["kisi_eslesen"], 1)
        with self.assertRaises(ValueError):
            tk.onizle("bos.zip", zip_yap({"a.txt": b"x"}), {})

    def test_zip_guvenligi_ve_gecersiz_dosya(self):
        with self.assertRaises(ValueError):
            tk.onizle("bomba.zip", zip_yap({"x.ics": b"0" * 40_000_000}), {})   # oran > 200
        with self.assertRaises(ValueError):
            tk.onizle("kotu.zip", zip_yap({"../x.ics": b"BEGIN:VCALENDAR"}), {})
        with self.assertRaises(ValueError):
            tk.onizle("a.ics", b"merhaba dunya", {})
        with self.assertRaises(ValueError):
            tk.onizle("a.ics", b"0" * (tk.DOSYA_AZAMI + 1), {})

    def test_kaynak_degil_adresler_atlanir(self):
        ics = takvim(olay("r", "DTSTART:20250310T100000", kisiler=[BEN, DENIZ, ("Oda 1", "x@resource.calendar.google.com"),
                                                                 ("", "noreply@ornek.test")]))
        r = tk.onizle("t.ics", ics, {})
        self.assertEqual(r["ozet"]["yeni_oneri"], 0)

    def test_sure_dolunca_belirtec_gecersiz(self):
        r = self.prova()
        ort._bekleyen[r["token"]] = (ort._bekleyen[r["token"]][0], time.time() - 99999, ort._bekleyen[r["token"]][2])
        with self.assertRaises(ValueError):
            tk.uygula(r["token"], {})
        with self.assertRaises(ValueError):
            tk.uygula("uydurma", {})
        r = self.prova()
        with self.assertRaises(ValueError):
            li.uygula(r["token"], {})   # başka türün belirteci kabul edilmez


# ================= LinkedIn =================
BAGLANTI_CSV = (
    "Notes:\n\"When exporting your connection data, you may notice that some of the email addresses are missing due to the privacy settings of "
    "your connections.\"\n\nFirst Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    "Ada,Deneme MBA,https://www.linkedin.com/in/ada-deneme-123,,Örnek Anonim A.Ş.,Ürün Yöneticisi,12 Mar 2024\n"
    "Deniz,Örnek,https://tr.linkedin.com/in/deniz-ornek/?trk=x,deniz@ornek.test,Kurgu Ltd.,Mühendis,05 Jan 2023\n"
    "Fatma,Kurgu 🚀,https://www.linkedin.com/in/fatma-kurgu,,\"Test, Şirketi\",\"Kıdemli, Uzman\",2022-07-30\n"
    "Gül,Deneme,,,,,\n"
)
MESAJ_CSV = (
    "CONVERSATION ID,CONVERSATION TITLE,FROM,SENDER PROFILE URL,TO,RECIPIENT PROFILE URLS,DATE,SUBJECT,CONTENT,FOLDER\n"
    "c1,,Fatma Kurgu,https://www.linkedin.com/in/fatma-kurgu,Kerem Test,https://www.linkedin.com/in/kerem-test,2024-05-02 10:11:12 UTC,,SIRKI-MESAJ-ICERIGI-XYZ,INBOX\n"
    "c1,,Kerem Test,https://www.linkedin.com/in/kerem-test,Fatma Kurgu,https://www.linkedin.com/in/fatma-kurgu,2024-05-02 11:00:00 UTC,,\"baska gizli, satir\nuzun icerik\",SENT\n"
    "c1,,Fatma Kurgu,https://www.linkedin.com/in/fatma-kurgu,Kerem Test,https://www.linkedin.com/in/kerem-test,2024-06-09 09:00:00 UTC,,icerik uc,INBOX\n"
    "c2,,Ada Deneme,https://www.linkedin.com/in/ada-deneme-123,Kerem Test,https://www.linkedin.com/in/kerem-test,2024-07-01 09:00:00 UTC,,gizli-d,INBOX\n"
    "c3,Grup,Ada Deneme,https://www.linkedin.com/in/ada-deneme-123,\"Kerem Test, Deniz Örnek\","
    "https://www.linkedin.com/in/kerem-test https://www.linkedin.com/in/deniz-ornek,2024-07-02 09:00:00 UTC,,GRUP-ICERIK,INBOX\n"
)


class LinkedinTest(Taban):
    def setUp(self):
        super().setUp()
        c.kisi_yaz("ada-deneme", {**self.kisi("ada-deneme"), "kurum": "", "linkedin": ""}, c.yeni_govde("Ada Deneme", "deneme"))

    def test_notes_basligi_eksik_sutun_ve_varyantlar(self):
        b = li.baglantilari_oku(BAGLANTI_CSV)
        self.assertEqual([x["ad"] for x in b], ["Ada Deneme", "Deniz Örnek", "Fatma Kurgu", "Gül Deneme"])   # MBA, emoji temizlendi
        self.assertEqual(b[2]["kurum"], "Test, Şirketi")
        self.assertEqual(b[1]["eposta"], "deniz@ornek.test")
        # eksik sütunlar (Email/Company/Position/Connected On yok) ve Türkçe başlık
        tr = "Ad,Soyadı,URL\nAda,Deneme,https://www.linkedin.com/in/ada-deneme-123\n"
        self.assertEqual(li.baglantilari_oku(tr)[0]["url"], "https://www.linkedin.com/in/ada-deneme-123")
        tr2 = "Ad,Soyadı,E-posta Adresi,Şirket,Pozisyon,Bağlantı Tarihi\nDeniz,Örnek,d@ornek.test,Kurgu,Dev,12 Mar 2024\n"
        self.assertEqual(li.baglantilari_oku(tr2)[0]["kurum"], "Kurgu")
        with self.assertRaises(ValueError):
            li.baglantilari_oku("a,b,c\n1,2,3\n")

    def test_baglanti_tarihi(self):
        self.assertEqual(str(li.baglanti_tarihi("12 Mar 2024")), "2024-03-12")
        self.assertEqual(str(li.baglanti_tarihi("Mar 12, 2024")), "2024-03-12")
        self.assertEqual(str(li.baglanti_tarihi("2022-07-30")), "2022-07-30")
        self.assertEqual(str(li.baglanti_tarihi("25/12/2024")), "2024-12-25")
        self.assertIsNone(li.baglanti_tarihi("03/04/2024"))   # belirsiz: uydurma yok

    def prova(self, **kw):
        return li.onizle([("Connections.csv", BAGLANTI_CSV.encode()), ("messages.csv", MESAJ_CSV.encode())], **kw)

    def test_onizleme_yazmaz_ve_mesaj_icerigi_alinmaz(self):
        once = self.dosyalar()
        r = self.prova()
        self.assertEqual(self.dosyalar(), once)
        d = json.dumps(r, ensure_ascii=False)
        for gizli in ("SIRKI-MESAJ", "gizli", "GRUP-ICERIK", "icerik uc"):
            self.assertNotIn(gizli, d)
        o = r["ozet"]
        self.assertEqual((o["baglanti"], o["kisi_eslesen"], o["yeni_oneri"]), (4, 2, 2))   # Ada + Deniz eşleşti; Fatma, Gül yeni
        ada = next(e for e in r["eslesenler"] if e["id"] == "ada-deneme")
        self.assertEqual(ada["alan"], {"linkedin": "https://www.linkedin.com/in/ada-deneme-123", "kurum": "Örnek Anonim A.Ş.", "rol": "Ürün Yöneticisi"})
        deniz = next(e for e in r["eslesenler"] if e["id"] == "deniz-ornek")
        self.assertEqual(deniz["alan"].get("linkedin"), "https://tr.linkedin.com/in/deniz-ornek/?trk=x")   # linkedin boştu → öneri; kurum/rol da
        self.assertTrue(any("grup sohbeti" in u for u in r["uyari"]))   # üç kişilik sohbet temas sayılmadı

    def test_uygula_alanlar_dogrulaya_temas_yazilir_yeni_secimli(self):
        r = self.prova()
        s = li.uygula(r["token"], {})
        self.assertEqual(s["yeni"], [])
        ada = self.kisi("ada-deneme")
        self.assertEqual(ada.get("linkedin", ""), "")                    # boş alan doğrudan doldurulmaz
        self.assertEqual(ada.get("kurum", ""), "")
        q = {(x["kisi"], x["alan"]): x for x in c.cikarimlari_oku() if x["durum"] == "bekliyor"}
        self.assertIn(("ada-deneme", "kurum"), q)                        # Doğrula'ya düştü
        self.assertEqual(q[("ada-deneme", "linkedin")]["deger"], "https://www.linkedin.com/in/ada-deneme-123")
        temas = c.bolum_oku(ada["govde"], "Temas")
        self.assertIn("01.07.2024 · linkedin · mesajlaşma", temas)       # mesaj üst verisi → temas
        self.assertEqual(ada["son_temas"], "2024-07-01")
        self.assertIn("bağlantı tarihi 12.03.2024", c.bolum_oku(ada["govde"], "Kaynaklar"))
        self.assertIn("linkedin", c.liste_yap(ada["nereden"]))
        # yeni bağlantı yalnız seçilince, yakınlık 0, tür tahmini yok
        fatma = next(y for y in r["yeni"] if y["ad"] == "Fatma Kurgu")
        self.assertEqual(fatma["mesaj_gun"], 2)
        s = li.uygula(r["token"], {"eslesen": False, "yeni": [{"k": fatma["k"], "ad": "Fatma Kurgu"}]})
        k = self.kisi(s["yeni"][0])
        self.assertEqual((k["yakinlik"], k["tur"], k["kurum"], k["rol"], k["son_temas"]), ("0", "cevre", "Test, Şirketi", "Kıdemli, Uzman", "2024-06-09"))
        self.assertEqual(k["linkedin"], "https://www.linkedin.com/in/fatma-kurgu")
        self.assertIn("bağlantı tarihi 30.07.2022", c.bolum_oku(k["govde"], "Kaynaklar"))
        self.assertEqual(c.bolum_oku(k["govde"], "Temas").count(" · linkedin · "), 2)
        for gizli in ("SIRKI-MESAJ", "baska gizli", "GRUP-ICERIK"):
            self.assertNotIn(gizli, self.tum_metin())

    def test_idempotent(self):
        r = self.prova()
        fatma = next(y for y in r["yeni"] if y["ad"] == "Fatma Kurgu")
        sec = {"yeni": [{"k": fatma["k"], "ad": fatma["ad"]}]}
        li.uygula(r["token"], sec)
        once = self.dosyalar()
        li.uygula(r["token"], sec)
        self.assertEqual(self.dosyalar(), once)
        r2 = self.prova()
        self.assertEqual(r2["ozet"]["temas_satiri"], 0)
        self.assertEqual(r2["ozet"]["yeni_oneri"], 1)   # Fatma artık ağda (linkedin adresiyle eşleşir): yalnız Gül kaldı

    def test_zip_yalniz_iki_dosya_acilir(self):
        z = zip_yap({"Connections.csv": BAGLANTI_CSV, "messages.csv": MESAJ_CSV, "Profile.csv": "First Name,Last Name\nGizli,Kisi\n",
                     "Positions.csv": "Company Name\nX\n"})
        r = li.onizle([("Complete_LinkedInDataExport.zip", z)])
        self.assertEqual(r["ozet"]["baglanti"], 4)
        self.assertEqual(r["ozet"]["mesaj_sohbet"], 3)
        self.assertNotIn("Gizli", json.dumps(r))
        with self.assertRaises(ValueError):
            li.onizle([("bos.zip", zip_yap({"Profile.csv": "a"}))])
        with self.assertRaises(ValueError):
            li.onizle([("kotu.zip", zip_yap({"../Connections.csv": BAGLANTI_CSV}))])
        with self.assertRaises(ValueError):
            li.onizle([("bomba.zip", zip_yap({"Connections.csv": b"0" * 40_000_000}))])

    def test_ben_adi_yoksa_mesaj_sayilmaz_uyarir(self):
        with open(ia.AYARLAR, "w", encoding="utf-8") as f:
            json.dump({"ben_adlari": ["Baska Biri"]}, f)
        c.ben_yaz({"ad": "Baska Biri"})
        r = li.onizle([("messages.csv", MESAJ_CSV.encode())])
        # üç sohbette de Kerem Test geçiyor → ≥%90 kuralıyla otomatik 'ben'
        self.assertTrue(any("Kerem Test" in u for u in r["uyari"]))

    def test_binlerce_baglanti_hizli(self):
        satirlar = ["First Name,Last Name,URL,Email Address,Company,Position,Connected On"]
        harf = lambda n: "".join(chr(97 + (n // 26 ** j) % 26) for j in range(3))   # rakamsız, benzersiz kurgusal adlar
        for i in range(4000):
            satirlar.append(f"Kurgu{harf(i % 300)},Kisi{harf(i)},https://www.linkedin.com/in/kurgu-kisi-{i},,Sirket {i % 50},Rol,12 Mar 2024")
        for i in range(300):
            self.kisi_ac(f"mevcut-{i}", f"Mevcut Adam{harf(i)}")
        t = time.time()
        r = li.onizle([("Connections.csv", "\n".join(satirlar).encode())])
        self.assertLess(time.time() - t, 20)
        self.assertEqual(r["ozet"]["yeni_oneri"], 4000)
        t = time.time()
        s = li.uygula(r["token"], {"eslesen": False, "yeni": [{"k": y["k"], "ad": y["ad"]} for y in r["yeni"][:1500]]})
        self.assertEqual(len(s["yeni"]), 1500)
        self.assertLess(time.time() - t, 60)


# ================= ders listesi =================
YAPISTIR = """ISE 424 Sistem Analizi · Dr. Dilara Tuna Örnek
ISE 426-1\tVeri Madenciliği\tProf. Dr. Ali Veli / Doç. Dr. Ayşe Kaya\tPzt 10:00-12:00
MATH 101
Calculus I
ÖĞR. GÖR. DR. CEM ÖRNEK
ISE 430 - Bilgi Sistemleri - Dr. Öğr. Üyesi Deniz Test
ISE 440 Proje Yönetimi Arş. Gör. Eda Deneme
ISE 450  Staj  Mehmet Yılmaz  Salon 3
Mart 2026 programı
"""


class DersYapistirTest(Taban):
    def test_unvan_ayiklama(self):
        for ham, unvan, ad in [("Prof. Dr. Ali Veli", "Prof. Dr.", "Ali Veli"), ("Doç. Dr. Ayşe Kaya", "Doç. Dr.", "Ayşe Kaya"),
                               ("Dr. Öğr. Üyesi Deniz Test", "Dr. Öğr. Üyesi", "Deniz Test"), ("Öğr. Gör. Eda Deneme", "Öğr. Gör.", "Eda Deneme"),
                               ("Arş. Gör. Dr. Cem Örnek", "Arş. Gör. Dr.", "Cem Örnek"), ("Hoca: Dr. Ali Veli", "Dr.", "Ali Veli")]:
            self.assertEqual(dy.unvan_ayir(ham), (unvan, ad), ham)
        self.assertEqual(dy.unvan_ayir("Ali Veli"), ("", "Ali Veli"))

    def test_cesitli_bicimler(self):
        s = dy.ayikla(YAPISTIR)
        d = {x["k"]: x for x in s["dersler"]}
        self.assertEqual(list(d), ["ISE 424", "ISE 426-1", "MATH 101", "ISE 430", "ISE 440", "ISE 450"])
        adlar = lambda k: [h["ad"] for h in d[k]["hocalar"]]
        self.assertEqual(adlar("ISE 424"), ["Dilara Tuna Örnek"])                       # '·' ayracı
        self.assertEqual(d["ISE 424"]["ad"], "Sistem Analizi")
        self.assertEqual(adlar("ISE 426-1"), ["Ali Veli", "Ayşe Kaya"])                # sekme + '/' ile iki hoca; saat atlandı
        self.assertEqual((d["ISE 426-1"]["kod"], d["ISE 426-1"]["sube"]), ("ISE 426", "1"))
        self.assertEqual((d["MATH 101"]["ad"], adlar("MATH 101")), ("Calculus I", ["Cem Örnek"]))   # satır satır, BÜYÜK HARF düzeltildi
        self.assertEqual(adlar("ISE 430"), ["Deniz Test"])                             # ' - ' ayracı
        self.assertEqual(adlar("ISE 440"), ["Eda Deneme"])                             # ad ile unvan bitişik
        self.assertEqual(adlar("ISE 450"), ["Mehmet Yılmaz"])                          # çok boşluklu sütunlar, unvansız
        self.assertFalse(d["ISE 450"]["hocalar"][0]["unvanli"])
        self.assertTrue(d["ISE 424"]["hocalar"][0]["unvanli"])
        self.assertIn("Mart 2026 programı", s["tanimayan"])

    def test_kod_olmayan_ve_yasak_onek(self):
        s = dy.ayikla("Mart 2026 Takvimi\nCOVID 101 bilgilendirme\nÖnkoşul: ISE 101\nISE 101 Giriş")
        self.assertEqual([d["k"] for d in s["dersler"]], ["ISE 101"])
        with self.assertRaises(ValueError):
            dy.onizle("hiç ders yok burada")

    def test_onizleme_yazmaz(self):
        once = self.dosyalar()
        eski_ben = c.ben().get("dersler")
        self.kisi_ac("dilara-ornek", "Dilara Tuna Örnek")
        once = self.dosyalar()
        r = dy.onizle(YAPISTIR)
        self.assertEqual(self.dosyalar(), once)
        self.assertEqual(c.ben().get("dersler"), eski_ben)
        h = next(h for d in r["dersler"] for h in d["hocalar"] if h["ad"] == "Dilara Tuna Örnek")
        self.assertEqual(h["agda"], "dilara-ornek")      # mevcut kişi eşleşti
        self.assertEqual(r["ozet"]["yeni_hoca"], r["ozet"]["hoca"] - 1)

    def test_uygula_profil_hoca_baglar_agsiz(self):
        c.ben_yaz({"dersler": ["MATH 101"]})
        with mock.patch.object(kn, "_istek", side_effect=AssertionError("ağ isteği yok")):
            r = dy.onizle(YAPISTIR)
            s = dy.uygula(r["token"], {"dersler": ["ISE 424", "ISE 426-1", "MATH 101"], "hocalar": ["ISE 424:0", "ISE 426-1:0", "MATH 101:0"]})
        self.assertEqual(sorted(c.liste_yap(c.ben()["dersler"])), ["ISE 424", "ISE 426-1", "MATH 101"])
        self.assertEqual(sorted(s["eklenen"]), ["Ali Veli", "Cem Örnek", "Dilara Tuna Örnek"])   # Ayşe seçilmedi; ISE 430.. seçilmedi
        k = next(x for x in c.kisileri_oku() if x["ad"] == "Dilara Tuna Örnek")
        self.assertEqual((k["tur"], k["yakinlik"]), ("akademi", 0))
        self.assertIn("ISE 424 Sistem Analizi", c.bolum_oku(k["govde"], "Dersler"))
        bag = [i for i in c.iliskileri_oku() if i["tip"] == "hocasi"]
        self.assertEqual(sorted(i["a"] for i in bag), sorted(x["id"] for x in c.kisileri_oku() if x["ad"] in ("Dilara Tuna Örnek", "Ali Veli", "Cem Örnek")))
        self.assertTrue(all(i["b"] == c.ben_id() for i in bag))                         # hoca → ben (kural b)
        self.assertTrue(any(x["alan"] == "soru" and x["kisi"] == k["id"] for x in c.cikarimlari_oku()))
        n = len(c.kisileri_oku())
        dy.uygula(r["token"], {"dersler": ["ISE 424"], "hocalar": ["ISE 424:0"]})   # tekrar: kopya kişi/ders/bağ yok
        self.assertEqual(len(c.kisileri_oku()), n)
        self.assertEqual(len([i for i in c.iliskileri_oku() if i["tip"] == "hocasi"]), len(bag))
        self.assertEqual(c.bolum_oku(self.kisi(k["id"])["govde"], "Dersler").count("ISE 424"), 1)

    def test_mevcut_hocaya_ders_eklenir_ve_unvansiz_varsayilan_secilmez(self):
        self.kisi_ac("dilara-ornek", "Dilara Tuna Örnek", tur="akademi")
        r = dy.onizle("ISE 424 Sistem Analizi · Dr. Dilara Tuna Örnek\nISE 450 Staj  Mehmet Yılmaz  Salon 3")
        dy.uygula(r["token"], {})   # hocalar verilmezse yalnız unvanlılar
        self.assertEqual([k["ad"] for k in c.kisileri_oku()].count("Dilara Tuna Örnek"), 1)
        self.assertIn("ISE 424", c.bolum_oku(self.kisi("dilara-ornek")["govde"], "Dersler"))
        self.assertNotIn("Mehmet Yılmaz", [k["ad"] for k in c.kisileri_oku()])
        self.assertEqual(sorted(c.liste_yap(c.ben()["dersler"])), ["ISE 424", "ISE 450"])
        with self.assertRaises(ValueError):
            dy.uygula(r["token"], {"dersler": []})


# ================= sunucu uçları =================
class UcTest(Taban):
    YOLLAR = ("/api/takvim/onizle", "/api/takvim/uygula", "/api/linkedin/onizle", "/api/linkedin/uygula",
              "/api/ders-yapistir/onizle", "/api/ders-yapistir/uygula")

    def test_kayit_koken_ve_kilit(self):
        for y in self.YOLLAR:
            self.assertIn(y, sunucu.ISLEMLER)               # ISLEMLER yalnız do_POST'ta, kilit ve anahtar denetiminden sonra çözülür
            self.assertIn(y, sunucu.KOKEN_DENETIMLI)
            self.assertIn(y, sunucu.YUKLEME_AZAMI)
            # önizlemeler genel veri kilidini tutmaz (uzun sürebilir; kişi dosyalarını okuyan kısa bölüm ort.okuma_kilidi ile korunur); uygula yazar → kilitli
            self.assertEqual(y in sunucu.KILITSIZ, y.endswith("/onizle"), y)
        for y in self.YOLLAR[::2]:
            self.assertIn(y, sunucu.DEGISTIRMEYEN)          # önizleme yazmaz
        for y in self.YOLLAR[1::2]:
            self.assertNotIn(y, sunucu.DEGISTIRMEYEN)
        self.assertLess(sunucu.YUKLEME_AZAMI["/api/ders-yapistir/onizle"], 1_000_000)

    def test_onizle_uclari_islenir(self):
        import base64
        ics = "data:text/calendar;base64," + base64.b64encode(takvim(olay("s", "DTSTART:20250310T100000", kisiler=[BEN, DENIZ]))).decode()
        r = sunucu.ISLEMLER["/api/takvim/onizle"]({"ad": "../../takvim.ics", "veri": ics})
        self.assertEqual(r["ozet"]["kisi_eslesen"], 1)
        s = sunucu.ISLEMLER["/api/takvim/uygula"]({"token": r["token"], "secimler": "geçersiz"})   # tür bozuksa varsayılan
        self.assertEqual(s["eslesen"], 1)
        csv_ = "data:text/csv;base64," + base64.b64encode(BAGLANTI_CSV.encode()).decode()
        r = sunucu.ISLEMLER["/api/linkedin/onizle"]({"dosyalar": [{"ad": "Connections.csv", "veri": csv_}]})
        self.assertEqual(r["ozet"]["baglanti"], 4)
        with self.assertRaises(ValueError):
            sunucu.ISLEMLER["/api/linkedin/onizle"]({"dosyalar": []})
        r = sunucu.ISLEMLER["/api/ders-yapistir/onizle"]({"metin": YAPISTIR})
        self.assertEqual(r["ozet"]["ders"], 6)

    def test_govde_siniri_413(self):
        isl = sunucu.Isleyici.__new__(sunucu.Isleyici)
        gonderilen = []
        isl._gonder = lambda kod, govde, *a, **k: gonderilen.append(kod)
        isl.headers = {"Content-Length": str(sunucu.YUKLEME_AZAMI["/api/ders-yapistir/onizle"] + 1)}
        self.assertIsNone(isl._govde(sunucu.YUKLEME_AZAMI["/api/ders-yapistir/onizle"]))
        self.assertEqual(gonderilen, [413])

    def test_zip_icerik_eski_whatsapp_davranisi_korundu(self):
        z = zip_yap({"WhatsApp Chat - Ada Deneme.txt": "12.03.2025 10:00 - Ada Deneme: merhaba\n"})
        (ad, metin), = list(ia._txt_metinleri("x.zip", z))
        self.assertEqual(ad, "WhatsApp Chat - Ada Deneme.txt")
        with self.assertRaises(ValueError):
            list(ia._txt_metinleri("x.zip", zip_yap({"a.txt": b"0" * 40_000_000})))


if __name__ == "__main__":
    unittest.main()
