"""Kut sana gelsin (ag_bildirim): ayar doğrulama, zamanlanmış görev komutları (Windows/macOS/Linux, hepsi mock), tırnaklama ve uzunluk sınırı,
toast XML kaçışı ve ortam değişkeniyle aktarım, metin() gizliliği, calistir akışları, durum().
Gerçek Görev Zamanlayıcı'ya, LaunchAgent/systemd klasörüne ya da gerçek bildirime dokunulmaz: subprocess.run sahtedir, ev dizini geçicidir."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import base64
import os
import plistlib
import subprocess
import sys
import tempfile
import types
import unittest
import xml.etree.ElementTree as ET
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_bildirim as bd  # noqa: E402
import ag_cekirdek as c  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402

BUGUN = date(2026, 10, 19)   # pazartesi


def yanit(rc=0, out=b"", err=b""):
    return subprocess.CompletedProcess([], rc, out, err)


class Temel(unittest.TestCase):
    """Her testte: geçici ayar klasörü + ev dizini, subprocess.run sahte (kayıt tutar), platform seçilebilir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.kok = self._tmp.name
        self.ev = os.path.join(self.kok, "ev")
        self.veri = os.path.join(self.kok, "Kut verisi İ", "veri")
        os.makedirs(self.veri)
        self.cagrilar = []        # [(args, env)]
        self.cevap = lambda args: yanit()
        for p in (mock.patch.object(ia, "DEPO", os.path.join(self.kok, "depo")),
                  mock.patch.object(ia, "AYARLAR", os.path.join(self.kok, "depo", "ayarlar.json")),
                  mock.patch.object(c, "VERI", self.veri),
                  mock.patch.object(bd.subprocess, "run", side_effect=self._sahte_run),
                  mock.patch.object(bd, "_ev", return_value=self.ev),
                  mock.patch.object(bd, "_uid", return_value=501),
                  mock.patch.object(bd.shutil, "which", side_effect=lambda ad, *a, **k: "/usr/bin/" + ad),
                  mock.patch.dict(sys.modules, {"winreg": self._sahte_winreg()})):   # gerçek kayıt defterine asla yazılmaz
            p.start()
            self.addCleanup(p.stop)
        self.platform("windows")

    def _sahte_winreg(self):
        """Bellekte kayıt defteri: {anahtar: {ad: değer}}; silinen anahtarlar `self.silinen`."""
        self.kayit, self.silinen, test = {}, [], self

        class Anahtar:
            def __init__(self, yol):
                self.yol = yol

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        w = types.SimpleNamespace(HKEY_CURRENT_USER="HKCU", REG_SZ=1)
        w.CreateKey = lambda kok, yol: (test.kayit.setdefault(yol, {}), Anahtar(yol))[1]
        w.SetValueEx = lambda k, ad, _, tip, deger: test.kayit[k.yol].__setitem__(ad, deger)
        w.DeleteKey = lambda kok, yol: (test.silinen.append(yol), test.kayit.pop(yol))
        return w

    def _sahte_run(self, args, **kw):
        self.cagrilar.append((list(args), kw.get("env")))
        if "/XML" in args:                                  # Görev Zamanlayıcı dosyayı çağrı sırasında okur: içeriği o an yakala
            self.xml_yol = args[args.index("/XML") + 1]
            with open(self.xml_yol, "rb") as f:
                self.xml_bayt = f.read()
        return self.cevap(list(args))

    def platform(self, ad):
        p = mock.patch.object(bd, "_platform", return_value=ad)
        p.start()
        self.addCleanup(p.stop)

    def args(self, i=None):
        liste = [a for a, _ in self.cagrilar]
        return liste if i is None else liste[i]

    def gunluk(self):
        try:
            return open(os.path.join(ia.DEPO, "sunucu.log"), encoding="utf-8").read()
        except OSError:
            return ""


def ozet_ornek(**ek):
    """Kurgusal özet: kişi adları, notlar, söz ve taslak içerikleri gizlilik testi için bilerek 'sızdırılabilir' alanlarda durur."""
    o = {"hafta": "2026-W43", "tarih": "2026-10-19", "selam": "Günaydın Deniz. Bu hafta 3 kişi ve 1 söz seni bekliyor.", "bos": False,
         "maddeler": [
             {"id": "ayse-yilmaz", "ad": "Ayşe Yılmaz", "tur": "is", "neden": "Yeni proje (bugün)", "adim": "GIZLI-ADIM", "taslak": "GIZLI-TASLAK", "not": "GIZLI-NOT"},
             {"id": "mehmet-kaya", "ad": "Mehmet Kaya", "tur": "cevre", "neden": "40 gündür temas yok", "adim": "GIZLI-ADIM2", "taslak": "GIZLI-TASLAK2"},
             {"id": "deniz-demo", "ad": "Deniz Demo", "tur": "akademi", "neden": "Rapor sorusu (2 gün gecikti)", "adim": "x", "taslak": "y"}],
         "sozler": [{"id": "ayse-yilmaz", "ad": "Ayşe Yılmaz", "neden": "verdiğin söz: 3 gün gecikti · GIZLI-SOZ-METNI", "metin": "GIZLI-SOZ-METNI", "yazi": "GIZLI-SOZ-METNI"}],
         "sonuc_bekleyen": [], "istatistik": {}}
    o.update(ek)
    return o


class AyarDogrulamaTest(Temel):
    def test_varsayilan_kapali(self):
        a = bd.ayar()
        self.assertEqual(a, {"acik": False, "siklik": "haftalik", "gun": 0, "saat": "09:00", "adlar": False, "veri": "", "kurulum": "", "son": ""})
        self.cevap = lambda a: yanit(1)                                # görev yok
        d = bd.durum()
        self.assertFalse(d["acik"])
        self.assertFalse(d["kurulu"])

    def test_gecersiz_girdiler_reddedilir_ve_hicbir_sey_calismaz(self):
        kotu = [None, [], "acik", {"acik": "true"}, {"acik": 1}, {"adlar": "evet"}, {"adlar": None},
                {"siklik": "aylik"}, {"siklik": ""}, {"siklik": 1},
                {"gun": 7}, {"gun": -1}, {"gun": "1"}, {"gun": True}, {"gun": 1.0}, {"gun": None},
                {"saat": "9:00"}, {"saat": "24:00"}, {"saat": "09:60"}, {"saat": "09:00:00"}, {"saat": 900}, {"saat": None}, {"saat": "09:00\n"}, {"saat": " 09:00"},
                {"veri": "C:\\baska"}, {"kurulum": "zamanlayici"}, {"son": "x"}, {"acik": True, "komut": "calc"}]
        for g in kotu:
            with self.subTest(g=g), self.assertRaises(ValueError):
                bd.ayarla(g)
        self.assertEqual(self.cagrilar, [])                           # hiçbir alt süreç çalışmadı
        self.assertFalse(os.path.exists(ia.AYARLAR))                  # ayar yazılmadı

    def test_gecerli_kapali_ayar_yazilir_gorev_kurulmaz(self):
        d = bd.ayarla({"acik": False, "siklik": "gunluk", "gun": 4, "saat": "07:30", "adlar": True})
        self.assertEqual((d["acik"], d["siklik"], d["gun"], d["saat"], d["adlar"]), (False, "gunluk", 4, "07:30", True))
        self.assertTrue(all(a[1] != "/Create" for a in self.args()))
        self.assertEqual(bd.ayar()["gun"], 4)

    def test_kismi_girdi_mevcut_degerleri_korur(self):
        bd.ayarla({"siklik": "gunluk", "saat": "06:15", "adlar": True})
        d = bd.ayarla({"gun": 2})
        self.assertEqual((d["siklik"], d["saat"], d["adlar"], d["gun"]), ("gunluk", "06:15", True, 2))

    def test_ayar_dosyasindaki_bozuk_alanlar_varsayilana_duser(self):
        ia.ayar_yaz({"ben_adlari": ["x"], "bildirim": {"acik": "yes", "siklik": "x", "gun": 99, "saat": "zz", "adlar": 1, "kurulum": "baska", "veri": 5}})
        a = bd.ayar()
        self.assertEqual(a, dict(bd.VARSAYILAN))
        ia.ayar_yaz({"bildirim": "bozuk"})
        self.assertEqual(bd.ayar(), dict(bd.VARSAYILAN))

    def test_acinca_kurar_veri_yolu_mutlak_saklanir_diger_ayarlar_korunur(self):
        ia.ayar_yaz({"ben_adlari": ["Deniz"], "ses": {"mikrofon": "izinli"}})
        d = bd.ayarla({"acik": True})
        self.assertTrue(d["acik"])
        self.assertEqual(d["kurulum"], "zamanlayici")
        self.assertEqual(d["veri"], os.path.abspath(self.veri))
        self.assertTrue(os.path.isabs(d["veri"]))
        tum = ia.ayarlar()
        self.assertEqual(tum["ben_adlari"], ["Deniz"])
        self.assertEqual(tum["ses"], {"mikrofon": "izinli"})
        self.assertEqual(tum["bildirim"]["kurulum"], "zamanlayici")

    def test_kapatinca_kaldirir(self):
        bd.ayarla({"acik": True})
        self.cagrilar.clear()
        self.cevap = lambda a: yanit(0)
        d = bd.ayarla({"acik": False})
        self.assertFalse(d["acik"])
        self.assertEqual(d["kurulum"], "")
        silinen = [a for a in self.args() if a[1:2] == ["/Delete"]]
        self.assertEqual(len(silinen), 2)                              # iki sıklığın görevi de

    def test_kurulum_basarisizsa_acik_kalmaz_ve_anlasilir_hata(self):
        self.cevap = lambda a: yanit(1, b"", b"ERROR: Access is denied.\r\n") if a[1] == "/Create" else yanit(1)
        with self.assertRaises(bd.KurulumHatasi) as ctx:
            bd.ayarla({"acik": True, "saat": "08:00"})
        self.assertIn("Access is denied", str(ctx.exception))
        self.assertIn("kod 1", str(ctx.exception))
        a = bd.ayar()
        self.assertFalse(a["acik"])
        self.assertEqual(a["kurulum"], "")
        self.assertEqual(a["saat"], "08:00")                           # diğer tercihler yine saklanır

    def test_onceki_acik_ayar_yeniden_kurulumda_basarisizsa_kapanir(self):
        bd.ayarla({"acik": True})
        self.cevap = lambda a: yanit(1) if a[1] == "/Create" else yanit(0)
        with self.assertRaises(bd.KurulumHatasi):
            bd.ayarla({"acik": True, "saat": "10:00"})
        self.assertFalse(bd.ayar()["acik"])

    def test_zaman_asimi_ve_oserror_kurulum_hatasi_olur(self):
        for hata in (subprocess.TimeoutExpired("schtasks", 20), FileNotFoundError(2, "Sistem belirtilen dosyayı bulamıyor")):
            with self.subTest(hata=type(hata).__name__):
                with mock.patch.object(bd.subprocess, "run", side_effect=hata), self.assertRaises(bd.KurulumHatasi):
                    bd.ayarla({"acik": True})
                self.assertFalse(bd.ayar()["acik"])

    def test_kaldirma_basarisizsa_hata_ama_ayar_kapali(self):
        bd.ayarla({"acik": True})
        self.cevap = lambda a: yanit(0) if a[1] == "/Query" else yanit(1, b"", b"denied")   # silme başarısız, görev duruyor
        with self.assertRaises(bd.KurulumHatasi):
            bd.ayarla({"acik": False})
        self.assertFalse(bd.ayar()["acik"])                            # calistir kapalı ayarda bir şey yapmaz

    def test_desteksiz_platform(self):
        self.platform("diger")
        with self.assertRaises(bd.KurulumHatasi):
            bd.ayarla({"acik": True})
        self.assertFalse(bd.ayar()["acik"])
        d = bd.durum()
        self.assertFalse(d["destek"])
        self.assertTrue(d["destek_neden"])
        self.assertFalse(d["kurulu"])
        bd.ayarla({"acik": False})                                     # kapatmak yine sorunsuz


class KomutTest(Temel):
    def test_kaynak_kurulum_pythonw_ve_kut_pyw(self):
        py = os.path.join(self.kok, "Python İ 312")
        os.makedirs(py)
        for ad in ("python.exe", "pythonw.exe"):
            open(os.path.join(py, ad), "w").close()
        with mock.patch.object(sys, "executable", os.path.join(py, "python.exe")):
            liste = bd.komut_listesi({"veri": self.veri})
        self.assertEqual(liste, [os.path.join(py, "pythonw.exe"), os.path.join(c.DEPO, "kut.pyw"), "--ozet", "--veri", os.path.abspath(self.veri)])

    def test_pythonw_yoksa_sys_executable(self):
        py = os.path.join(self.kok, "py2")
        os.makedirs(py)
        with mock.patch.object(sys, "executable", os.path.join(py, "python.exe")):
            self.assertEqual(bd.komut_listesi({"veri": self.veri})[0], os.path.join(py, "python.exe"))

    def test_pythonw_zaten_verilmisse_oldugu_gibi(self):
        with mock.patch.object(sys, "executable", os.path.join(self.kok, "PythonW.EXE")):
            self.assertEqual(bd.komut_listesi({"veri": self.veri})[0], os.path.join(self.kok, "PythonW.EXE"))

    def test_exe_kurulumu(self):
        with mock.patch.object(c, "DONDURULDU", True), mock.patch.object(sys, "executable", os.path.join(self.kok, "Kut.exe")):
            self.assertEqual(bd.komut_listesi({"veri": self.veri}), [os.path.join(self.kok, "Kut.exe"), "--ozet", "--veri", os.path.abspath(self.veri)])

    def test_veri_bossa_c_VERI(self):
        self.assertEqual(bd.komut_listesi({})[-1], os.path.abspath(self.veri))

    def test_durum_komut_gosterimi(self):
        d = bd.durum()
        self.assertIn("--ozet", d["komut"])
        self.assertIn("kut.pyw", d["komut"])
        self.assertIn(os.path.abspath(self.veri), d["komut"])


class WindowsTest(Temel):
    NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}

    def kur(self, **ek):
        return bd.ayarla({"acik": True, **ek})

    def olustur_cagrisi(self):
        (a,) = [x for x in self.args() if x[1:2] == ["/Create"]]
        return a

    def gorev(self, **ek):
        """Kurar; (schtasks argümanları, ayrıştırılmış görev XML'i) döndürür. XML, schtasks çağrılırken diskten okunmuş içeriktir."""
        self.kur(**ek)
        return self.olustur_cagrisi(), ET.fromstring(self.xml_bayt)

    def bul(self, kok, yol):
        (e,) = kok.findall(yol, self.NS)
        return e

    def test_xml_ile_kurulur_komut_satirinda_zamanlama_yok(self):
        a, _ = self.gorev(gun=2, saat="08:30")
        self.assertEqual(os.path.basename(a[0]).lower(), "schtasks.exe")
        self.assertEqual(a[1:6], ["/Create", "/F", "/TN", "Kut" + chr(92) + "Haftalik ozet", "/XML"])
        self.assertEqual(len(a), 7)
        for yasak in ("/SC", "/D", "/ST", "/TR"):
            self.assertNotIn(yasak, a)

    def test_xml_utf16_le_bom_ve_gecici_dosya_silinir(self):
        a, _ = self.gorev()
        self.assertEqual(self.xml_bayt[:2], b"\xff\xfe")
        self.assertIn('encoding="UTF-16"', self.xml_bayt.decode("utf-16").splitlines()[0])
        self.assertTrue(os.path.basename(a[-1]).startswith("kut-gorev-"))
        self.assertFalse(os.path.exists(a[-1]))

    def test_gecici_dosya_hata_olsa_da_silinir(self):
        self.cevap = lambda a: yanit(1, b"", b"ERROR: bad xml")
        with self.assertRaises(bd.KurulumHatasi):
            self.kur()
        self.assertFalse(os.path.exists(self.xml_yol))
        with mock.patch.object(bd.subprocess, "run", side_effect=subprocess.TimeoutExpired("schtasks", 20)), self.assertRaises(bd.KurulumHatasi):
            self.kur()

    def test_haftalik_tetikleyici(self):
        _, k = self.gorev(gun=2, saat="08:30")
        t = self.bul(k, "t:Triggers/t:CalendarTrigger")
        self.assertEqual([e.tag.split("}")[1] for e in self.bul(t, "t:ScheduleByWeek/t:DaysOfWeek")], ["Wednesday"])
        self.assertEqual(self.bul(t, "t:ScheduleByWeek/t:WeeksInterval").text, "1")
        bas = self.bul(t, "t:StartBoundary").text
        self.assertRegex(bas, r"^\d{4}-\d\d-\d\dT08:30:00$")
        self.assertEqual(date.fromisoformat(bas[:10]).weekday(), 2)               # başlangıç günü seçilen gün
        self.assertEqual(self.bul(t, "t:Enabled").text, "true")

    def test_gunluk_tetikleyici(self):
        a, k = self.gorev(siklik="gunluk", saat="07:05", gun=3)
        self.assertEqual(a[4], "Kut" + chr(92) + "Gunluk ozet")
        t = self.bul(k, "t:Triggers/t:CalendarTrigger")
        self.assertEqual(self.bul(t, "t:ScheduleByDay/t:DaysInterval").text, "1")
        self.assertEqual(t.findall("t:ScheduleByWeek", self.NS), [])
        self.assertTrue(self.bul(t, "t:StartBoundary").text.endswith("T07:05:00"))

    def test_gun_adlari(self):
        for gun, ad in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]):
            with self.subTest(gun=gun):
                self.cagrilar.clear()
                _, k = self.gorev(gun=gun)
                self.assertEqual([e.tag.split("}")[1] for e in self.bul(k, "t:Triggers/t:CalendarTrigger/t:ScheduleByWeek/t:DaysOfWeek")], [ad])

    def test_baslangic_gelecekte_ve_dogru_gunde(self):
        from datetime import datetime
        simdi = datetime(2026, 10, 19, 10, 0)                                     # pazartesi 10:00
        h = lambda **ek: bd._win_baslangic({**bd.VARSAYILAN, **ek}, simdi)
        self.assertEqual(h(gun=0, saat="09:00"), datetime(2026, 10, 26, 9, 0))    # bugünkü 09:00 geçti: gelecek pazartesi
        self.assertEqual(h(gun=0, saat="11:00"), datetime(2026, 10, 19, 11, 0))
        self.assertEqual(h(gun=6, saat="09:00"), datetime(2026, 10, 25, 9, 0))
        self.assertEqual(h(siklik="gunluk", saat="09:00"), datetime(2026, 10, 20, 9, 0))
        self.assertEqual(h(siklik="gunluk", saat="23:59"), datetime(2026, 10, 19, 23, 59))

    def test_ayarlar_pil_kacirilan_tek_ornek_sinir(self):
        _, k = self.gorev()
        ayar = lambda ad: self.bul(k, "t:Settings/t:" + ad).text
        self.assertEqual(ayar("DisallowStartIfOnBatteries"), "false")
        self.assertEqual(ayar("StopIfGoingOnBatteries"), "false")
        self.assertEqual(ayar("StartWhenAvailable"), "true")
        self.assertEqual(ayar("MultipleInstancesPolicy"), "IgnoreNew")
        self.assertEqual(ayar("ExecutionTimeLimit"), "PT5M")
        self.assertEqual(ayar("Enabled"), "true")
        self.assertEqual(self.bul(k, "t:Principals/t:Principal/t:LogonType").text, "InteractiveToken")
        self.assertEqual(self.bul(k, "t:Principals/t:Principal/t:RunLevel").text, "LeastPrivilege")   # yönetici yetkisi yok

    def test_exec_komut_ve_arguman_ayri_unicode_yol_tirnakli(self):
        py = os.path.join(self.kok, "Python İ 312")
        os.makedirs(py)
        open(os.path.join(py, "pythonw.exe"), "w").close()
        with mock.patch.object(sys, "executable", os.path.join(py, "python.exe")):
            _, k = self.gorev()
        komut = self.bul(k, "t:Actions/t:Exec/t:Command").text
        arg = self.bul(k, "t:Actions/t:Exec/t:Arguments").text
        self.assertEqual(komut, os.path.join(py, "pythonw.exe"))                  # Command tek başına, tırnaksız
        self.assertNotIn(komut, arg)
        self.assertEqual(arg, subprocess.list2cmdline([os.path.join(c.DEPO, "kut.pyw"), "--ozet", "--veri", os.path.abspath(self.veri)]))
        self.assertTrue(arg.endswith('--ozet --veri "' + os.path.abspath(self.veri) + '"'))   # boşluklu/Unicode veri yolu tırnaklı
        self.assertIn("İ", arg)

    def test_xml_kacisi(self):
        bs = chr(92)
        liste = ["C:" + bs + "A&B" + bs + "pythonw.exe", "C:" + bs + "kut.pyw", "--ozet", "--veri", "C:" + bs + "A&B <x> 'y' </Arguments><Evil/>"]
        xml = bd._win_xml(dict(bd.VARSAYILAN), liste)
        k = ET.fromstring(xml.encode("utf-16"))                                    # iyi biçimli: enjeksiyon yeni öğe açamadı
        self.assertEqual(k.findall(".//t:Evil", self.NS), [])
        self.assertEqual(self.bul(k, "t:Actions/t:Exec/t:Command").text, liste[0])
        self.assertIn(liste[4], self.bul(k, "t:Actions/t:Exec/t:Arguments").text)  # kaçış çift yönlü geri döner
        for ham in ("<x>", "<Evil/>", " & "):
            self.assertNotIn(ham, xml)
        self.assertIn("&amp;", xml)
        self.assertIn("&lt;", xml)

    @unittest.skipUnless(os.name == "nt", "CommandLineToArgvW yalnız Windows'ta")
    def test_arguman_gercek_ayristirmayla_geri_doner(self):
        import ctypes
        f = ctypes.windll.shell32.CommandLineToArgvW
        f.restype = ctypes.POINTER(ctypes.c_wchar_p)
        k = ctypes.windll.kernel32
        k.LocalFree.argtypes = [ctypes.c_void_p]

        def ayristir(satir):
            n = ctypes.c_int(0)
            p = f(satir, ctypes.byref(n))
            try:
                return [p[i] for i in range(n.value)]
            finally:
                k.LocalFree(ctypes.cast(p, ctypes.c_void_p))

        for veri in (r"C:\Users\Ornek\Documents\İkinci Beyin\notlar\ag", r"C:\Kut", "C:\\", r"D:\Çok  Boşluklu   Klasör\Ağ Verisi"):
            with self.subTest(veri=veri):
                liste = [r"C:\Python312\pythonw.exe", r"C:\Users\Ornek\Documents\İkinci Beyin\projeler\agim\kut.pyw", "--ozet", "--veri", veri]
                # Görev Zamanlayıcı <Arguments>'ı pencere komut satırı olarak programa verir: program kendi argv'sini buradan görür
                self.assertEqual(ayristir("prog.exe " + bd._win_arguman(liste)), ["prog.exe"] + liste[1:])

    def test_261_karakter_sinirinin_kalkmasi_uzun_yol_kabul(self):
        uzun = os.path.join("C:" + chr(92), "x" * 250)                             # eski /TR sınırını aşardı; var olması gerekmez
        with mock.patch.object(c, "VERI", uzun):
            _, k = self.gorev()
        self.assertIn(uzun, self.bul(k, "t:Actions/t:Exec/t:Arguments").text)
        self.assertTrue(bd.ayar()["acik"])

    def test_cift_tirnakli_ya_da_satir_sonlu_yol_reddedilir(self):
        for kotu in ('C:\\a"b', "C:\\a\nb"):
            with self.subTest(kotu=kotu), mock.patch.object(c, "VERI", kotu), self.assertRaises(bd.KurulumHatasi):
                self.kur()

    def test_siklik_degisince_eski_gorev_silinir(self):
        self.cevap = lambda a: yanit(0)
        self.kur(siklik="gunluk")
        self.assertIn(["/Delete", "/F", "/TN", "Kut\\Haftalik ozet"], [a[1:] for a in self.args()])

    def test_kaldir_olmayan_gorevde_sessiz(self):
        self.cevap = lambda a: yanit(1)                                # /Query: yok
        bd.kaldir()
        self.assertTrue(all(a[1] == "/Query" for a in self.args()))

    def test_kaldir_delete_F(self):
        self.cevap = lambda a: yanit(0)
        bd.kaldir()
        self.assertIn(["/Delete", "/F", "/TN", "Kut\\Haftalik ozet"], [a[1:] for a in self.args()])

    def test_durum_kurulu_gercekten_sorgular(self):
        bd.ayarla({"acik": True})
        self.cagrilar.clear()
        self.cevap = lambda a: yanit(0)
        self.assertTrue(bd.durum()["kurulu"])
        self.assertEqual(self.args(0)[1:], ["/Query", "/TN", "Kut\\Haftalik ozet"])
        self.cevap = lambda a: yanit(1, b"", b"ERROR: The system cannot find the file specified.")
        self.assertFalse(bd.durum()["kurulu"])                         # ayar 'acik' olsa da görev silinmişse False

    def test_durum_gunluk_ayarda_gunluk_gorevi_sorar(self):
        bd.ayarla({"acik": True, "siklik": "gunluk"})
        self.cagrilar.clear()
        bd.durum()
        self.assertEqual(self.args(0)[3], "Kut\\Gunluk ozet")

    def test_durum_istisna_firlatmaz(self):
        bd.ayarla({"acik": True})
        with mock.patch.object(bd.subprocess, "run", side_effect=OSError("yok")):
            d = bd.durum()
        self.assertFalse(d["kurulu"])
        self.assertTrue(d["destek"])
        self.assertEqual(d["platform"], "windows")

    def test_alt_surecler_pencere_acmaz_kabuksuz(self):
        kayit = []
        with mock.patch.object(bd.subprocess, "run", side_effect=lambda a, **kw: (kayit.append((a, kw)), yanit())[1]):
            bd.ayarla({"acik": True})
        for a, kw in kayit:
            self.assertIsInstance(a, list)
            self.assertFalse(kw.get("shell"))
            self.assertIn("timeout", kw)
            if os.name == "nt":
                self.assertEqual(kw["creationflags"], subprocess.CREATE_NO_WINDOW)


class MacTest(Temel):
    def setUp(self):
        super().setUp()
        self.platform("macos")

    def plist(self):
        with open(bd._mac_plist(), "rb") as f:
            return plistlib.load(f)

    def test_haftalik_plist_ve_launchctl(self):
        bd.ayarla({"acik": True, "gun": 6, "saat": "08:05"})
        p = self.plist()
        self.assertEqual(p["Label"], "com.koraykutlu.kut.ozet")
        self.assertEqual(p["StartCalendarInterval"], {"Hour": 8, "Minute": 5, "Weekday": 0})          # Pazar = 0
        self.assertEqual(p["ProgramArguments"][1:], [os.path.join(c.DEPO, "kut.pyw"), "--ozet", "--veri", os.path.abspath(self.veri)])
        self.assertFalse(p["RunAtLoad"])
        yol = os.path.join(self.ev, "Library", "LaunchAgents", "com.koraykutlu.kut.ozet.plist")
        self.assertEqual(bd._mac_plist(), yol)
        self.assertEqual(self.args()[:2], [["launchctl", "bootout", "gui/501/com.koraykutlu.kut.ozet"], ["launchctl", "bootstrap", "gui/501", yol]])

    def test_pazartesi_weekday_1_ve_gunluk_weekday_yok(self):
        bd.ayarla({"acik": True, "gun": 0})
        self.assertEqual(self.plist()["StartCalendarInterval"]["Weekday"], 1)
        bd.ayarla({"acik": True, "siklik": "gunluk"})
        self.assertNotIn("Weekday", self.plist()["StartCalendarInterval"])

    def test_bootstrap_basarisizsa_hata(self):
        self.cevap = lambda a: yanit(5, b"", b"Bootstrap failed: 5: Input/output error") if a[1] == "bootstrap" else yanit(0)
        with self.assertRaises(bd.KurulumHatasi) as ctx:
            bd.ayarla({"acik": True})
        self.assertIn("Input/output", str(ctx.exception))
        self.assertFalse(bd.ayar()["acik"])

    def test_kaldir_bootout_ve_plist_silinir(self):
        bd.ayarla({"acik": True})
        self.cagrilar.clear()
        bd.ayarla({"acik": False})
        self.assertEqual(self.args(0), ["launchctl", "bootout", "gui/501/com.koraykutlu.kut.ozet"])
        self.assertFalse(os.path.exists(bd._mac_plist()))
        bd.kaldir()                                                    # ikinci kez: sessiz

    def test_durum_kurulu_plist_ve_launchctl_print(self):
        bd.ayarla({"acik": True})
        self.cagrilar.clear()
        self.assertTrue(bd.durum()["kurulu"])
        self.assertEqual(self.args(0), ["launchctl", "print", "gui/501/com.koraykutlu.kut.ozet"])
        self.cevap = lambda a: yanit(113)
        self.assertFalse(bd.durum()["kurulu"])

    def test_bildirim_argv_ile_metin_gomulmez(self):
        self.assertTrue(bd.bildir("Kut", 'Bu hafta "2" kişi \\ seni bekliyor.'))
        a = self.args(0)
        self.assertEqual(a[0], "osascript")
        self.assertEqual(a[-2:], ["Kut", 'Bu hafta "2" kişi \\ seni bekliyor.'])
        betik = " ".join(a[1:-2])
        self.assertIn("on run argv", betik)
        self.assertNotIn("seni bekliyor", betik)
        self.assertNotIn("Kut", [x for x in a[1:-2] if x != "-e"][1:])  # başlık betik içine gömülmedi

    def test_bildirim_tire_ile_baslayan_metin_secenek_olamaz(self):
        bd.bildir("-e Kut", "--x")
        self.assertFalse(any(x.startswith("-") for x in self.args(0)[-2:]))


class LinuxTest(Temel):
    def setUp(self):
        super().setUp()
        self.platform("linux")
        self.d = os.path.join(self.ev, ".config", "systemd", "user")

    def oku(self, ad):
        with open(os.path.join(self.d, ad), encoding="utf-8") as f:
            return f.read()

    def test_haftalik_birimler_ve_systemctl(self):
        bd.ayarla({"acik": True, "gun": 4, "saat": "09:00"})
        t = self.oku("kut-ozet.timer")
        self.assertIn("OnCalendar=Fri *-*-* 09:00:00", t)
        self.assertIn("Persistent=true", t)
        self.assertIn("WantedBy=timers.target", t)
        s = self.oku("kut-ozet.service")
        self.assertIn("Type=oneshot", s)
        self.assertIn('ExecStart="', s)
        self.assertIn(f'"--ozet" "--veri" "{os.path.abspath(self.veri)}"'.replace("\\", "\\\\"), s)
        self.assertEqual(self.args()[:2], [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", "kut-ozet.timer"]])

    def test_gunluk_oncalendar_gunsuz(self):
        bd.ayarla({"acik": True, "siklik": "gunluk", "saat": "06:45"})
        self.assertIn("OnCalendar=*-*-* 06:45:00", self.oku("kut-ozet.timer"))

    def test_systemd_tirnaklama(self):
        self.assertEqual(bd._systemd_tirnak('/a b/c%d$e"f\\g'), '"/a b/c%%d$$e\\"f\\\\g"')

    def test_enable_basarisizsa_hata_ve_ayar_kapali(self):
        self.cevap = lambda a: yanit(1, b"", b"Failed to connect to bus") if "enable" in a else yanit(0)
        with self.assertRaises(bd.KurulumHatasi) as ctx:
            bd.ayarla({"acik": True})
        self.assertIn("Failed to connect", str(ctx.exception))
        self.assertFalse(bd.ayar()["acik"])
        self.assertFalse(os.path.exists(os.path.join(self.d, "kut-ozet.timer")))     # yarım kurulum temizlendi

    def test_kaldir(self):
        bd.ayarla({"acik": True})
        self.cagrilar.clear()
        bd.ayarla({"acik": False})
        self.assertEqual(self.args(), [["systemctl", "--user", "disable", "--now", "kut-ozet.timer"], ["systemctl", "--user", "daemon-reload"]])
        self.assertEqual(os.listdir(self.d), [])
        self.cagrilar.clear()
        bd.kaldir()
        self.assertEqual(self.cagrilar, [])                            # kurulu değilse hiçbir şey çalıştırılmaz

    def test_durum_kurulu(self):
        bd.ayarla({"acik": True})
        self.cagrilar.clear()
        self.assertTrue(bd.durum()["kurulu"])
        self.assertEqual(self.args(0), ["systemctl", "--user", "is-enabled", "kut-ozet.timer"])
        self.cevap = lambda a: yanit(1)
        self.assertFalse(bd.durum()["kurulu"])

    def test_systemd_yoksa_destek_false(self):
        with mock.patch.object(bd.shutil, "which", side_effect=lambda ad, *a, **k: None if ad == "systemctl" else "/usr/bin/" + ad):
            d = bd.durum()
            self.assertFalse(d["destek"])
            self.assertIn("systemd", d["destek_neden"])
            with self.assertRaises(bd.KurulumHatasi):
                bd.ayarla({"acik": True})
        self.assertFalse(os.path.exists(self.d))

    def test_notify_send_yoksa_destek_false(self):
        with mock.patch.object(bd.shutil, "which", side_effect=lambda ad, *a, **k: None if ad == "notify-send" else "/usr/bin/" + ad):
            self.assertFalse(bd.durum()["destek"])

    def test_bildirim_notify_send(self):
        self.assertTrue(bd.bildir("Kut", "Bu hafta 2 kişi seni bekliyor."))
        self.assertEqual(self.args(0), ["notify-send", "-a", "Kut", "--", "Kut", "Bu hafta 2 kişi seni bekliyor."])
        self.cevap = lambda a: yanit(1)
        self.assertFalse(bd.bildir("Kut", "x"))


class ToastTest(Temel):
    def bildir(self, baslik="Kut", metin="Bu hafta 2 kişi seni bekliyor."):
        sonuc = bd.bildir(baslik, metin)
        a, env = self.cagrilar[-1]
        return sonuc, a, env

    def test_betik_saf_ascii_ve_gerekli_parcalar(self):
        self.assertTrue(bd.PS_BETIK.isascii())
        self.assertIn("$env:KUT_TOAST_APPID", bd.PS_BETIK)   # uygulama kimliği betiğe gömülü değil, ortamdan gelir
        self.assertIn("$env:KUT_TOAST_XML", bd.PS_BETIK)
        self.assertIn("ToastNotificationManager", bd.PS_BETIK)
        self.assertNotIn("launch", bd.PS_BETIK.lower())               # toast'a launch verilmez
        self.assertNotIn("Kut", bd.PS_BETIK.replace("KUT_TOAST_XML", ""))   # metin/marka betiğe gömülü değil

    def test_bildirim_kut_kimligiyle_gosterilir(self):
        """Başlıkta "Windows PowerShell" değil "Kut" ve kün simgesi: HKCU AppUserModelId kaydı + o kimlikle toast (16 Ekim 2026)."""
        ok, a, env = self.bildir()
        self.assertTrue(ok)
        self.assertEqual(env["KUT_TOAST_APPID"], "KorayKutlu.Kut")
        k = self.kayit["Software\\Classes\\AppUserModelId\\KorayKutlu.Kut"]
        self.assertEqual(k["DisplayName"], "Kut")
        self.assertEqual(k["IconUri"], os.path.join(self.kok, "depo", "kut-bildirim.png"))
        with open(k["IconUri"], "rb") as f:
            self.assertEqual(f.read(4), b"\x89PNG")   # kut.ico'nun en büyük karesi
        self.bildir()   # ikinci kez: aynı kayıt, hata yok
        self.assertEqual(len(self.kayit), 1)

    def test_kimlik_kaydedilemezse_powershell_kimligine_duser(self):
        def bozuk(*a, **k):
            raise OSError("erişim yok")
        sys.modules["winreg"].CreateKey = bozuk
        ok, _, env = self.bildir()
        self.assertTrue(ok)
        self.assertEqual(env["KUT_TOAST_APPID"], bd.WIN_AUMID)

    def test_kaldirinca_kimlik_ve_simge_silinir(self):
        self.bildir()
        simge = os.path.join(self.kok, "depo", "kut-bildirim.png")
        self.assertTrue(os.path.exists(simge))
        bd.kaldir()
        self.assertIn("Software\\Classes\\AppUserModelId\\KorayKutlu.Kut", self.silinen)
        self.assertFalse(os.path.exists(simge))

    def test_arguman_listesi_ve_kodlanmis_betik(self):
        ok, a, env = self.bildir()
        self.assertTrue(ok)
        self.assertEqual(os.path.basename(a[0]).lower(), "powershell.exe")
        self.assertEqual(a[1:6], ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand"])
        self.assertEqual(len(a), 7)
        self.assertEqual(base64.b64decode(a[6]).decode("utf-16-le"), bd.PS_BETIK)

    def test_metin_komut_satirinda_degil_ortam_degiskeninde(self):
        _, a, env = self.bildir("Başlık ğüşiöçİ", "Gövde metni 12345 seni bekliyor.")
        tum = " ".join(a)
        for parca in ("Başlık", "Gövde", "12345", "seni bekliyor"):
            self.assertNotIn(parca, tum)
        self.assertIn("Gövde metni 12345 seni bekliyor.", env["KUT_TOAST_XML"])
        self.assertIn("Başlık ğüşiöçİ", env["KUT_TOAST_XML"])
        self.assertIn("PATH", {k.upper() for k in env})                # mevcut ortam korunur

    def test_xml_kacisi(self):
        kotu_b, kotu_m = 'A & B <c> "d" \'e\'', '</text><text>sahte</text> &amp; "x" <![CDATA[y]]>'
        _, _, env = self.bildir(kotu_b, kotu_m)
        kok = ET.fromstring(env["KUT_TOAST_XML"])                      # iyi biçimli XML olmalı
        metinler = [t.text for t in kok.iter("text")]
        self.assertEqual(metinler, [kotu_b, kotu_m])                   # kaçış çift yönlü geri döner; enjeksiyonla ek <text> oluşmadı
        self.assertEqual(len(kok.findall(".//text")), 2)
        self.assertNotIn("<c>", env["KUT_TOAST_XML"])
        self.assertIn("&lt;", env["KUT_TOAST_XML"])
        self.assertIn("&amp;", env["KUT_TOAST_XML"])
        self.assertIn("&quot;", env["KUT_TOAST_XML"])
        self.assertNotIn("launch", env["KUT_TOAST_XML"])

    def test_xml_ozel_islemler_ve_gecersiz_karakterler_temizlenir(self):
        _, _, env = self.bildir("Kut\x00\x01\x1b", "satir1\nsatir2\r\n\ud800tab\t!")
        kok = ET.fromstring(env["KUT_TOAST_XML"])
        self.assertEqual([t.text for t in kok.iter("text")], ["Kut", "satir1 satir2 tab !"])

    def test_uzunluk_siniri(self):
        _, _, env = self.bildir("B" * 500, "M" * 2000)
        t = [x.text for x in ET.fromstring(env["KUT_TOAST_XML"]).iter("text")]
        self.assertLessEqual(len(t[0]), bd.BASLIK_AZAMI)
        self.assertLessEqual(len(t[1]), bd.METIN_AZAMI)

    def test_bos_metin_gosterilmez(self):
        self.assertFalse(bd.bildir("", "  "))
        self.assertEqual(self.cagrilar, [])

    def test_hata_kodlari_false(self):
        for rc in (2, 3, 1):
            self.cevap = lambda a, rc=rc: yanit(rc)
            self.assertFalse(bd.bildir("Kut", "x"), rc)

    def test_zaman_asimi_ve_oserror_false_istisna_yok(self):
        for hata in (subprocess.TimeoutExpired("powershell", 20), FileNotFoundError("yok"), PermissionError("izin"), RuntimeError("beklenmedik")):
            with mock.patch.object(bd.subprocess, "run", side_effect=hata):
                self.assertFalse(bd.bildir("Kut", "x"))

    def test_zaman_asimi_20_sn(self):
        kayit = {}
        with mock.patch.object(bd.subprocess, "run", side_effect=lambda a, **kw: (kayit.update(kw), yanit())[1]):
            bd.bildir("Kut", "x")
        self.assertEqual(kayit["timeout"], 20)
        self.assertFalse(kayit.get("shell"))
        if os.name == "nt":
            self.assertEqual(kayit["creationflags"], subprocess.CREATE_NO_WINDOW)

    def test_desteksiz_platformda_false(self):
        self.platform("diger")
        self.assertFalse(bd.bildir("Kut", "x"))


class MetinTest(Temel):
    GIZLI = ("GIZLI-ADIM", "GIZLI-TASLAK", "GIZLI-NOT", "GIZLI-SOZ-METNI", "GIZLI-ADIM2", "Yeni proje", "gün gecikti", "gündür temas")

    def test_adlar_kapaliyken_hicbir_kisi_adi_yok(self):
        b, g = bd.metin(ozet_ornek())
        tum = b + " " + g
        self.assertEqual(g, "Bu hafta 3 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")
        self.assertEqual(b, "Kut")
        for yasak in ("Ayşe", "Yılmaz", "Mehmet", "Kaya", "Deniz", "Demo", "ayse", "mehmet") + self.GIZLI:
            self.assertNotIn(yasak, tum)
        self.assertNotIn("Deniz", tum)                                   # selam alanı (kullanıcı adı) da kullanılmaz

    def test_varsayilan_adlar_kapali(self):
        self.assertEqual(bd.metin(ozet_ornek()), bd.metin(ozet_ornek(), adlar=False))

    def test_adlar_acikken_en_cok_iki_ilk_ad_ve_arti_n(self):
        b, g = bd.metin(ozet_ornek(), adlar=True)
        self.assertEqual(g, "Bu hafta Ayşe ve Mehmet seni bekliyor (+1). 1 söz de var. Özet Kut'ta hazır.")
        for yasak in ("Yılmaz", "Kaya", "Demo") + self.GIZLI:
            self.assertNotIn(yasak, b + g)

    def test_adlar_yalniz_true_ile_acilir(self):
        for deger in ("evet", 1, "true"):
            self.assertNotIn("Ayşe", bd.metin(ozet_ornek(), adlar=deger)[1])

    def test_adlar_tek_ve_iki_kisi(self):
        o = ozet_ornek(maddeler=ozet_ornek()["maddeler"][:1], sozler=[])
        self.assertEqual(bd.metin(o, True)[1], "Bu hafta Ayşe seni bekliyor. Özet Kut'ta hazır.")
        o = ozet_ornek(maddeler=ozet_ornek()["maddeler"][:2], sozler=[])
        self.assertEqual(bd.metin(o, True)[1], "Bu hafta Ayşe ve Mehmet seni bekliyor. Özet Kut'ta hazır.")

    def test_unvan_atlanir_ad_temizlenir(self):
        o = ozet_ornek(maddeler=[{"id": "d", "ad": "Dr. Deniz Demo"}, {"id": "p", "ad": "Prof.  Selin\nHoca"}], sozler=[])
        self.assertEqual(bd.metin(o, True)[1], "Bu hafta Deniz ve Selin Hoca seni bekliyor. Özet Kut'ta hazır.")

    def test_yalniz_kisi_yalniz_soz(self):
        self.assertEqual(bd.metin(ozet_ornek(sozler=[]))[1], "Bu hafta 3 kişi seni bekliyor. Özet Kut'ta hazır.")
        self.assertEqual(bd.metin(ozet_ornek(maddeler=[]))[1], "Bu hafta 1 söz seni bekliyor. Özet Kut'ta hazır.")
        self.assertEqual(bd.metin(ozet_ornek(maddeler=[]), adlar=True)[1], "Bu hafta 1 söz seni bekliyor. Özet Kut'ta hazır.")   # söz sahibi adı da verilmez

    def test_gunluk_ifadesi(self):
        self.assertTrue(bd.metin(ozet_ornek(), siklik="gunluk")[1].startswith("Bugün 3 kişi ve 1 söz"))

    def test_bos_ozet_none(self):
        self.assertIsNone(bd.metin(ozet_ornek(maddeler=[], sozler=[], bos=True)))
        self.assertIsNone(bd.metin(ozet_ornek(maddeler=[], sozler=[])))
        self.assertIsNone(bd.metin(ozet_ornek(bos=True)))
        for kotu in (None, {}, [], "x", 5, {"maddeler": "x", "sozler": 3}):
            self.assertIsNone(bd.metin(kotu))

    def test_sonucu_islenmis_ogeler_sayilmaz(self):
        m = ozet_ornek()["maddeler"]
        m[0]["sonuc"], m[1]["sonuc"], m[2]["sonuc"] = "ise_yaradi", "ertelendi", "bekliyor"
        sz = [{"id": "ayse-yilmaz", "ad": "A", "sonuc": "yaptim"}, {"id": "x", "ad": "X"}]
        self.assertEqual(bd.metin(ozet_ornek(maddeler=m, sozler=sz))[1], "Bu hafta 1 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")
        for x in m:
            x["sonuc"] = "atlandi"
        self.assertIsNone(bd.metin(ozet_ornek(maddeler=m, sozler=[{"id": "x", "sonuc": "yaptim"}])))

    def test_ayni_kisi_iki_kez_sayilmaz(self):
        o = ozet_ornek(maddeler=[{"id": "a", "ad": "Ayşe"}, {"id": "a", "ad": "Ayşe"}], sozler=[])
        self.assertEqual(bd.metin(o)[1], "Bu hafta 1 kişi seni bekliyor. Özet Kut'ta hazır.")

    def test_metin_ve_baslik_xml_ve_arguman_icin_guvenli(self):
        o = ozet_ornek(maddeler=[{"id": "a", "ad": '<b>"Ay&şe"</b>'}], sozler=[])
        b, g = bd.metin(o, True)
        bd.bildir(b, g)
        ET.fromstring(self.cagrilar[-1][1]["KUT_TOAST_XML"])           # iyi biçimli


class CalistirTest(Temel):
    def setUp(self):
        super().setUp()
        self.bildirimler = []
        self.ozet = ozet_ornek()
        self.fake = types.SimpleNamespace(olustur=mock.Mock(side_effect=lambda *a, **k: self.ozet))
        for p in (mock.patch.dict(sys.modules, {"ag_ozet": self.fake}),
                  mock.patch.object(c, "veri_klasoru"),
                  mock.patch.object(bd, "bildir", side_effect=self._bildir)):
            p.start()
            self.addCleanup(p.stop)
        self.bildir_sonuc = True
        # Hariç ikinci katmanı kişi dosyasını okur: geçici kişi klasörü + haric.md
        self.kisiler_dizini = os.path.join(self.kok, "kisiler")
        os.makedirs(self.kisiler_dizini)
        for p in (mock.patch.object(c, "KISILER", self.kisiler_dizini), mock.patch.object(c, "HARIC", os.path.join(self.kok, "haric.md"))):
            p.start()
            self.addCleanup(p.stop)
        for kid in ("ayse-yilmaz", "mehmet-kaya", "deniz-demo", "a", "b", "c", "d"):
            self.kisi(kid)

    def kisi(self, kid, **alan):
        satirlar = [f"{k}: {v}" for k, v in {"ad": kid, "tur": "cevre", **alan}.items()]
        with open(os.path.join(self.kisiler_dizini, kid + ".md"), "w", encoding="utf-8", newline="") as f:
            f.write("---" + chr(10) + chr(10).join(satirlar) + chr(10) + "---" + chr(10) + "# " + kid + chr(10))

    def _bildir(self, baslik, metin):
        self.bildirimler.append((baslik, metin))
        return self.bildir_sonuc

    def ac(self, **ek):
        bd._ayar_yaz({**bd.VARSAYILAN, "acik": True, "veri": self.veri, **ek})

    ARGV = ["kut.pyw", "--ozet"]

    def test_haftalik_bos_degilse_bildirir_adsiz(self):
        self.ac()
        self.assertEqual(bd.calistir(self.ARGV, BUGUN), 0)
        self.assertEqual(self.bildirimler, [("Kut", "Bu hafta 3 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")])
        self.fake.olustur.assert_called_once_with(BUGUN)
        self.assertRegex(bd.ayar()["son"], r"^\d{4}-\d\d-\d\d \d\d:\d\d$")
        self.assertTrue(bd.ayar()["acik"])                              # son yazılırken diğer alanlar bozulmadı
        self.assertEqual(bd.ayar()["veri"], self.veri)

    def test_haftalik_adlar_acik(self):
        self.ac(adlar=True)
        bd.calistir(self.ARGV, BUGUN)
        self.assertIn("Ayşe ve Mehmet seni bekliyor (+1)", self.bildirimler[0][1])

    def test_haftalik_bos_bildirim_yok(self):
        self.ac()
        self.ozet = ozet_ornek(maddeler=[], sozler=[], bos=True, selam="Bu hafta acil bir şey yok. Ağın sakin.")
        self.assertEqual(bd.calistir(self.ARGV, BUGUN), 0)
        self.assertEqual(self.bildirimler, [])
        self.assertEqual(bd.ayar()["son"], "")

    def test_kapaliyken_hicbir_sey_yapmaz(self):
        self.assertEqual(bd.calistir(self.ARGV, BUGUN), 0)
        self.fake.olustur.assert_not_called()
        self.assertEqual(self.bildirimler, [])

    def test_veri_arguman_uygulanir(self):
        self.ac()
        self.assertEqual(bd.calistir(self.ARGV + ["--veri", self.veri], BUGUN), 0)
        c.veri_klasoru.assert_called_once_with(self.veri)
        c.veri_klasoru.reset_mock()
        bd.calistir(self.ARGV + [f"--veri={self.veri}"], BUGUN)
        c.veri_klasoru.assert_called_once_with(self.veri)

    def test_veri_yoksa_yeniden_yaratilmaz_kod_2(self):
        self.ac()
        yok = os.path.join(self.kok, "silinmis")
        self.assertEqual(bd.calistir(self.ARGV + ["--veri", yok], BUGUN), 2)
        c.veri_klasoru.assert_not_called()
        self.fake.olustur.assert_not_called()
        self.assertIn("veri klasoru yok", self.gunluk())
        self.assertNotIn("silinmis", self.gunluk())

    def test_sessiz_ozeti_uretir_bildirmez(self):
        self.ac()
        self.assertEqual(bd.calistir(self.ARGV + ["--sessiz"], BUGUN), 0)
        self.fake.olustur.assert_called_once()
        self.assertEqual(self.bildirimler, [])

    def test_sunucu_acilmaz(self):
        self.ac()
        with mock.patch.dict(sys.modules, {"ag_sunucu": None}):        # içe aktarılırsa ImportError → test patlar
            self.assertEqual(bd.calistir(self.ARGV, BUGUN), 0)
        self.assertNotIn("ag_sunucu", bd.__dict__)

    def test_gunluk_tarih_bugun_ya_da_gecmis_ve_sonuc_bekliyor(self):
        self.ac(siklik="gunluk")
        self.ozet = ozet_ornek(
            maddeler=[{"id": "a", "ad": "Ayşe", "tarih": "2026-10-19", "sonuc": "bekliyor"},        # bugün
                      {"id": "b", "ad": "Mehmet", "tarih": "", "sonuc": "bekliyor"},                 # ihmal: tarihsiz
                      {"id": "c", "ad": "Deniz", "tarih": "2026-10-24", "sonuc": "bekliyor"},        # ileri tarih
                      {"id": "d", "ad": "Elif", "tarih": "2026-10-15", "sonuc": "bekliyor"}],        # gecikmiş
            sozler=[{"id": "a", "tarih": "2026-10-10"}, {"id": "b", "tarih": "2026-10-25"}, {"id": "c", "tarih": ""}])
        self.assertEqual(bd.calistir(self.ARGV, BUGUN), 0)
        self.assertEqual(self.bildirimler, [("Kut", "Bugün 2 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")])

    def test_gunluk_hafta_ortasi_vadesi_gelen_adim_o_gun_bildirilir(self):
        # Özet pazartesi üretildi: neden metni donmuş ("3 gün kaldı"), ama vade çarşamba. Çarşamba bildirim gelmeli, salı gelmemeli.
        self.ac(siklik="gunluk")
        self.ozet = ozet_ornek(maddeler=[{"id": "a", "ad": "Ayşe", "neden": "Teklif (3 gün kaldı)", "tarih": "2026-10-21", "sonuc": "bekliyor"}], sozler=[])
        self.assertEqual(bd.calistir(self.ARGV, date(2026, 10, 20)), 0)
        self.assertEqual(self.bildirimler, [])
        self.assertEqual(bd.calistir(self.ARGV, date(2026, 10, 21)), 0)
        self.assertEqual(self.bildirimler, [("Kut", "Bugün 1 kişi seni bekliyor. Özet Kut'ta hazır.")])
        self.assertEqual(bd.calistir(self.ARGV, date(2026, 10, 22)), 0)                              # gecikmiş de sayılır
        self.assertEqual(len(self.bildirimler), 2)

    def test_gunluk_tarih_alani_varsa_neden_metnine_bakilmaz(self):
        self.ac(siklik="gunluk")
        self.ozet = ozet_ornek(maddeler=[{"id": "a", "ad": "Ayşe", "neden": "Yeni proje (bugün)", "tarih": "2026-12-01"}],
                               sozler=[{"id": "a", "neden": "verdiğin söz: 4 gün gecikti · x", "tarih": ""}])
        bd.calistir(self.ARGV, BUGUN)
        self.assertEqual(self.bildirimler, [])

    def test_gunluk_sonucu_isaretlenmis_madde_sayilmaz(self):
        self.ac(siklik="gunluk")
        kapali = [{"id": x, "ad": x, "tarih": "2026-10-10", "sonuc": s} for x, s in
                  (("a", "yaptim"), ("b", "ise_yaradi"), ("c", "ise_yaramadi"), ("d", "atlandi"), ("deniz-demo", "ertelendi"))]
        self.ozet = ozet_ornek(maddeler=kapali, sozler=[])
        bd.calistir(self.ARGV, BUGUN)
        self.assertEqual(self.bildirimler, [])
        self.ozet = ozet_ornek(maddeler=kapali + [{"id": "ayse-yilmaz", "ad": "Ayşe", "tarih": "2026-10-10", "sonuc": "bekliyor"},
                                                  {"id": "mehmet-kaya", "ad": "Mehmet", "tarih": "2026-10-10"}], sozler=[])   # sonuc alanı yok = bekliyor
        bd.calistir(self.ARGV, BUGUN)
        self.assertEqual(self.bildirimler[0][1], "Bugün 2 kişi seni bekliyor. Özet Kut'ta hazır.")

    def test_haftalik_sonucu_isaretlenmis_maddeler_sayilmaz(self):
        self.ac()
        m = ozet_ornek()["maddeler"]
        m[0]["sonuc"], m[1]["sonuc"] = "yaptim", "atlandi"
        self.ozet = ozet_ornek(maddeler=m)
        bd.calistir(self.ARGV, BUGUN)
        self.assertEqual(self.bildirimler[0][1], "Bu hafta 1 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")

    def test_haftalik_hepsi_kapandiysa_bildirim_yok(self):
        self.ac()
        m = ozet_ornek()["maddeler"]
        for x, s in zip(m, ("yaptim", "ise_yaradi", "ertelendi")):
            x["sonuc"] = s
        self.ozet = ozet_ornek(maddeler=m, sozler=[])
        self.assertEqual(bd.calistir(self.ARGV, BUGUN), 0)
        self.assertEqual(self.bildirimler, [])
        self.assertEqual(bd.ayar()["son"], "")

    def test_haric_kisi_kisi_dosyasindan_ikinci_katmanda_elenir(self):
        self.ac()
        with open(c.HARIC, "w", encoding="utf-8") as f:
            f.write("# Hariç\n\n- Gölge Holding\n")
        self.kisi("mehmet-kaya", kurum="Gölge Holding")                     # dosya haric.md ile eşleşiyor
        self.ozet = ozet_ornek()                                           # özet (yanlışlıkla) Mehmet'i içeriyor
        bd.calistir(self.ARGV, BUGUN)
        self.assertEqual(self.bildirimler[0][1], "Bu hafta 2 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")

    def test_haric_kisi_sozu_de_elenir(self):
        self.ac(adlar=True)
        with open(c.HARIC, "w", encoding="utf-8") as f:
            f.write("- Gölge Holding\n")
        self.kisi("ayse-yilmaz", kurum="Gölge Holding")
        self.ozet = ozet_ornek(maddeler=ozet_ornek()["maddeler"][1:])
        bd.calistir(self.ARGV, BUGUN)
        self.assertEqual(self.bildirimler[0][1], "Bu hafta Mehmet ve Deniz seni bekliyor. Özet Kut'ta hazır.")   # söz de Ayşe'nin: o da düştü

    def test_kisi_dosyasi_yoksa_ya_kimlik_gecersizse_madde_sayilmaz(self):
        self.ac()
        os.remove(os.path.join(c.KISILER, "deniz-demo.md"))
        m = ozet_ornek()["maddeler"] + [{"id": "../ben", "ad": "X"}, {"id": "", "ad": "Y"}, {"ad": "Z"}]
        self.ozet = ozet_ornek(maddeler=m)
        bd.calistir(self.ARGV, BUGUN)
        self.assertEqual(self.bildirimler[0][1], "Bu hafta 2 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")

    def test_haric_kisi_dosyasi_bozuksa_sayilmaz(self):
        self.ac()
        with open(os.path.join(c.KISILER, "mehmet-kaya.md"), "w", encoding="utf-8") as f:
            f.write("frontmatter yok")
        bd.calistir(self.ARGV, BUGUN)
        self.assertEqual(self.bildirimler[0][1], "Bu hafta 2 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")

    # --- geriye uyum: ag_ozet `tarih` alanı vermiyorsa eski kalıplar ---
    def test_gunluk_eski_neden_kalibi_tarih_alani_yokken(self):
        self.ac(siklik="gunluk")
        self.ozet = ozet_ornek(
            maddeler=[{"id": "a", "ad": "Ayşe", "neden": "Yeni proje (bugün)"}, {"id": "b", "ad": "Mehmet", "neden": "40 gündür temas yok"},
                      {"id": "c", "ad": "Deniz", "neden": "Rapor (3 gün kaldı)"}, {"id": "d", "ad": "Elif", "neden": "Bugün yaz diye not (2 gün gecikti)"}],
            sozler=[{"id": "a", "neden": "verdiğin söz: 5 gün gecikti · bugün kitabı ver"}, {"id": "b", "neden": "verdiğin söz: 2 gün kaldı · x"}])
        self.assertEqual(bd.calistir(self.ARGV, BUGUN), 0)
        self.assertEqual(self.bildirimler, [("Kut", "Bugün 2 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")])

    def test_gunluk_eski_hicbiri_vadeli_degilse_bildirim_yok(self):
        self.ac(siklik="gunluk")
        self.ozet = ozet_ornek(maddeler=[{"id": "b", "ad": "Mehmet", "neden": "40 gündür temas yok"}, {"id": "c", "ad": "D", "neden": "Rapor (3 gün kaldı)"}],
                               sozler=[{"id": "b", "neden": "verdiğin söz: 25 gündür açık · bugün"}])
        self.assertEqual(bd.calistir(self.ARGV, BUGUN), 0)
        self.assertEqual(self.bildirimler, [])

    def test_gunluk_eski_yapisal_alanlar(self):
        self.ac(siklik="gunluk")
        self.ozet = ozet_ornek(maddeler=[{"id": "a", "ad": "A", "sonraki_tarih": "2026-10-19"}, {"id": "b", "ad": "B", "sonraki_tarih": "2026-10-25"},
                                         {"id": "c", "ad": "C", "gecikmis": True}, {"id": "d", "ad": "D", "durum": "yaklasan"}],
                               sozler=[{"id": "a", "son": "2026-10-10"}, {"id": "b", "son": "2026-12-01"}, {"id": "c", "son": "bozuk"}])
        bd.calistir(self.ARGV, BUGUN)
        self.assertEqual(self.bildirimler[0][1], "Bugün 2 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")

    def test_gunluk_adlar_yalniz_vadeli_kisiler(self):
        self.ac(siklik="gunluk", adlar=True)
        self.ozet = ozet_ornek(maddeler=[{"id": "b", "ad": "Mehmet", "tarih": ""}, {"id": "a", "ad": "Ayşe", "tarih": "2026-10-19"}], sozler=[])
        bd.calistir(self.ARGV, BUGUN)
        self.assertEqual(self.bildirimler[0][1], "Bugün Ayşe seni bekliyor. Özet Kut'ta hazır.")

    def test_bildirim_gosterilemezse_kod_3_ve_son_yazilmaz(self):
        self.ac()
        self.bildir_sonuc = False
        self.assertEqual(bd.calistir(self.ARGV, BUGUN), 3)
        self.assertIn("bildirim gosterilemedi", self.gunluk())
        self.assertEqual(bd.ayar()["son"], "")

    def test_hata_icerik_yazmadan_gunluge_ve_kod_1(self):
        self.ac()
        self.fake.olustur.side_effect = ValueError("Ayşe Yılmaz GIZLI-NOT okunamadı")
        self.assertEqual(bd.calistir(self.ARGV, BUGUN), 1)
        g = self.gunluk()
        self.assertEqual(len(g.strip().splitlines()), 1)
        self.assertIn("ozet-bildirim: hata: ValueError", g)
        for sizinti in ("Ayşe", "GIZLI", "okunamadı", self.kok):
            self.assertNotIn(sizinti, g)
        self.assertRegex(g, r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ")
        self.assertEqual(self.bildirimler, [])

    def test_ag_ozet_yoksa_kod_1(self):
        self.ac()
        with mock.patch.dict(sys.modules, {"ag_ozet": None}):
            self.assertEqual(bd.calistir(self.ARGV, BUGUN), 1)
        self.assertIn("ModuleNotFoundError", self.gunluk())

    def test_beklenmedik_argv_ve_gunluk_yazilamazsa_istisna_yok(self):
        self.ac()
        with mock.patch.object(bd.os, "makedirs", side_effect=OSError("disk dolu")):
            self.fake.olustur.side_effect = RuntimeError("x")
            self.assertEqual(bd.calistir(None, BUGUN), 1)
            self.assertEqual(bd.calistir([None, 5], BUGUN), 1)

    def test_olustur_bos_ozet_dondururse_yine_guvenli(self):
        self.ac(siklik="gunluk")
        self.ozet = None
        self.assertEqual(bd.calistir(self.ARGV, BUGUN), 0)
        self.assertEqual(self.bildirimler, [])


class OzetSozlesmesiTest(Temel):
    """Gerçek ag_ozet.hazirla çıktısıyla uyum (ag_ozet yoksa/yarımsa atlanır): alan adları ve neden kalıpları değişirse burada kırılır."""

    def setUp(self):
        super().setUp()
        try:
            import ag_ozet, ag_soz
        except ImportError:
            self.skipTest("ag_ozet yok")
        g = ag_soz.ekle("# A\n", "ben", "Kitabı göndermek", "2026-10-15", BUGUN)
        kisiler = [{"id": "ben", "ad": "Ben"},
                   {"id": "ayse-yilmaz", "ad": "Ayşe Yılmaz", "tur": "is", "yakinlik": 2, "sonraki_adim": "Proje notunu gönder", "sonraki_tarih": "2026-10-19",
                    "govde": g, "etkin_son_temas": "2026-10-01"},
                   {"id": "mehmet-kaya", "ad": "Mehmet Kaya", "tur": "cevre", "yakinlik": 3, "govde": "# M\n", "etkin_son_temas": "2026-08-01", "son_temas": "2026-08-01"},
                   {"id": "selin-hoca", "ad": "Selin Hoca", "tur": "akademi", "yakinlik": 2, "sonraki_adim": "Çağrı", "sonraki_tarih": "2026-10-24", "govde": "# S\n",
                    "etkin_son_temas": "2026-10-10"}]
        veri = {"kisiler": kisiler, "iliskiler": [], "bu_hafta": c.bu_hafta(kisiler[1:], BUGUN), "ben": kisiler[0]}
        try:
            self.ozet = ag_ozet.hazirla(veri, BUGUN, [])
        except Exception as e:   # başka ajanın yarım işi: bu testin konusu değil
            self.skipTest("ag_ozet.hazirla çalışmıyor: " + type(e).__name__)

    def test_haftalik_metin(self):
        self.assertEqual(bd.metin(self.ozet)[1], "Bu hafta 3 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")
        self.assertEqual(bd.metin(self.ozet, True)[1], "Bu hafta Mehmet ve Ayşe seni bekliyor (+1). 1 söz de var. Özet Kut'ta hazır.")

    def test_gunluk_suzgec_yalniz_bugun_ve_gecikmis(self):
        s = bd._gunluk_suz(self.ozet, BUGUN)
        self.assertEqual([m["id"] for m in s["maddeler"]], ["ayse-yilmaz"])        # Selin (5 gün kaldı) ve Mehmet (temas yok) değil
        self.assertEqual(len(s["sozler"]), 1)                                       # 4 gün gecikmiş söz
        self.assertEqual(bd.metin(s, siklik="gunluk")[1], "Bugün 1 kişi ve 1 söz seni bekliyor. Özet Kut'ta hazır.")


class GerceklikTest(Temel):
    def test_modul_ag_ozet_ice_aktarmadan_yuklenir(self):
        # ag_ozet henüz yokken/yarımken bile modül içe aktarılabilir olmalı (geç içe aktarma).
        self.assertNotIn("import ag_ozet", open(bd.__file__, encoding="utf-8").read().split("def calistir")[0])

    def test_kaynakta_unicode_betik_yok_ve_ortam_adi_sabit(self):
        self.assertEqual(bd.TOAST_ORTAM, "KUT_TOAST_XML")
        self.assertTrue(bd.PS_BETIK.isascii())


if __name__ == "__main__":
    unittest.main()
