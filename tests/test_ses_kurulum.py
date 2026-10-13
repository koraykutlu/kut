"""Ses ortamı kurulumu (ag_ses_kur.py): plan/boyutlar, onay kapısı, Python arama, pip/model adımları, hata, iptal, yarım kurulum temizliği,
ortam arama sırası (ag_ses.py) ve API kapısı. pip ve model indirme GERÇEKTEN çalışmaz: alt süreçler taklit edilir."""
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
import threading
import time
import unittest
from unittest import mock

KOK_DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOK = os.path.join(KOK_DEPO, "kut")
sys.path.insert(0, KOK)
import ag_ice_aktar as ia  # noqa: E402
import ag_ses as ses  # noqa: E402
import ag_ses_kur as sk  # noqa: E402

SISTEMDE_ORIJ = sk.sistemde_python
PYEXE = "python.exe" if os.name == "nt" else "python"


class SahteSurec:
    """subprocess.Popen taklidi: satırları verir, istenirse kill() gelene kadar bekler."""
    def __init__(self, satirlar=(), kod=0, engelle=None):
        self.pid, self.returncode, self.engelle, self.oldu = 4242, None, engelle, threading.Event()
        self._satirlar, self._kod = list(satirlar), kod
        self.stdout = self._uret()

    def _uret(self):
        for s in self._satirlar:
            yield s + "\n"
        if self.engelle:
            self.engelle.set()
            self.oldu.wait(10)
            self.returncode = -9
            return
        self.returncode = self._kod

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.oldu.set()


class Temel(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        mock.patch.object(ia, "DEPO", self.d.name).start()
        mock.patch.object(ia, "AYARLAR", os.path.join(self.d.name, "ayarlar.json")).start()
        mock.patch.object(sk, "python_listesi", return_value=[{"surum": "3.12", "yol": sys.executable}]).start()
        mock.patch.object(sk, "gpu_var", return_value=False).start()
        mock.patch.object(sk, "sistemde_python", return_value=None).start()   # geliştirici makinesindeki gerçek önbelleğe bakılmasın
        mock.patch.object(sk, "_oldur", side_effect=lambda p: p.kill()).start()
        # taklit dışına çıkan her alt süreç testi bozmalı: gerçek pip/indirme asla çalışmasın
        self.popen = mock.patch.object(subprocess, "Popen", side_effect=AssertionError("gerçek alt süreç")).start()
        self.run = mock.patch.object(subprocess, "run", side_effect=AssertionError("gerçek alt süreç")).start()
        sk._onbellek.clear()
        sk._d.update(durum="yok", adim="", yuzde=0, ileti="", hata="", python_yok=False, turler=[], model="")
        sk._is.update(th=None, p=None, iptal=threading.Event(), ag=[], toplam=1)
        self.cagrilar = []

    def tearDown(self):
        th = sk._is["th"]
        if th:
            th.join(5)
        mock.patch.stopall()
        self.d.cleanup()

    def senaryo(self, pip_kod=0, model_kod=0, venv_kod=0):
        """Normal akış: venv oluşturur (python.exe dosyası), pip satırları, model ilerleme satırları."""
        def popen(arg, **kw):
            self.cagrilar.append((list(arg), kw))
            if arg[2:4] == ["-m", "venv"]:
                if venv_kod == 0:
                    yol = os.path.join(arg[4], *(("Scripts", PYEXE) if os.name == "nt" else ("bin", "python")))
                    os.makedirs(os.path.dirname(yol), exist_ok=True)
                    open(yol, "w").close()
                return SahteSurec([], venv_kod)
            if "pip" in arg[:4]:
                if pip_kod:
                    return SahteSurec(["Collecting torch==2.6.0", "ERROR: Could not find a version that satisfies the requirement"], pip_kod)
                return SahteSurec(["Collecting ema-lightning==1.1.2", "Downloading torch-2.6.0.whl (204.0 MB)", "Successfully installed ema-lightning-1.1.2"])
            if "indir" in arg:
                if model_kod:
                    return SahteSurec(["ConnectionError: getaddrinfo failed"], model_kod)
                return SahteSurec(['{"indirilen": 1048576}', '{"indirilen": 5242880, "bitti": true}'])
            raise AssertionError("beklenmeyen komut " + repr(arg))
        self.popen.side_effect = popen

    def bekle(self):
        sk._is["th"].join(10)
        self.assertFalse(sk._is["th"].is_alive())


class PlanTest(Temel):
    def test_onay_olmadan_hicbir_sey_baslamaz(self):
        for onay in (False, None, "evet", 1):
            with self.assertRaises(ValueError):
                sk.baslat(["oku"], None, onay)
        self.popen.assert_not_called()
        self.run.assert_not_called()
        self.assertEqual(sk.ozet()["durum"], "yok")
        self.assertFalse(os.path.exists(sk.klasor()))

    def test_plan_varsayilan_model_ekran_kartina_gore(self):
        p = sk.plan()
        self.assertEqual((p["yaz_model"], p["oneri"], p["gpu"]), ("small", "small", False))
        self.assertEqual(p["toplam_mb"], sk.PIP_MB["oku"] + sk.EMA_MODEL_MB + sk.PIP_MB["yaz"] + sk.MODELLER["small"]["mb"])
        self.assertTrue(p["python"]["var"])
        self.assertEqual([m["anahtar"] for m in p["modeller"] if m["oneri"]], ["small"])
        with mock.patch.object(sk, "gpu_var", return_value=True):
            g = sk.plan(["yaz"])
        self.assertEqual((g["yaz_model"], g["oneri"]), ("large-v3", "large-v3"))
        self.assertEqual(g["toplam_mb"], sk.PIP_MB["yaz"] + sk.PIP_MB["gpu"] + sk.MODELLER["large-v3"]["mb"])
        self.assertEqual(sk.plan(["yaz"], "medium")["yaz_model"], "medium")

    def test_plan_gecersiz_girdi(self):
        with self.assertRaises(ValueError):
            sk.plan(["oku", "rm -rf"])
        with self.assertRaises(ValueError):
            sk.plan(["yaz"], "../../etc")

    def test_python_yoksa_plan_haber_verir(self):
        sk.python_listesi.return_value = []
        p = sk.plan()
        self.assertFalse(p["python"]["var"])
        self.assertEqual(p["python"]["url"], "https://www.python.org/downloads/")

    def test_paket_surumleri_sabit(self):
        for ad in sk.PIP_PAKET["oku"] + sk.PIP_PAKET["yaz"] + sk.PIP_PAKET["gpu"]:
            self.assertRegex(ad, r"^[A-Za-z0-9_.-]+==\d+(\.\d+)+$", ad)
        self.assertIn("ema-lightning==1.1.2", sk.PIP_PAKET["oku"])
        self.assertTrue(any(a.startswith("normalizer-tr==0.7") for a in sk.PIP_PAKET["oku"]))


class PythonAramaTest(Temel):
    def test_surum_araligi_ve_tekrar(self):
        mock.patch.stopall()
        self.d2 = mock.patch.object(ia, "DEPO", self.d.name).start()
        cikti = {"py -3.13": "3.13", "py -3.12": "3.12", "py -3.11": "3.11"}
        gercek = os.path.abspath(sys.executable)

        def calis(arg, **kw):
            self.assertIsInstance(arg, list)
            self.assertNotIn("shell", kw)
            if arg[:2] == ["py", "-3.12"] or arg[0] == "python":
                return subprocess.CompletedProcess(arg, 0, f"3 12 {gercek}\n", "")
            if arg[:2] == ["py", "-3"]:
                return subprocess.CompletedProcess(arg, 0, f"3 9 {gercek}\n", "")   # çok eski → reddedilir
            if arg[:2] == ["py", "-3.13"]:
                return subprocess.CompletedProcess(arg, 0, f"3 14 {gercek}\n", "")   # çok yeni → reddedilir
            raise FileNotFoundError(arg[0])
        sk._onbellek.clear()
        with mock.patch.object(subprocess, "run", side_effect=calis), mock.patch.object(sk, "_adaylar", return_value=[
                ["py", "-3.13"], ["py", "-3.12"], ["py", "-3"], ["python"], ["yok-boyle-bir-python"]]):
            liste = sk.python_listesi()
        self.assertEqual([b["surum"] for b in liste], ["3.12"])   # aynı yol bir kez, 3.9 ve 3.14 yok, olmayan komut atlandı

    def test_frozen_kendi_exesini_aday_yapmaz(self):
        mock.patch.stopall()
        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertNotIn([sys.executable], sk._adaylar())
        self.assertIn([sys.executable] if "pythonw" not in sys.executable.lower() else [sys.executable.replace("pythonw", "python")], sk._adaylar())


class KurulumAkisiTest(Temel):
    def test_tam_kurulum_komutlari_ve_kayit(self):
        self.senaryo()
        d = sk.baslat(["oku", "yaz"], "small", True)
        self.assertEqual(d["durum"], "kuruluyor")
        self.bekle()
        o = sk.ozet()
        self.assertEqual((o["durum"], o["yuzde"], o["hata"]), ("hazir", 100, ""))
        self.assertEqual(o["kurulu"], {"oku": True, "yaz": True})
        self.assertEqual(o["model"], "small")
        # sıra: oku için venv, pip (hash'li), pip (bağımlılıklar), model; yaz için venv, pip, model
        komutlar = [c[0] for c in self.cagrilar]
        self.assertEqual(len(komutlar), 7)
        self.assertEqual(komutlar[0][1:4], ["-I", "-m", "venv"])    # python yalıtılmış kip
        self.assertEqual(komutlar[4][1:4], ["-I", "-m", "venv"])
        for arg, kw in self.cagrilar:
            self.assertIsInstance(arg, list)                       # argüman listesi
            self.assertFalse(kw.get("shell"))                      # kabuk yok
            self.assertNotIn("HF_HUB_OFFLINE", kw["env"])          # indirme kipinde çevrimdışı kilit yok
        pip_hash, pip_oku, pip_yaz = komutlar[1], komutlar[2], komutlar[5]
        for pip in (pip_hash, pip_oku, pip_yaz):
            self.assertEqual(pip[1:6], ["-I", "-m", "pip", "--isolated", "install"])
            self.assertIn("--only-binary", pip)
            self.assertEqual(pip[pip.index("--only-binary") + 1], ":all:")
        self.assertIn("--require-hashes", pip_hash)
        self.assertIn("--no-deps", pip_hash)
        self.assertNotIn("--require-hashes", pip_yaz)
        for paket in sk.EMA_BAGIMLILIK:
            self.assertIn(paket, pip_oku)
        for paket in sk.PIP_PAKET["yaz"]:
            self.assertIn(paket, pip_yaz)
        self.assertNotIn("nvidia-cublas-cu12==12.9.2.10", pip_yaz)   # ekran kartı yok → GPU kitaplığı yok
        indir = komutlar[3]
        self.assertEqual(indir[1:3], ["-I", sk.ISCI])
        self.assertEqual(indir[3:], ["indir", "oku", "", sk.EMA_REPO, sk.EMA_SHA])   # commit sha'ya sabit
        self.assertEqual(komutlar[6][3:], ["indir", "yaz", "small", sk.MODELLER["small"]["repo"], sk.MODELLER["small"]["sha"]])
        self.assertEqual(self.cagrilar[3][1]["env"]["HF_HOME"], sk.hf_klasor())
        # kayıt ve ortam bulma
        b = sk.kurulu_bilgi()
        self.assertEqual(b["yaz"]["model"], "small")
        self.assertEqual(sk.python_yolu("oku"), sk.venv_python("oku"))
        self.assertEqual(sk.yaz_model(), "small")
        self.assertTrue(sk.kut_mu(sk.venv_python("yaz")))
        self.assertEqual(sk.isci_ortam(sk.venv_python("yaz")), {"HF_HOME": sk.hf_klasor()})
        self.assertEqual(sk.isci_ortam(sys.executable), {})
        for t in ("oku", "yaz"):
            self.assertFalse(os.path.exists(os.path.join(sk._tur_klasor(t), ".kuruluyor")))
        # tekrar istenirse zaten kurulu
        with self.assertRaises(ValueError):
            sk.baslat(["oku"], None, True)

    def test_ekran_kartiyla_gpu_paketleri(self):
        self.senaryo()
        with mock.patch.object(sk, "gpu_var", return_value=True):
            sk.baslat(["yaz"], "large-v3", True)
            self.bekle()
        pip = self.cagrilar[1][0]   # yaz: venv, pip
        self.assertIn("nvidia-cublas-cu12==12.9.2.10", pip)
        self.assertIn("nvidia-cudnn-cu12==9.27.0.42", pip)
        self.assertTrue(sk.kurulu_bilgi()["yaz"]["gpu"])

    def test_kurulu_yaz_icin_yalniz_model_degisir(self):
        self.senaryo()
        sk.baslat(["yaz"], "small", True)
        self.bekle()
        self.cagrilar.clear()
        sk.baslat(["yaz"], "medium", True)
        self.bekle()
        self.assertEqual(len(self.cagrilar), 1)   # venv/pip yok, yalnız model
        self.assertEqual(self.cagrilar[0][0][3:], ["indir", "yaz", "medium", sk.MODELLER["medium"]["repo"], sk.MODELLER["medium"]["sha"]])
        self.assertEqual(sk.yaz_model(), "medium")

    def test_python_yok_acik_yonerge(self):
        sk.python_listesi.return_value = []
        sk.baslat(["oku"], None, True)
        self.bekle()
        o = sk.ozet()
        self.assertEqual(o["durum"], "hata")
        self.assertTrue(o["python_yok"])
        self.assertIn("python.org/downloads", o["hata"])
        self.popen.assert_not_called()
        self.assertFalse(sk.kurulu("oku"))

    def test_pip_hatasi_yarim_ortami_siler(self):
        self.senaryo(pip_kod=1)
        sk.baslat(["oku"], None, True)
        self.bekle()
        o = sk.ozet()
        self.assertEqual(o["durum"], "hata")
        self.assertIn("Python 3.11", o["hata"])   # "paket bulunamadı" için anlaşılır yönerge
        self.assertFalse(os.path.exists(sk._tur_klasor("oku")))
        self.assertEqual(sk.kurulu_bilgi(), {})
        self.assertFalse(sk.ozet()["kurulu"]["oku"])

    def test_model_indirme_hatasi_baglanti_mesaji(self):
        self.senaryo(model_kod=1)
        sk.baslat(["oku"], None, True)
        self.bekle()
        o = sk.ozet()
        self.assertEqual(o["durum"], "hata")
        self.assertIn("İnternet", o["hata"])
        self.assertFalse(os.path.exists(sk._tur_klasor("oku")))

    def test_baska_kurulum_sirasinda_reddedilir(self):
        engel = threading.Event()

        def popen(arg, **kw):
            return SahteSurec([], 0, engelle=engel)
        self.popen.side_effect = popen
        sk.baslat(["oku"], None, True)
        engel.wait(5)
        with self.assertRaises(ValueError):
            sk.baslat(["yaz"], None, True)
        with self.assertRaises(ValueError):
            sk.kaldir()
        sk.iptal()

    def test_disk_yetersizse_baslamaz(self):
        with mock.patch.object(sk, "plan", return_value={"bos_disk_mb": 10, "gerekli_disk_mb": 2000, "toplam_mb": 1000}):
            with self.assertRaises(ValueError) as h:
                sk.baslat(["oku"], None, True)
        self.assertIn("Diskte", str(h.exception))
        self.popen.assert_not_called()


class IptalVeTemizlikTest(Temel):
    def test_iptal_sureci_oldurur_ve_ortami_siler(self):
        engel = threading.Event()

        def popen(arg, **kw):
            if arg[2:4] == ["-m", "venv"]:
                yol = os.path.join(arg[4], *(("Scripts", PYEXE) if os.name == "nt" else ("bin", "python")))
                os.makedirs(os.path.dirname(yol), exist_ok=True)
                open(yol, "w").close()
                return SahteSurec([], 0)
            return SahteSurec(["Collecting torch"], 0, engelle=engel)   # pip takılır
        self.popen.side_effect = popen
        sk.baslat(["oku"], None, True)
        self.assertTrue(engel.wait(5))
        self.assertTrue(os.path.exists(os.path.join(sk._tur_klasor("oku"), ".kuruluyor")))
        o = sk.iptal()
        self.assertFalse(o["calisiyor"])
        self.assertEqual(o["durum"], "iptal")
        self.assertFalse(os.path.exists(sk._tur_klasor("oku")))
        self.assertEqual(sk.kurulu_bilgi(), {})

    def test_yarida_kalan_kurulum_temizlenir(self):
        # Kut kurulum sırasında kapandı: .kuruluyor işareti ve yarım venv kaldı
        os.makedirs(os.path.join(sk._tur_klasor("yaz"), ".venv", "Scripts"))
        open(os.path.join(sk._tur_klasor("yaz"), ".kuruluyor"), "w").close()
        sk._bilgi_yaz("yaz", {"model": "small"})
        self.assertFalse(sk.kurulu("yaz"))   # python.exe yok → kurulu sayılmaz
        sk.ozet()   # GET yoklaması dizin silmez (O4)
        self.assertTrue(os.path.exists(sk._tur_klasor("yaz")))
        sk._yarida_temizle()   # baslat() içinde çalışır
        self.assertFalse(os.path.exists(sk._tur_klasor("yaz")))
        self.assertEqual(sk.kurulu_bilgi(), {})

    def _isaret(self, tur, pid, zaman):
        os.makedirs(os.path.join(sk._tur_klasor(tur), ".venv"), exist_ok=True)
        with open(os.path.join(sk._tur_klasor(tur), ".kuruluyor"), "w") as f:
            json.dump({"pid": pid, "zaman": zaman}, f)

    def test_baska_canli_kut_kurulumuna_dokunulmaz(self):
        self._isaret("yaz", 424242, time.time())
        with mock.patch.object(sk, "_pid_canli", return_value=True):
            sk._yarida_temizle()
            self.assertTrue(os.path.exists(sk._tur_klasor("yaz")))
            with self.assertRaises(ValueError) as h:
                sk.baslat(["yaz"], None, True)
            self.assertIn("Başka bir Kut", str(h.exception))
            with self.assertRaises(ValueError):
                sk.kaldir()
            self.assertTrue(os.path.exists(sk._tur_klasor("yaz")))
            self.popen.assert_not_called()

    def test_olu_pid_ya_da_eski_isaret_temizlenir(self):
        self._isaret("yaz", 424242, time.time())
        with mock.patch.object(sk, "_pid_canli", return_value=False):
            sk._yarida_temizle()
        self.assertFalse(os.path.exists(sk._tur_klasor("yaz")))
        self._isaret("oku", 424242, time.time() - sk.ISARET_ESKI_SN - 10)   # PID canlı görünse de eskimiş
        with mock.patch.object(sk, "_pid_canli", return_value=True):
            sk._yarida_temizle()
        self.assertFalse(os.path.exists(sk._tur_klasor("oku")))

    def test_isaret_pid_ve_zaman_yazar(self):
        self.senaryo()
        engel = threading.Event()
        eski = self.popen.side_effect

        def popen(arg, **kw):
            if "pip" in arg[:4]:
                with open(os.path.join(sk._tur_klasor("yaz"), ".kuruluyor"), encoding="utf-8") as f:
                    self.isaret = json.load(f)
            return eski(arg, **kw)
        self.popen.side_effect = popen
        sk.baslat(["yaz"], "small", True)
        self.bekle()
        self.assertEqual(self.isaret["pid"], os.getpid())
        self.assertLess(abs(self.isaret["zaman"] - time.time()), 60)

    def test_yarim_model_indirmesi_hatada_ve_iptalde_silinir(self):
        repo_k = sk._repo_klasor(sk.MODELLER["small"]["repo"])

        def popen(arg, **kw):
            if arg[2:4] == ["-m", "venv"]:
                yol = os.path.join(arg[4], *(("Scripts", PYEXE) if os.name == "nt" else ("bin", "python")))
                os.makedirs(os.path.dirname(yol), exist_ok=True)
                open(yol, "w").close()
                return SahteSurec([], 0)
            if "indir" in arg:
                os.makedirs(os.path.join(repo_k, "blobs"), exist_ok=True)
                open(os.path.join(repo_k, "blobs", "abc.incomplete"), "w").write("yarim")
                return SahteSurec(["ConnectionError: getaddrinfo failed"], 1)
            return SahteSurec(["Collecting x"], 0)
        self.popen.side_effect = popen
        sk.baslat(["yaz"], "small", True)
        self.bekle()
        self.assertEqual(sk.ozet()["durum"], "hata")
        self.assertFalse(os.path.exists(repo_k))   # yarım .incomplete dahil silindi
        # daha önce tamamen inmiş bir depo silinmez, yalnız .incomplete dosyaları gider
        os.makedirs(os.path.join(repo_k, "snapshots", "abc"), exist_ok=True)
        open(os.path.join(repo_k, "snapshots", "abc", "model.bin"), "w").write("tam")
        sk.baslat(["yaz"], "small", True)
        self.bekle()
        self.assertTrue(os.path.exists(os.path.join(repo_k, "snapshots", "abc", "model.bin")))
        self.assertFalse(os.path.exists(os.path.join(repo_k, "blobs", "abc.incomplete")))

    def test_iptal_mesaji_silinemeyen_dosyayi_dogru_soyler(self):
        # _calis içindeki Iptal dalı: silinemeyen dosya varsa "silindi" demez
        with mock.patch.object(sk, "python_bul", return_value={"yol": "py", "surum": "3.12"}), mock.patch.object(sk, "_kur_tur", side_effect=sk.Iptal()):
            sk._is.update(kalan=["/ses/hf/x.incomplete"], tamam=["oku"])
            sk._calis(["yaz"], "small", False)
        d = sk.ozet()
        self.assertEqual(d["durum"], "iptal")
        self.assertIn("silinemedi", d["ileti"])
        self.assertIn("oku", d["ileti"])

    def test_pip_izole_ve_hash_sabitleme(self):
        for ad, hashler in sk.PIP_HASH.items():
            self.assertRegex(ad, r"^[A-Za-z0-9_.-]+==\d+(\.\d+)+$")
            self.assertTrue(hashler)
            for h in hashler:
                self.assertRegex(h, r"^[0-9a-f]{64}$")
        self.assertEqual(set(sk.PIP_HASH), {"ema-lightning==1.1.2", "normalizer-tr==0.7.0"})
        for repo_sha in [sk.EMA_SHA] + [m["sha"] for m in sk.MODELLER.values()]:
            self.assertRegex(repo_sha, r"^[0-9a-f]{40}$")
        k = os.path.join(self.d.name, "hashdeneme")
        os.makedirs(k)
        komutlar = sk._pip_adimlari("oku", "vpy", k, False)
        self.assertEqual(len(komutlar), 2)
        icerik = open(os.path.join(k, "gereksinim-hash.txt"), encoding="utf-8").read()
        self.assertIn("ema-lightning==1.1.2 --hash=sha256:", icerik)
        self.assertIn("normalizer-tr==0.7.0 --hash=sha256:", icerik)
        with mock.patch.dict(os.environ, {"PIP_INDEX_URL": "https://kotu.example/simple", "PIP_EXTRA_INDEX_URL": "https://kotu2.example", "pip_trusted_host": "kotu.example", "HF_ENDPOINT": "https://kotu.example"}):
            e = sk._env()
        for anahtar in e:
            self.assertFalse(anahtar.upper().startswith("PIP_") and anahtar.upper() not in ("PIP_DISABLE_PIP_VERSION_CHECK", "PIP_NO_INPUT"), anahtar)
        self.assertNotIn("HF_ENDPOINT", e)

    def test_kaldir_yalniz_ses_klasorunu_siler(self):
        self.senaryo()
        sk.baslat(["oku"], None, True)
        self.bekle()
        komsu = os.path.join(self.d.name, "ayarlar.json")
        open(komsu, "w").write("{}")
        o = sk.kaldir()
        self.assertFalse(os.path.exists(sk.klasor()))
        self.assertTrue(os.path.exists(komsu))
        self.assertEqual(o["durum"], "yok")
        self.assertEqual(o["kurulu"], {"oku": False, "yaz": False})

    def test_kaldir_beklenmeyen_klasorde_reddeder(self):
        with mock.patch.object(sk, "klasor", return_value=self.d.name):
            with self.assertRaises(ValueError):
                sk.kaldir()
        self.assertTrue(os.path.isdir(self.d.name))


class AyarTest(Temel):
    def test_bir_daha_sorma(self):
        self.assertEqual(sk.soru(), "")
        sk.soru_yaz("sorma")
        self.assertEqual(sk.soru(), "sorma")
        self.assertEqual(ia.ayarlar()["ses"]["kurulum_sorusu"], "sorma")
        self.assertEqual(ses.durum()["teklif"], False)
        sk.soru_yaz("sor")
        self.assertEqual(sk.soru(), "")
        with self.assertRaises(ValueError):
            sk.soru_yaz("belki")

    def test_mevcut_ses_ayarlari_korunur(self):
        ia.ayar_yaz({"ses": {"mikrofon": "izinli"}, "ben_adlari": []})
        sk.soru_yaz("sorma")
        self.assertEqual(ia.ayarlar()["ses"], {"mikrofon": "izinli", "kurulum_sorusu": "sorma"})


class OrtamSirasiTest(Temel):
    """Arama sırası: ayardaki açık yol → Kut'un kurduğu ortam → eski bilinen yollar → sistem Python'u."""
    def setUp(self):
        super().setUp()
        self.kok = os.path.join(self.d.name, "kasa", "kut", "kod")
        os.makedirs(self.kok)
        mock.patch.object(ses, "KOK", self.kok).start()
        self.bilinen = os.path.join(self.d.name, "kasa", ".claude", "tools", "ema", ".venv", ses.PY)
        os.makedirs(os.path.dirname(self.bilinen))
        open(self.bilinen, "w").close()
        self.acik = os.path.join(self.d.name, "benim-python.exe")
        open(self.acik, "w").close()

    def kut_kur(self):
        yol = sk.venv_python("oku")
        os.makedirs(os.path.dirname(yol))
        open(yol, "w").close()
        sk._bilgi_yaz("oku", {"kapsam": 1})
        return yol

    def test_siralama(self):
        sistem = os.path.join(self.d.name, "sistem-python.exe")
        open(sistem, "w").close()
        with mock.patch.object(sk, "sistemde_python", return_value=sistem):
            self.assertEqual(ses.python_yolu("oku"), self.bilinen)          # yalnız eski bilinen yol
            self.assertEqual(ses.python_yolu("yaz"), sistem)                # hiçbiri yok → sistem Python'u
            kut = self.kut_kur()
            self.assertEqual(ses.python_yolu("oku"), kut)                   # Kut'un kurduğu, bilinen yoldan önce
            ia.ayar_yaz({"ses": {"oku_python": self.acik}})
            self.assertEqual(ses.python_yolu("oku"), self.acik)             # ayardaki açık yol hepsinden önce
            ia.ayar_yaz({"ses": {"oku_python": os.path.join(self.d.name, "yok.exe")}})
            self.assertIsNone(ses.python_yolu("oku"))                       # açık yol bozuksa sessizce başkasına geçilmez

    def test_hicbiri_yoksa_ses_kapali_ve_teklif(self):
        os.remove(self.bilinen)
        with mock.patch.object(sk, "sistemde_python", return_value=None):
            d = ses.durum()
        self.assertEqual((d["oku"], d["yaz"]), (False, False))
        self.assertEqual(d["eksik"], ["oku", "yaz"])
        self.assertTrue(d["teklif"])
        self.assertEqual(d["kurulum"]["durum"], "yok")

    def test_isci_kut_ortaminda_hf_home_ve_model(self):
        kut = self.kut_kur()
        sk._bilgi_yaz("yaz", {"model": "medium"})
        yol = sk.venv_python("yaz")
        os.makedirs(os.path.dirname(yol))
        open(yol, "w").close()
        ciktilar = []

        class P:
            stdout = mock.Mock(readline=lambda: b'{"hazir": true}\n')
        self.popen.side_effect = lambda arg, **kw: ciktilar.append((arg, kw)) or P()
        for tur in ("oku", "yaz"):
            ses.Isci(tur)._baslat()
        (a_oku, kw_oku), (a_yaz, kw_yaz) = ciktilar
        self.assertEqual(a_oku[0], kut)
        self.assertEqual(kw_oku["env"]["HF_HOME"], sk.hf_klasor())
        self.assertEqual(a_yaz[-2:], ["medium", "int8_float16"])            # kurulu model kullanılır
        ia.ayar_yaz({"ses": {"yaz_model": "large-v3"}})
        ses.Isci("yaz")._baslat()
        self.assertEqual(ciktilar[-1][0][-2], "large-v3")                   # ayardaki açık model kurulu olandan önce
        # bilinen yol (geliştirici makinesi) için ortam değişmez
        os.remove(kut)
        ia.ayar_yaz({})
        ses.Isci("oku")._baslat()
        self.assertIsNone(ciktilar[-1][1]["env"])


class SistemPythonuTest(Temel):
    def test_paketler_ve_onbellek_varsa(self):
        mock.patch.object(sk, "sistemde_python", SISTEMDE_ORIJ).start()
        hf = os.path.join(self.d.name, "hf-hub")
        with mock.patch.dict(os.environ, {"HF_HUB_CACHE": hf}):
            self.assertIsNone(sk.sistemde_python("oku"))   # model önbelleği yok → çalışmaz, alt süreç da çalışmaz
            self.popen.assert_not_called()
            snap = os.path.join(hf, "models--canberkkkkkk--ema-lightning", "snapshots", "abc")
            os.makedirs(snap)
            mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0)).start()
            self.assertEqual(sk.sistemde_python("oku"), sys.executable)
            sk._onbellek.clear()
            subprocess.run.return_value = subprocess.CompletedProcess([], 1)   # paket yok
            self.assertIsNone(sk.sistemde_python("oku"))


class IsciIndirTest(unittest.TestCase):
    def test_indir_kipinde_cevrimdisi_kilit_yok_digerinde_var(self):
        isci = os.path.join(KOK, "ag_ses_isci.py")
        kod = "import sys,os,runpy;sys.argv=['x']+sys.argv[1:];os.environ.pop('HF_HUB_OFFLINE',None);" \
              "m=runpy.run_path(%r,run_name='kontrol');print(os.environ.get('HF_HUB_OFFLINE'),file=sys.__stdout__)" % isci
        for arg, beklenen in ((["indir"], "None"), (["yaz"], "1")):
            p = subprocess.run([sys.executable, "-I", "-c", kod, *arg], capture_output=True, text=True, timeout=60)
            self.assertEqual(p.stdout.strip().splitlines()[-1], beklenen, p.stderr)


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SesKurulumApiTest(unittest.TestCase):
    """Ayrı süreçte sunucu, geçici LOCALAPPDATA: kilit, anahtar, yerel kaynak ve onay kapıları. İndirme başlatılmaz."""
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

    def test_kapilar(self):
        uclar = [("GET", "/api/ses/kurulum", None)] + [("POST", "/api/ses/kurulum/" + u, {}) for u in ("baslat", "iptal", "kaldir", "ayar")]
        for y, yol, g in uclar:
            self.assertEqual(self.istek(y, yol, g)[0], 401 if y == "GET" else 403, (y, yol))   # kilitli / anahtarsız
        kod, cerez, _ = self.istek("POST", "/api/kilit/kur", {"pin": "4321", "pin2": "4321"})
        self.assertEqual(kod, 200)
        cerez = {"Cookie": cerez.split(";")[0]}
        anahtar = re.search(r'"anahtar":\s*"([^"]+)"', self.istek("GET", "/", None, cerez)[2].decode("utf-8")).group(1)
        a = {**cerez, "X-Ag-Anahtar": anahtar}
        for y, yol, g in uclar:
            self.assertEqual(self.istek(y, yol, g, cerez)[0], 403, (y, yol))                    # oturum var, anahtar yok
        for u in ("baslat", "iptal", "kaldir", "ayar"):
            self.assertEqual(self.istek("POST", "/api/ses/kurulum/" + u, {}, {"X-Ag-Anahtar": anahtar})[0], 401)   # anahtar var, oturum yok
            self.assertEqual(self.istek("POST", "/api/ses/kurulum/" + u, {"onay": True}, {**a, "Origin": "http://evil.example"})[0], 403)   # yabancı kaynak
        self.assertEqual(self.istek("GET", "/api/ses/kurulum", None, cerez)[0], 403)
        self.assertEqual(self.istek("PUT", "/api/ses/kurulum/baslat", {}, a)[0] in (404, 501), True)   # yalnız POST
        # onaysız başlatma reddedilir, hiçbir şey indirilmez
        for govde in ({}, {"onay": False}, {"onay": "true"}, {"parcalar": ["oku"]}):
            kod, _, v = self.istek("POST", "/api/ses/kurulum/baslat", govde, a)
            self.assertEqual(kod, 400, govde)
            self.assertIn("onay", json.loads(v)["hata"])
        kod, _, v = self.istek("GET", "/api/ses/kurulum", None, a)
        self.assertEqual(kod, 200)
        d = json.loads(v)
        self.assertEqual(d["durum"], "yok")
        self.assertFalse(d["calisiyor"])
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.ayar), "ses")))
        # sorma cevabı ayara yazılır; sayfa durumu teklifi kapatır
        self.assertEqual(self.istek("POST", "/api/ses/kurulum/ayar", {"cevap": "belki"}, a)[0], 400)
        self.assertEqual(self.istek("POST", "/api/ses/kurulum/ayar", {"cevap": "sorma"}, a)[0], 200)
        with open(self.ayar, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["ses"]["kurulum_sorusu"], "sorma")
        self.assertFalse(json.loads(self.istek("GET", "/api/ses", None, a)[2])["teklif"])
        # plan yoklaması ağa çıkmaz ve boyut verir
        kod, _, v = self.istek("GET", "/api/ses/kurulum?plan=1&parca=yaz&model=medium", None, a)
        self.assertEqual(kod, 200)
        plan = json.loads(v)["plan"]
        self.assertEqual((plan["parcalar"], plan["yaz_model"]), (["yaz"], "medium"))
        self.assertGreater(plan["toplam_mb"], 1500)
        self.assertEqual(self.istek("POST", "/api/ses/kurulum/kaldir", {}, a)[0], 200)   # kurulu bir şey yok: zararsız


if __name__ == "__main__":
    unittest.main()
