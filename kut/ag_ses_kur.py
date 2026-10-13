"""Kut ses ortamı kurulumu: Whisper (konuşmayı yazıya) ve EMA Lightning (Türkçe ses) için kullanıcının onayıyla yerel kurulum.

Kut kendi Python'unda paket kurmaz (Kut.exe içinden pip çalışmaz); sistemdeki Python 3.11–3.13 ile Kut'un veri klasöründe (%LOCALAPPDATA%\\agim\\ses)
iki ayrı sanal ortam kurar: ses/oku/.venv (EMA) ve ses/yaz/.venv (faster-whisper). Model ağırlıkları ses/hf altına iner (HF_HOME); işçi
süreçler (ag_ses_isci.py) sonradan çevrimdışı çalışır. Paket sürümleri sabittir (bu dosyada); yalnız PyPI ve Hugging Face'e gidilir.

Gizlilik: hiçbir şey kullanıcı "Evet" demeden indirilmez (baslat onay ister). Kurulum bittikten sonra ses ve metin internete gitmez.
Durum yalnız bellekte tutulur; yarıda kalan kurulum (Kut kapandı, elektrik gitti) bir sonraki `baslat`ta temizlenir (`.kuruluyor` işareti PID ve zaman taşır:
başka canlı bir Kut'un süren kurulumuna dokunulmaz; GET yoklaması dizin silmez). İptal ve hata alt süreci öldürür, o kurulumda açılan ortamı ve yarım model
indirmelerini (.incomplete) siler. pip `-I`/`--isolated` ile çalışır, PIP_* ortam değişkenleri aktarılmaz; küçük ve yeni paketler `--require-hashes`, modeller commit sha ile sabittir. Sabit sürümler geliştirici makinesinde çalışan ortamlardan alındı (ema-lightning 1.1.2, faster-whisper 1.2.1).
"""
import atexit
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import ag_ice_aktar as ia

KOK = os.path.dirname(os.path.abspath(__file__))
ISCI = os.path.join(KOK, "ag_ses_isci.py")
PY_URL = "https://www.python.org/downloads/"
PY_ASGARI, PY_AZAMI = (3, 11), (3, 13)   # ema-lightning ≥3.11; sabitlenmiş paketlerin tekerlekleri 3.13'e kadar sınanmış
TURLER = ("oku", "yaz")
KAPSAM_SURUM = 1   # kurulu.json biçim sürümü

# sabit paket sürümleri (hepsi PyPI; kaynak koddan derleme yok: --only-binary)
PIP_PAKET = {
    "oku": ["ema-lightning==1.1.2", "normalizer-tr==0.7.0", "torch==2.6.0"],
    "yaz": ["faster-whisper==1.2.1", "ctranslate2==4.8.2"],
    "gpu": ["nvidia-cublas-cu12==12.9.2.10", "nvidia-cudnn-cu12==9.27.0.42"],   # yalnız Windows + NVIDIA kartı; ctranslate2 CUDA kitaplıkları
}
PYTORCH_CPU = "https://download.pytorch.org/whl/cpu"   # yalnız Linux: PyPI'daki torch CUDA bağımlılıklarını da çeker; resmi işlemci deposu
# ema-lightning ve normalizer-tr 2-3 günlük (10-11 Ekim 2026) küçük paketlerdir: tekerlek sha256 değerleri PyPI JSON API'sinden
# (https://pypi.org/pypi/<paket>/<sürüm>/json) alındı ve `--require-hashes` ile doğrulanır. Torch/CUDA ve faster-whisper bağımlılık ağacı
# platform başına çok büyük olduğundan yalnız sürümle sabitlenir (hash yok); bkz. README "Ses kurulumunun güvenliği".
PIP_HASH = {
    "ema-lightning==1.1.2": ["821c737587d2db32f83a863abadd455610720d359872f6fb8b08ddd1c9b84840"],   # py3-none-any tekerleği
    "normalizer-tr==0.7.0": [
        "0b4246cbea8a41e01d5d48204d058348c14f0256b5835902d73f094f430aa2d1", "63003874f3294b13755ba666b29062e6d855cd4d005614fa323950074b510260",
        "f4f8075bbc2519b4a64083bee8adc4ed90bb6a28a99f13e35aa1629c3d05fa27", "fc179f78dfec681923b3c7314cf9796c456ea0c036faa4db0208bf81027ec4ba",
        "d3780e3e9b60ece4aa7eff711e4c812a5ec5511a689e52547488ffb9a6d8dc45", "2ff1551ce0c3230f12aeee629f3b100b67ee0ed042b9705839c29a7afb6c80d6",
        "7ef7fe39948462564f7179f096fa434da95e4bbb449d4aef4be04d20cc08a659", "47c42c552b407eefe2602b57d1f31567a82d406ca78842814aa02e5f08703d74",
        "034cef1eddd844ad3c940242a075ada6c3d2c59bc867297c3df6d50a2bda813a", "603baa57a84d890bdcda1f8f88ce915edbb09bbaf84fd81092aab9f5d9539cbb",
        "b55c25299b43be4b73adaff50e807e02742b4584c65d015f3db70d1424e8a754", "86841fb1ea86914c96f10d04cc371b54936a141d0381a641648f0c5489d066bc",
        "3ad2921b7aabe08f89e8fc3a49bd9deb2f2bbbe617c656d082895c82296d8c4c", "3f53939f2db8516208adaea0e9d6792a96260430cfb4d06c79f3188fa647cee4",
        "b14857623e73f9be9681c71de44140e314d9de4c6c05ad665ad68c8a267a8271", "65ac3d4edc29ae70585a5e50e21007cbb8f8d28853f8378d45b8ccbe6d5bf837"],
}
# ema-lightning 1.1.2'nin gerekleri (PyPI requires_dist): normalizer-tr yukarıda hash'li; geri kalanı sürümle sabit değil
EMA_BAGIMLILIK = ["torch==2.6.0", "huggingface-hub>=0.20", "numpy>=1.24"]
EMA_REPO = "canberkkkkkk/ema-lightning"
# Hugging Face commit sha'ları (https://huggingface.co/api/models/<repo> → "sha", 13 Ekim 2026'da doğrulandı); hf_hub_download/snapshot_download
# revision=<sha> ile çağrılır: depo sonradan değişse de aynı dosyalar iner
EMA_SHA = "7a6ba1ad216bb2f1da9863f80ac8770a6a807632"
# yaklaşık indirme boyutları (MB); kullanıcıya gösterilir. Whisper boyutları Hugging Face önbelleğinde ölçülen (small 464, large-v3 ~2,9 GB)
PIP_MB = {"oku": 300, "yaz": 120, "gpu": 1200}
EMA_MODEL_MB = 35
MODELLER = {
    "small": {"ad": "Whisper small", "repo": "Systran/faster-whisper-small", "mb": 470, "sha": "536b0662742c02347bc0e980a01041f333bce120",
              "not": "Hızlı; işlemcide de rahat çalışır, Türkçede daha çok yanlış yazar."},
    "medium": {"ad": "Whisper medium", "repo": "Systran/faster-whisper-medium", "mb": 1530, "sha": "08e178d48790749d25932bbc082711ddcfdfbc4f",
               "not": "Dengeli; işlemcide yavaş, ekran kartında hızlı."},
    "large-v3": {"ad": "Whisper large-v3", "repo": "Systran/faster-whisper-large-v3", "mb": 2950, "sha": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
                 "not": "En doğru Türkçe; NVIDIA ekran kartı önerilir, işlemcide yavaştır."},
}
VENV_MB = 20
BEKLENEN_SATIR = {"oku": 24, "yaz": 30}   # pip "Collecting/Downloading" satır sayısı → kaba ilerleme

_kilit = threading.RLock()
_d = {"durum": "yok", "adim": "", "yuzde": 0, "ileti": "", "hata": "", "python_yok": False, "turler": [], "model": ""}
_is = {"th": None, "iptal": threading.Event(), "p": None, "ag": [], "toplam": 1, "tamam": [], "kalan": []}
_onbellek = {}


class Iptal(Exception):
    pass


class Hata(Exception):
    def __init__(self, mesaj, python_yok=False):
        super().__init__(mesaj)
        self.python_yok = python_yok


# ---- yollar ve kurulu bilgisi ----
def klasor():
    return os.path.join(ia.DEPO, "ses")


def _tur_klasor(tur):
    return os.path.join(klasor(), tur)


def venv_python(tur):
    return os.path.join(_tur_klasor(tur), ".venv", *(("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")))


def hf_klasor():
    return os.path.join(klasor(), "hf")


def _bilgi_yolu():
    return os.path.join(klasor(), "kurulu.json")


def kurulu_bilgi():
    b = ia._json_oku(_bilgi_yolu(), {})
    return b if isinstance(b, dict) else {}


def kurulu(tur):
    return isinstance(kurulu_bilgi().get(tur), dict) and os.path.isfile(venv_python(tur))


def python_yolu(tur):
    """Kut'un kurduğu ortamın Python'u; kurulu değilse None."""
    return venv_python(tur) if kurulu(tur) else None


def yaz_model():
    b = kurulu_bilgi().get("yaz")
    return b.get("model") if isinstance(b, dict) and kurulu("yaz") else None


def kut_mu(py):
    """Verilen Python Kut'un kendi kurduğu ortamda mı?"""
    try:
        return os.path.commonpath([os.path.abspath(py), os.path.abspath(klasor())]) == os.path.abspath(klasor())
    except ValueError:
        return False


def isci_ortam(py):
    """İşçi sürece eklenecek ortam değişkenleri: Kut'un ortamında model önbelleği Kut'un klasöründedir."""
    return {"HF_HOME": hf_klasor()} if kut_mu(py) else {}


def _bilgi_yaz(tur, bilgi):
    b = kurulu_bilgi()
    if bilgi is None:
        b.pop(tur, None)
    else:
        b[tur] = bilgi
    os.makedirs(klasor(), exist_ok=True)
    ia._json_yaz(_bilgi_yolu(), b)


# ---- kullanıcının bu soruya cevabı (Bir daha sorma) ----
def soru():
    return "sorma" if (ia.ayarlar().get("ses") or {}).get("kurulum_sorusu") == "sorma" else ""


def soru_yaz(cevap):
    if cevap not in ("sorma", "sor"):
        raise ValueError("cevap: sorma | sor")
    a = ia.ayarlar()
    s = a.setdefault("ses", {})
    if cevap == "sorma":
        s["kurulum_sorusu"] = "sorma"
    else:
        s.pop("kurulum_sorusu", None)
    ia.ayar_yaz(a)
    return {"soru": soru()}


# ---- sistemdeki Python'lar ve ekran kartı (kısa süre önbellekte) ----
def _onbellekli(anahtar, uret, sure=120):
    t, v = _onbellek.get(anahtar, (0, None))
    if time.time() - t > sure:
        v = uret()
        _onbellek[anahtar] = (time.time(), v)
    return v


def _bayrak():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _adaylar():
    if os.name == "nt":
        a = [["py", "-3.13"], ["py", "-3.12"], ["py", "-3.11"], ["py", "-3"], ["python"], ["python3"]]
    else:
        a = [["python3.13"], ["python3.12"], ["python3.11"], ["python3"], ["python"]]
    if not getattr(sys, "frozen", False):   # Kut kaynaktan çalışıyorsa kendi Python'u da aday (Kut.exe'ninki değil)
        exe = sys.executable
        if os.path.basename(exe).lower() == "pythonw.exe":
            exe = os.path.join(os.path.dirname(exe), "python.exe")
        a.append([exe])
    return a


def _sorgula(arg):
    """Adayın (sürüm, yol) bilgisi; çalışmıyorsa ya da aralık dışındaysa None."""
    try:
        p = subprocess.run(arg + ["-I", "-c", "import sys;print(sys.version_info[0],sys.version_info[1],sys.executable)"],
                           capture_output=True, text=True, timeout=20, creationflags=_bayrak())
    except (OSError, subprocess.SubprocessError):
        return None
    satirlar = (p.stdout or "").strip().splitlines()
    m = re.match(r"^(\d+) (\d+) (.+)$", satirlar[-1]) if p.returncode == 0 and satirlar else None
    if not m:
        return None
    s = (int(m.group(1)), int(m.group(2)))
    if not (PY_ASGARI <= s <= PY_AZAMI) or not os.path.isfile(m.group(3)):
        return None
    return {"surum": f"{s[0]}.{s[1]}", "yol": m.group(3)}


def python_listesi():
    """Sistemde kullanılabilir Python 3.11–3.13 kurulumları (aynı yol bir kez), yeniden eskiye."""
    def uret():
        gorulen, liste = set(), []
        for arg in _adaylar():
            b = _sorgula(arg)
            if b and os.path.normcase(b["yol"]) not in gorulen:
                gorulen.add(os.path.normcase(b["yol"]))
                liste.append(b)
        return liste
    return _onbellekli("python", uret)


def python_bul():
    liste = python_listesi()
    return liste[0] if liste else None


def gpu_var():
    """Windows'ta NVIDIA ekran kartı var mı (nvidia-smi)? Whisper'ın GPU kitaplıkları yalnız bu durumda önerilir."""
    def uret():
        if os.name != "nt" or not shutil.which("nvidia-smi"):
            return False
        try:
            p = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=10, creationflags=_bayrak())
            return p.returncode == 0 and "GPU" in (p.stdout or "")
        except (OSError, subprocess.SubprocessError):
            return False
    return _onbellekli("gpu", uret, 600)


def _hf_onbellek_var(repo):
    kok = os.environ.get("HF_HUB_CACHE") or os.path.join(os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface"), "hub")
    snap = os.path.join(kok, "models--" + repo.replace("/", "--"), "snapshots")
    try:
        with os.scandir(snap) as it:
            return any(True for _ in it)
    except OSError:
        return False


def sistemde_python(tur, model="large-v3"):
    """Kut'un kurmadığı ama paketleri ve model önbelleği hazır bir sistem Python'u (ör. kullanıcı Whisper/EMA'yı kendi kurmuşsa)."""
    gerekli, repo = (("ema_lightning",), EMA_REPO) if tur == "oku" else (("faster_whisper", "ctranslate2"), MODELLER.get(model, MODELLER["large-v3"])["repo"])
    if not _hf_onbellek_var(repo):
        return None

    def uret():
        kod = "import importlib.util as u,sys;sys.exit(0 if all(u.find_spec(m) for m in %r) else 1)" % (gerekli,)
        for b in python_listesi():
            try:
                if subprocess.run([b["yol"], "-I", "-c", kod], capture_output=True, timeout=20, creationflags=_bayrak()).returncode == 0:
                    return b["yol"]
            except (OSError, subprocess.SubprocessError):
                pass
        return None
    return _onbellekli(("sistem", tur, model), uret)


# ---- plan: ne indirilecek, ne kadar ----
def _parcalar(p):
    p = [p] if isinstance(p, str) else list(p or TURLER)
    if not p or any(t not in TURLER for t in p):
        raise ValueError("parçalar: oku ve/veya yaz")
    return [t for t in TURLER if t in p]


def _model_sec(model, gpu):
    if model in (None, ""):
        return "large-v3" if gpu else "small"
    if model not in MODELLER:
        raise ValueError("bilinmeyen Whisper modeli")
    return model


def plan(parcalar=None, model=None):
    parcalar, gpu = _parcalar(parcalar), gpu_var()
    oner = _model_sec(None, gpu)
    model = _model_sec(model, gpu)
    k = []
    if "oku" in parcalar and not kurulu("oku"):
        k += [{"ad": "EMA Lightning paketleri (PyTorch işlemci sürümü)", "mb": PIP_MB["oku"]},
              {"ad": "EMA Lightning Türkçe ses modeli", "mb": EMA_MODEL_MB}]
    if "yaz" in parcalar:
        if not kurulu("yaz"):
            k.append({"ad": "Whisper paketleri (faster-whisper)", "mb": PIP_MB["yaz"]})
            if gpu:
                k.append({"ad": "NVIDIA CUDA kitaplıkları (hızlandırma)", "mb": PIP_MB["gpu"]})
        if yaz_model() != model:
            k.append({"ad": MODELLER[model]["ad"] + " modeli", "mb": MODELLER[model]["mb"]})
    toplam = sum(x["mb"] for x in k)
    py = python_bul()
    try:
        os.makedirs(klasor(), exist_ok=True)
        bos = shutil.disk_usage(klasor()).free // (1024 * 1024)
    except OSError:
        bos = None
    return {"parcalar": parcalar, "yaz_model": model, "oneri": oner, "gpu": gpu, "kalemler": k, "toplam_mb": toplam,
            "gerekli_disk_mb": int(toplam * 1.6 + 300), "bos_disk_mb": bos,
            "modeller": [{"anahtar": a, "ad": m["ad"], "mb": m["mb"], "not": m["not"], "oneri": a == oner} for a, m in MODELLER.items()],
            "python": {"var": bool(py), "surum": py["surum"] if py else "", "url": PY_URL, "aralik": "3.11–3.13"}}


# ---- durum ----
def _set(**k):
    with _kilit:
        _d.update(k)


def calisiyor():
    th = _is["th"]
    return bool(th and th.is_alive())


def ozet():
    """Arayüzün yokladığı durum (ucuz: alt süreç çalıştırmaz)."""
    with _kilit:   # GET yoklaması yan etki olarak dizin silmez: yarım ortam temizliği yalnız baslat() içinde
        d = dict(_d)
    d["calisiyor"] = calisiyor()
    d["kurulu"] = {t: kurulu(t) for t in TURLER}
    d["model"] = yaz_model() or d.get("model", "")
    d["soru"] = soru()
    d["python_url"] = PY_URL
    return d


def _agirliklar(parcalar, model, gpu):
    ag = [("python", 5)]
    for t in parcalar:
        yeni = not kurulu(t)
        if yeni:
            ag += [(f"venv:{t}", VENV_MB), (f"pip:{t}", PIP_MB[t] + (PIP_MB["gpu"] if t == "yaz" and gpu else 0))]
        if t == "oku" and yeni:
            ag.append(("model:oku", EMA_MODEL_MB))
        if t == "yaz" and (yeni or yaz_model() != model):
            ag.append(("model:yaz", MODELLER[model]["mb"]))
    return ag


ETIKET = {"python": "Python aranıyor", "venv:oku": "Türkçe ses ortamı hazırlanıyor", "pip:oku": "EMA Lightning paketleri indiriliyor",
          "model:oku": "EMA Türkçe ses modeli indiriliyor", "venv:yaz": "Yazıya çevirme ortamı hazırlanıyor",
          "pip:yaz": "Whisper paketleri indiriliyor", "model:yaz": "Whisper modeli indiriliyor"}


def _ilerle(anahtar, oran=0.0, ileti=None):
    with _kilit:
        biten, w = 0, 1
        for a, x in _is["ag"]:
            if a == anahtar:
                w = x
                break
            biten += x
        _d["adim"] = ETIKET.get(anahtar, anahtar)
        _d["yuzde"] = max(_d["yuzde"], min(99, int(100 * (biten + w * min(1.0, max(0.0, oran))) / max(1, _is["toplam"]))))
        if ileti is not None:
            _d["ileti"] = ileti[:140]


# ---- alt süreç (kabuk yok, argüman listesi) ----
def _env(ek=None):
    # PIP_* (PIP_INDEX_URL, PIP_EXTRA_INDEX_URL, PIP_TRUSTED_HOST...) ve HF_ENDPOINT/HF_TOKEN ortamdan miras alınmaz: indirme kaynağı sabittir
    e = {k: v for k, v in os.environ.items() if k.upper() not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "HF_HUB_OFFLINE", "HF_ENDPOINT", "HF_TOKEN",
                                                                   "HUGGING_FACE_HUB_TOKEN", "HF_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE") and not k.upper().startswith("PIP_")}
    e.update({"PYTHONUTF8": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_INPUT": "1", "HF_HUB_DISABLE_PROGRESS_BARS": "1"})
    e.update(ek or {})
    return e


def _gunluk_yolu():
    return os.path.join(ia.DEPO, "ses-kurulum.log")


def _gunluge(satir):
    try:
        with open(_gunluk_yolu(), "a", encoding="utf-8") as f:
            f.write(satir + "\n")
    except OSError:
        pass


def _oldur(p):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=_bayrak())
        else:
            p.kill()
    except Exception:
        pass


def _calistir(arg, env=None, satir=None):
    """Alt süreci çalıştırır, çıktısını (stderr dahil) satır satır `satir`'a verir. Dönüş: (çıkış kodu, son satırlar). İptalde Iptal."""
    if _is["iptal"].is_set():
        raise Iptal()
    _gunluge("$ " + " ".join(arg))
    p = subprocess.Popen(arg, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", env=_env(env), creationflags=_bayrak())
    with _kilit:
        _is["p"] = p
    if _is["iptal"].is_set():
        _oldur(p)
    son = collections.deque(maxlen=12)
    try:
        for s in p.stdout:
            s = s.strip()
            if not s:
                continue
            _gunluge(s)
            son.append(s)
            if satir:
                satir(s)
        p.wait()
    finally:
        with _kilit:
            _is["p"] = None
        if p.poll() is None:
            _oldur(p)
    if _is["iptal"].is_set():
        raise Iptal()
    return p.returncode, list(son)


def _hata_metni(adim, son):
    metin = " ".join(son[-4:])
    if re.search(r"getaddrinfo|Connection|timed out|Temporary failure|Max retries|SSL|ProxyError|offline|resolve", metin, re.I):
        return "İnternet bağlantısı kurulamadı ya da indirme kaynağına (PyPI / Hugging Face) ulaşılamadı. Bağlantını denetleyip tekrar dene."
    if re.search(r"No matching distribution|Could not find a version|not a supported wheel", metin, re.I):
        return "Bu Python sürümü için paketlerden biri bulunamadı. Python 3.11, 3.12 ya da 3.13 kurup tekrar dene."
    if re.search(r"No space left|ENOSPC|Errno 28", metin, re.I):
        return "Diskte yer kalmadı. Yer açıp tekrar dene."
    return f"{ETIKET.get(adim, adim)} adımı başarısız oldu. Ayrıntı: ses-kurulum.log" + (f" ({son[-1][:160]})" if son else "")


# ---- kurulum ----
ISARET_ESKI_SN = 6 * 3600   # bundan eski işaret, PID canlı görünse bile (PID yeniden kullanılmış olabilir) bayat sayılır


def _pid_canli(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            kod = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(kod))) and kod.value == 259   # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True   # PermissionError: süreç var
    return True


def _isaret_yaz(yol):
    with open(yol, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "zaman": time.time()}, f)


def _baska_kurulum_suruyor(tur):
    """`.kuruluyor` işareti BAŞKA bir canlı Kut sürecine ve yeterince yeniye mi ait? (Aynı ses klasörünü paylaşan ikinci bir Kut.)"""
    try:
        with open(os.path.join(_tur_klasor(tur), ".kuruluyor"), encoding="utf-8") as f:
            b = json.load(f)
    except (OSError, ValueError):
        return False   # yok, boş ya da eski biçim: bayat
    if not isinstance(b, dict) or not isinstance(b.get("pid"), int) or not isinstance(b.get("zaman"), (int, float)):
        return False
    return b["pid"] != os.getpid() and time.time() - b["zaman"] < ISARET_ESKI_SN and _pid_canli(b["pid"])


def _yarida_temizle():
    """Kurulum çalışmıyorken `.kuruluyor` işareti kalmışsa (Kut kapandı, süreç öldü) o ortamı sil: yarım ortam kullanılmaz.
    Başka canlı bir Kut'un süren kurulumuna ait işaretli ortama dokunmaz. Yalnız `baslat` çağırır (GET yoklaması dizin silmez)."""
    for t in TURLER:
        isaret = os.path.join(_tur_klasor(t), ".kuruluyor")
        if os.path.exists(isaret) and not calisiyor() and not _baska_kurulum_suruyor(t):
            _tur_sil(t)


def _hf_temizle(repo, onceden_vardi):
    """İptal/hata sonrası yarım indirmeleri siler: tüm `.incomplete` dosyaları ve bu denemede ilk kez açılan model deposu önbelleği.
    Dönen: silinemeyen yollar (boşsa temiz)."""
    kok = hf_klasor()
    for yol, _, adlar in os.walk(kok):
        for ad in adlar:
            if ad.endswith(".incomplete"):
                try:
                    os.remove(os.path.join(yol, ad))
                except OSError:
                    pass
    if repo and not onceden_vardi:
        shutil.rmtree(_repo_klasor(repo), ignore_errors=True)
    kalan = [os.path.join(y, a) for y, _, adlar in os.walk(kok) for a in adlar if a.endswith(".incomplete")]
    if repo and not onceden_vardi and os.path.exists(_repo_klasor(repo)):
        kalan.append(_repo_klasor(repo))
    return kalan


def _repo_klasor(repo):
    return os.path.join(hf_klasor(), "hub", "models--" + repo.replace("/", "--"))


def _tur_sil(tur):
    shutil.rmtree(_tur_klasor(tur), ignore_errors=True)
    if tur in kurulu_bilgi():
        _bilgi_yaz(tur, None)


def _pip_komutu(vpy, paketler, hash_dosyasi=None):
    """`-I` (python yalıtılmış kip) + `--isolated` (pip ortam değişkenlerini ve pip.ini'yi yok sayar). hash_dosyasi verilirse yalnız o
    gereksinim dosyası, `--no-deps --require-hashes` ile kurulur."""
    arg = [vpy, "-I", "-m", "pip", "--isolated", "install", "--disable-pip-version-check", "--no-input", "--no-cache-dir", "--progress-bar", "off",
           "--only-binary", ":all:"]
    if hash_dosyasi:
        return arg + ["--no-deps", "--require-hashes", "-r", hash_dosyasi]
    if sys.platform.startswith("linux") and any(p.startswith("torch") for p in paketler):
        arg += ["--extra-index-url", PYTORCH_CPU]
    return arg + paketler


def _pip_adimlari(tur, vpy, klasor_, gpu):
    """[(komut)] — oku: önce hash'li ema-lightning + normalizer-tr (bağımlılıksız), sonra torch ve kalan gerekler; yaz: sürümle sabit tek adım."""
    if tur == "oku":
        dosya = os.path.join(klasor_, "gereksinim-hash.txt")
        with open(dosya, "w", encoding="utf-8") as f:
            for ad, hashler in PIP_HASH.items():
                f.write(ad + " " + " ".join("--hash=sha256:" + h for h in hashler) + "\n")
        return [_pip_komutu(vpy, [], dosya), _pip_komutu(vpy, EMA_BAGIMLILIK)]
    return [_pip_komutu(vpy, PIP_PAKET[tur] + (PIP_PAKET["gpu"] if tur == "yaz" and gpu else []))]


def _kur_tur(tur, py, model, gpu):
    yeni = not kurulu(tur)
    vpy = venv_python(tur)
    isaret = os.path.join(_tur_klasor(tur), ".kuruluyor")
    repo, onceden = None, False
    if yeni and _baska_kurulum_suruyor(tur):   # başka bir Kut penceresi aynı ses klasöründe kuruyor: onun ortamını silme
        raise Hata("Başka bir Kut penceresi bu ses klasöründe kurulum yapıyor; bitmesini bekle ya da onu kapat.")
    try:
        if yeni:
            shutil.rmtree(_tur_klasor(tur), ignore_errors=True)
            os.makedirs(_tur_klasor(tur), exist_ok=True)
            _isaret_yaz(isaret)
            _ilerle(f"venv:{tur}", 0, "Sanal ortam oluşturuluyor")
            rc, son = _calistir([py, "-I", "-m", "venv", os.path.join(_tur_klasor(tur), ".venv")])
            if rc != 0 or not os.path.isfile(vpy):
                raise Hata(_hata_metni(f"venv:{tur}", son))
            sayac = [0]

            def pip_satir(s):
                if s.startswith(("Collecting", "Downloading", "Installing", "Successfully")):
                    sayac[0] += 1
                    _ilerle(f"pip:{tur}", sayac[0] / BEKLENEN_SATIR[tur], s)
            _ilerle(f"pip:{tur}", 0, "Paketler indiriliyor (pip)")
            for komut in _pip_adimlari(tur, vpy, _tur_klasor(tur), gpu):
                rc, son = _calistir(komut, satir=pip_satir)
                if rc != 0:
                    raise Hata(_hata_metni(f"pip:{tur}", son))
        if tur == "oku" and not yeni:
            return
        ad = model if tur == "yaz" else ""
        mb = MODELLER[model]["mb"] if tur == "yaz" else EMA_MODEL_MB
        repo, sha = (MODELLER[model]["repo"], MODELLER[model]["sha"]) if tur == "yaz" else (EMA_REPO, EMA_SHA)
        onceden = os.path.isdir(_repo_klasor(repo))

        def model_satir(s):
            if s.startswith("{"):
                try:
                    j = json.loads(s)
                except ValueError:
                    return
                if "indirilen" in j:
                    _ilerle(f"model:{tur}", j["indirilen"] / (mb * 1024 * 1024), f"{int(j['indirilen'] / 1048576)} / ~{mb} MB indirildi")
        _ilerle(f"model:{tur}", 0, "Model indiriliyor")
        rc, son = _calistir([vpy, "-I", ISCI, "indir", tur, ad, repo, sha], env={"HF_HOME": hf_klasor()}, satir=model_satir)
        if rc != 0:
            raise Hata(_hata_metni(f"model:{tur}", son))
        bilgi = {"kapsam": KAPSAM_SURUM, "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"), "paketler": PIP_PAKET[tur]}
        if tur == "yaz":
            bilgi.update(model=model, gpu=bool(gpu if yeni else (kurulu_bilgi().get("yaz") or {}).get("gpu")))
        _bilgi_yaz(tur, bilgi)
        if os.path.exists(isaret):
            os.remove(isaret)
        with _kilit:
            _is["tamam"].append(tur)
    except BaseException:
        if yeni:
            _tur_sil(tur)   # bu denemede açılan yarım ortam kalmasın (var olan çalışan ortama dokunulmaz)
        if repo:
            _is["kalan"] += _hf_temizle(repo, onceden)   # yarım model indirmesi (.incomplete dahil) kalmasın
        raise


def _calis(parcalar, model, gpu):
    try:
        _ilerle("python", 0, "Sistemde Python 3.11–3.13 aranıyor")
        py = python_bul()
        if not py:
            raise Hata("Sesli iletişim kurulumu için bilgisayarında Python 3.11, 3.12 ya da 3.13 gerekli; bulamadım. "
                       f"{PY_URL} adresinden kur (kurulumda “Add python.exe to PATH” kutusunu işaretle), sonra tekrar dene.", python_yok=True)
        for t in parcalar:
            _kur_tur(t, py["yol"], model, gpu)
        _set(durum="hazir", yuzde=100, adim="Hazır", ileti="Sesli iletişim kuruldu.", hata="")
    except Iptal:
        kalan, tamam = _is["kalan"], _is["tamam"]
        ileti = ("Kurulum iptal edildi; yarım kalan ortam ve yarım model indirmeleri silindi." if not kalan else
                 f"Kurulum iptal edildi; ancak {len(kalan)} yarım dosya/klasör silinemedi (ses klasörü). Kut'u kapatıp ses/hf klasörünü elle silebilirsin.")
        if tamam:
            ileti += " Tamamlanmış parça kaldı: " + ", ".join(tamam) + "."
        _set(durum="iptal", adim="", ileti=ileti, hata="")
    except Hata as e:
        _set(durum="hata", hata=str(e), python_yok=e.python_yok)
    except Exception as e:
        _gunluge(f"beklenmeyen hata: {type(e).__name__}: {e}")
        _set(durum="hata", hata=f"Kurulum beklenmedik biçimde durdu ({type(e).__name__}). Ayrıntı: ses-kurulum.log")


def baslat(parcalar=None, model=None, onay=False):
    """Kurulumu başlatır. Kullanıcının açık onayı (onay=True) olmadan hiçbir şey indirilmez."""
    if onay is not True:
        raise ValueError("Kurulum için onay gerekir.")
    parcalar, gpu = _parcalar(parcalar), gpu_var()
    model = _model_sec(model, gpu)
    if calisiyor():
        raise ValueError("Kurulum zaten sürüyor.")
    _yarida_temizle()
    for t in parcalar:
        if _baska_kurulum_suruyor(t):
            raise ValueError("Başka bir Kut penceresi aynı ses klasöründe kurulum yapıyor; o bitene kadar bekle.")
    ag = _agirliklar(parcalar, model, gpu)
    if len(ag) == 1:
        raise ValueError("İstenen ses ortamı zaten kurulu.")
    p = plan(parcalar, model)   # alt süreç yoklar (Python, ekran kartı); kilidi tutarken çalıştırma
    if p["bos_disk_mb"] is not None and p["bos_disk_mb"] < p["gerekli_disk_mb"]:
        raise ValueError(f"Diskte yeterli yer yok: en az ~{p['gerekli_disk_mb']} MB gerekli, {p['bos_disk_mb']} MB boş.")
    parcalar = [t for t in parcalar if any(a.endswith(":" + t) for a, _ in ag)]
    with _kilit:
        if calisiyor():
            raise ValueError("Kurulum zaten sürüyor.")
        _is.update(ag=ag, toplam=sum(x for _, x in ag), iptal=threading.Event(), p=None, tamam=[], kalan=[])
        _d.update(durum="kuruluyor", adim=ETIKET["python"], yuzde=0, ileti="", hata="", python_yok=False, turler=parcalar, model=model)
        try:
            os.makedirs(ia.DEPO, exist_ok=True)
            open(_gunluk_yolu(), "w").close()
        except OSError:
            pass
        th = threading.Thread(target=_calis, args=(parcalar, model, gpu), daemon=True)
        _is["th"] = th
        th.start()
    return ozet()


def iptal():
    """Sürmekte olan kurulumu durdurur (alt süreç öldürülür; o kurulumda açılan ortam silinir)."""
    with _kilit:
        if not calisiyor():
            return ozet()
        _is["iptal"].set()
        p = _is["p"]
    if p:
        _oldur(p)
    th = _is["th"]
    if th:
        th.join(timeout=20)
    return ozet()


def kaldir():
    """Kut'un kurduğu tüm ses ortamını ve indirilen modelleri siler (kullanıcının kendi Whisper/EMA ortamlarına dokunmaz)."""
    if calisiyor():
        raise ValueError("Kurulum sürüyor; önce iptal et.")
    if any(_baska_kurulum_suruyor(t) for t in TURLER):
        raise ValueError("Başka bir Kut penceresi aynı ses klasöründe kurulum yapıyor; o bitene kadar bekle.")
    k = os.path.abspath(klasor())
    if os.path.basename(k) != "ses" or os.path.abspath(ia.DEPO) != os.path.dirname(k):
        raise ValueError("beklenmeyen klasör")   # yanlış yolu asla silme
    shutil.rmtree(k, ignore_errors=True)
    if os.path.exists(k):
        raise ValueError("Klasör tamamen silinemedi (bir ses işlemi açık olabilir); Kut'u yeniden açıp tekrar dene.")
    _set(durum="yok", adim="", yuzde=0, ileti="", hata="", python_yok=False)
    return ozet()


def _cikista():
    p = _is["p"]
    if p and p.poll() is None:
        _oldur(p)


atexit.register(_cikista)
