"""Kut güncelleme: sürüm denetimi (GitHub Releases), exe/git kurulumu için uygulama ve geri dönüş.

Gizlilik: Kut sen izin vermeden internete çıkmaz. Otomatik denetim yalnız `guncelleme.otomatik` = true ise ve haftada en çok bir kez
yapılır (GitHub'dan yalnız sürüm bilgisi alınır, hiçbir veri gönderilmez); "Güncelleme var mı?" düğmesi elle her zaman çalışır.
Güncelleme veri klasörüne dokunmaz; yalnız programı değiştirir. Önceki program yedeklenir (exe: Kut.prev.exe, git: önceki commit).

Ağ: ag_kaynak'taki SSRF korumalı istek yolu kullanılır (_guvenli_url + yönlendirme denetimi) ve ek olarak ana makine izin listesi uygulanır.
exe bütünlüğü: API'deki varlık `digest` (sha256) alanı ya da yayındaki `Kut.exe.sha256` / `SHA256SUMS` dosyası. Sağlama toplamı yoksa kurulmaz.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import ag_cekirdek as c
import ag_ice_aktar as ia
import ag_kaynak as kn
import surum as sv

REPO = "koraykutlu/kut"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
API_HOSTLAR = frozenset({"api.github.com"})
# Yayın varlığı github.com'dan başlar; GitHub imzalı bir CDN adresine yönlendirir (eski: objects.githubusercontent.com,
# 2025'ten beri: release-assets.githubusercontent.com). Başka hiçbir ana makineye yönlendirme kabul edilmez.
INDIRME_HOSTLAR = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
                             "github-releases.githubusercontent.com"})
INDIRME_ONEKI = f"https://github.com/{REPO}/releases/download/"
API_AZAMI = 1_000_000
SUMS_AZAMI = 65_536
EXE_AZAMI = 50_000_000
ARALIK = 7 * 24 * 3600
NOT_AZAMI = 1500
UZAK_DESEN = re.compile(r"github\.com[:/]" + re.escape(REPO) + r"(?:\.git)?/?$", re.I)
SHA_DESEN = re.compile(r"^[0-9a-fA-F]{64}$")

KAPAT = None   # ag_sunucu.main sunucuyu durduran işlevi buraya koyar
PORT_AL = lambda: 47318   # ag_sunucu.main gerçek portu bildirir
_kilit = threading.Lock()
_mesgul = threading.Lock()


def _simdi():
    return time.time()


# ---- ayarlar (ayarlar.json → "guncelleme") ----
def _ayar():
    g = ia.ayarlar().get("guncelleme")
    return dict(g) if isinstance(g, dict) else {}


def _ayar_yaz(**kv):
    with _kilit:
        a = ia.ayarlar()
        g = a.get("guncelleme") if isinstance(a.get("guncelleme"), dict) else {}
        for k, v in kv.items():
            if v is None:
                g.pop(k, None)
            else:
                g[k] = v
        a["guncelleme"] = g
        ia.ayar_yaz(a)


def otomatik():
    """True/False; kullanıcıya henüz sorulmadıysa None."""
    o = _ayar().get("otomatik")
    return o if isinstance(o, bool) else None


def otomatik_ayarla(acik):
    _ayar_yaz(otomatik=bool(acik))
    return bool(acik)


def otomatik_gerekli(simdi=None):
    """Ağa çıkmadan karar: sorulmadıysa ya da kapalıysa asla; açıksa son başarılı denetimden 7 gün geçtiyse."""
    if otomatik() is not True:
        return False
    son = _ayar().get("son_denetim")
    return not isinstance(son, (int, float)) or (simdi if simdi is not None else _simdi()) - son >= ARALIK


# ---- kurulum türü ----
def kurulum_turu():
    if c.DONDURULDU:
        return "exe"
    if os.path.exists(os.path.join(c.DEPO, ".git")) and shutil.which("git"):
        return "git"
    return "kaynak"


# ---- ağ ----
def _https_izinli(url, hostlar):
    u = urllib.parse.urlparse(url or "")
    if u.scheme != "https" or (u.hostname or "").lower() not in hostlar:
        raise ValueError("adres izin listesinde değil")
    return url


def _acici(hostlar):
    class Y(kn.GuvenliYonlendirme):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            try:
                _https_izinli(urllib.parse.urljoin(req.full_url, newurl), hostlar)
            except ValueError as e:
                raise urllib.error.URLError("yönlendirme reddedildi: " + str(e))
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    return urllib.request.build_opener(Y)


def _istek_ac(url, hostlar, zaman):
    _https_izinli(url, hostlar)
    try:
        kn._guvenli_url(url)
    except ValueError as e:
        raise OSError("adres reddedildi: " + str(e))
    r = urllib.request.Request(url, headers={"User-Agent": "Kut/" + sv.SURUM, "Accept": "application/vnd.github+json, application/octet-stream"})
    return _acici(hostlar).open(r, timeout=zaman)


def _ag_oku(url, azami, hostlar, zaman=10):
    with _istek_ac(url, hostlar, zaman) as y:
        return kn.sinirli_oku(y, azami)


def _indir(url, hedef, azami, hostlar=INDIRME_HOSTLAR, zaman=30):
    """url'yi hedef dosyaya yazar (azami bayt aşılırsa durur); (boyut, sha256 hex) döndürür."""
    h, n = hashlib.sha256(), 0
    with _istek_ac(url, hostlar, zaman) as y, open(hedef, "wb") as f:
        while True:
            parca = y.read(65536)
            if not parca:
                break
            n += len(parca)
            if n > azami:
                raise OSError("dosya çok büyük")
            h.update(parca)
            f.write(parca)
    return n, h.hexdigest()


# ---- sürüm bilgisi ----
def _surum_coz(j):
    """GitHub 'releases/latest' cevabından yalnız gereken alanları alır (not metni veridir, kırpılır)."""
    if not isinstance(j, dict):
        raise ValueError("beklenmeyen cevap")
    etiket = str(j.get("tag_name") or "")
    s = ".".join(str(x) for x in sv.ayristir(etiket))
    exe, sums = None, None
    for a in j.get("assets") or []:
        if not isinstance(a, dict):
            continue
        ad, url = a.get("name"), a.get("browser_download_url")
        if ad == "Kut.exe":
            d = a.get("digest")
            sha = d[7:].lower() if isinstance(d, str) and d.lower().startswith("sha256:") and SHA_DESEN.match(d[7:]) else None
            boyut = a.get("size") if isinstance(a.get("size"), int) else None
            exe = {"url": url, "boyut": boyut, "sha256": sha}
        elif ad in ("Kut.exe.sha256", "SHA256SUMS"):
            if sums is None or ad == "Kut.exe.sha256":
                sums = {"ad": ad, "url": url}
    sayfa = str(j.get("html_url") or "")
    if not sayfa.startswith(f"https://github.com/{REPO}/"):
        sayfa = f"https://github.com/{REPO}/releases/tag/{etiket}"
    return {"surum": s, "etiket": etiket, "notlar": str(j.get("body") or "")[:NOT_AZAMI], "url": sayfa,
            "yayin": str(j.get("published_at") or "")[:10], "exe": exe, "sums": sums}


def denetle(elle=False):
    """GitHub'dan son sürümü sorar ve önbelleğe yazar. elle=False (otomatik) ise yalnız izin + haftalık süre uygunsa ağa çıkar.
    Elle çağrıda hata ValueError olur; sonuç durum()."""
    if not elle and not otomatik_gerekli():
        return durum()
    try:
        j = json.loads(_ag_oku(API_URL, API_AZAMI, API_HOSTLAR))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _ayar_yaz(son_denetim=_simdi(), son=None)
            raise ValueError("Henüz yayınlanmış bir sürüm yok.")
        raise ValueError("GitHub isteği reddetti" + (" (istek sınırı; sonra dene)" if e.code in (403, 429) else f" ({e.code})"))
    except (OSError, ValueError):
        raise ValueError("Güncelleme sunucusuna ulaşılamadı.")
    try:
        son = _surum_coz(j)
    except ValueError:
        raise ValueError("Sürüm bilgisi okunamadı.")
    _ayar_yaz(son_denetim=_simdi(), son=son)
    return durum()


def otomatik_denetim():
    """Sunucu açılışında (arka plan): izin ve süre uygunsa denetler; hata sessizce geçer (bir sonraki açılışta yeniden)."""
    if not otomatik_gerekli():
        return None
    try:
        return denetle(elle=False)
    except ValueError:
        return None


# ---- git yardımcıları ----
def _git(*a, zaman=120):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    p = subprocess.run(["git", "-C", c.DEPO, *a], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=zaman,
                       env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def git_uzak():
    """Genel Kut deposunu gösteren uzak adı (yoksa None)."""
    rc, cikti, _ = _git("config", "--get-regexp", r"^remote\..*\.url$", zaman=20)
    if rc != 0:
        return None
    for satir in cikti.splitlines():
        anahtar, _, url = satir.partition(" ")
        if UZAK_DESEN.search(url.strip()):
            return anahtar[len("remote."):-len(".url")]
    return None


def git_kirli():
    rc, cikti, _ = _git("status", "--porcelain", "--untracked-files=no", zaman=30)
    return rc != 0 or bool(cikti)


def _engel(tur, yeni=True):
    """Uygulamayı ağsız engelleyen neden ('' = engel yok)."""
    if tur == "kaynak":
        return "Bu kurulum git deposu değil (zip/kopya). Yeni sürümü indirip dosyaların üstüne kopyala; veri klasörüne dokunulmaz."
    if tur == "exe":
        if os.name != "nt":
            return "Otomatik exe güncellemesi yalnız Windows'ta."
        return ""
    if git_uzak() is None:
        return "Bu depo genel Kut deposunu (github.com/koraykutlu/kut) izlemiyor; güncelleme yalnız bildirilir."
    if git_kirli():
        return "Çalışma ağacında kaydedilmemiş değişiklik var; önce commit'le ya da geri al."
    return ""


# ---- durum ----
def geri_var():
    tur = kurulum_turu()
    if tur == "exe":
        return os.path.isfile(_exe_yollari()[2])
    if tur == "git":
        o = _ayar().get("onceki")
        return isinstance(o, dict) and o.get("tur") == "git" and bool(o.get("commit"))
    return False


def durum():
    g = _ayar()
    son = g.get("son") if isinstance(g.get("son"), dict) else None
    tur = kurulum_turu()
    try:
        yeni = bool(son) and sv.yeni_mi(son.get("surum"))
    except ValueError:
        yeni = False
    d = {"surum": sv.SURUM, "kurulum": tur, "otomatik": otomatik(), "sorulmadi": otomatik() is None,
         "son_denetim": datetime.fromtimestamp(g["son_denetim"]).strftime("%Y-%m-%d %H:%M") if isinstance(g.get("son_denetim"), (int, float)) else "",
         "son": son, "yeni": yeni, "geri_var": geri_var(), "engel": ""}
    if yeni:
        try:
            d["engel"] = _engel(tur)
        except Exception:
            d["engel"] = "Kurulum türü denetlenemedi."
    return d


# ---- exe ----
def _exe_yollari():
    mevcut = os.path.abspath(sys.executable)
    k = os.path.dirname(mevcut)
    return mevcut, os.path.join(k, "Kut.new.exe"), os.path.join(k, "Kut.prev.exe")


DEGISTIRICI_PS1 = r"""$ErrorActionPreference = 'Stop'
function Gunluk($m) { try { Add-Content -LiteralPath $env:KUT_LOG -Value ((Get-Date -Format 's') + ' ' + $m) } catch {} }
try {
  $p = [int]$env:KUT_PID
  for ($i = 0; $i -lt 120; $i++) { if (-not (Get-Process -Id $p -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Milliseconds 500 }
  Start-Sleep -Milliseconds 800
  $exe = $env:KUT_EXE; $yeni = $env:KUT_YENI; $once = $env:KUT_ONCE; $tmp = $exe + '.swap'
  if ((Test-Path -LiteralPath $once) -and ($once -ne $yeni)) { Remove-Item -LiteralPath $once -Force }
  Move-Item -LiteralPath $exe -Destination $tmp -Force
  try { Move-Item -LiteralPath $yeni -Destination $exe -Force } catch { Move-Item -LiteralPath $tmp -Destination $exe -Force; throw }
  Move-Item -LiteralPath $tmp -Destination $once -Force
  Gunluk 'degistirildi'
} catch { Gunluk ('HATA: ' + $_.Exception.Message) }
try { Start-Process -FilePath $env:KUT_EXE -ArgumentList $env:KUT_ARGS } catch { Gunluk ('baslatilamadi: ' + $_.Exception.Message) }
try { Remove-Item -LiteralPath $PSCommandPath -Force } catch {}
"""


def _acilis_argumanlari():
    return [a for a in sys.argv[1:] if a != "--tarayicisiz"] + ["--tarayicisiz"]   # eski pencere kendini yeniler; ikinci pencere açılmaz


def _kapat_planla():
    """Cevap tarayıcıya ulaşınca sunucuyu durdurur ve süreçten çıkar (değiştirici/yeniden başlatıcı bunu bekler)."""
    def is_():
        time.sleep(1.2)
        try:
            if KAPAT:
                KAPAT()
        finally:
            time.sleep(1.5)
            os._exit(0)
    threading.Thread(target=is_).start()


def _degistirici_baslat(mevcut, yeni, once):
    """Küçük, ayrık bir PowerShell betiği: bu süreç çıkınca mevcut→once, yeni→mevcut yapar ve Kut'u başlatır."""
    os.makedirs(ia.DEPO, exist_ok=True)
    fd, yol = tempfile.mkstemp(prefix="kut-degistir-", suffix=".ps1")
    with os.fdopen(fd, "w", encoding="ascii", newline="\r\n") as f:
        f.write(DEGISTIRICI_PS1)
    env = {**os.environ, "KUT_PID": str(os.getpid()), "KUT_EXE": mevcut, "KUT_YENI": yeni, "KUT_ONCE": once,
           "KUT_ARGS": subprocess.list2cmdline(_acilis_argumanlari()), "KUT_LOG": os.path.join(ia.DEPO, "guncelleme.log")}
    bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", yol],
                     env=env, close_fds=True, creationflags=bayrak, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


YENIDEN_BASLATICI_PY = (
    "import socket,subprocess,sys,time\n"
    "port=int(sys.argv[1])\n"
    "for _ in range(160):\n"
    "    try: socket.create_connection(('127.0.0.1',port),timeout=0.3).close()\n"
    "    except OSError: break\n"
    "    time.sleep(0.25)\n"
    "time.sleep(0.5)\n"
    "subprocess.Popen(sys.argv[2:],close_fds=True)\n"
)


def _yeniden_baslat_planla():
    """Kaynak/git kurulumu: port kapanınca başlatıcıyı aynı bağımsız değişkenlerle yeniden açan ayrık süreç."""
    komut = [sys.executable, "-c", YENIDEN_BASLATICI_PY, str(PORT_AL()), sys.executable,
             os.path.join(c.DEPO, "kut.pyw"), *_acilis_argumanlari()]
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    subprocess.Popen(komut, **kw)


def _sums_coz(ham, ad, tek_satir_ok):
    if ham[:2] in (b"\xff\xfe", b"\xfe\xff"):
        metin = ham.decode("utf-16", errors="ignore")
    else:
        metin = ham.decode("utf-8-sig", errors="ignore")
    for satir in metin.splitlines():
        p = satir.strip().split()
        if not p or not SHA_DESEN.match(p[0]):
            continue
        if len(p) == 1 and tek_satir_ok or len(p) >= 2 and p[-1].lstrip("*").replace("\\", "/").split("/")[-1].lower() == ad.lower():
            return p[0].lower()
    return None


def _beklenen_sha(son):
    exe = son.get("exe") or {}
    if exe.get("sha256"):
        return exe["sha256"]
    s = son.get("sums")
    if s and s.get("url"):
        _https_izinli(s["url"], INDIRME_HOSTLAR)
        if not s["url"].startswith(INDIRME_ONEKI):
            raise ValueError("sağlama dosyası adresi geçersiz")
        try:
            ham = _ag_oku(s["url"], SUMS_AZAMI, INDIRME_HOSTLAR)
        except (OSError, ValueError):
            raise ValueError("Sağlama dosyası indirilemedi.")
        return _sums_coz(ham, "Kut.exe", s.get("ad") == "Kut.exe.sha256")
    return None


def _uygula_exe(son):
    exe = son.get("exe") or {}
    url = exe.get("url")
    try:
        _https_izinli(url, INDIRME_HOSTLAR)
    except ValueError:
        raise ValueError("Kut.exe adresi izin verilen GitHub adreslerinde değil; kurulmadı.")
    if not url.startswith(INDIRME_ONEKI):
        raise ValueError("Kut.exe adresi bu deponun yayınında değil; kurulmadı.")
    if isinstance(exe.get("boyut"), int) and exe["boyut"] > EXE_AZAMI:
        raise ValueError("Kut.exe beklenenden büyük; kurulmadı.")
    beklenen = _beklenen_sha(son)
    if not beklenen:
        raise ValueError("Bu yayında Kut.exe için sağlama toplamı (digest ya da Kut.exe.sha256) yok; güvenlik için kurulmadı.")
    mevcut, yeni, once = _exe_yollari()
    try:
        boyut, ozet = _indir(url, yeni, EXE_AZAMI)
    except PermissionError:
        _sil(yeni)
        raise ValueError("Kut.exe'nin bulunduğu klasöre yazılamıyor; yeni sürümü elle indir.")
    except (OSError, ValueError):
        _sil(yeni)
        raise ValueError("Kut.exe indirilemedi.")
    if ozet != beklenen or (isinstance(exe.get("boyut"), int) and exe["boyut"] != boyut):
        _sil(yeni)
        raise ValueError("Sağlama toplamı uyuşmuyor; indirilen dosya silindi, kurulmadı.")
    _ayar_yaz(onceki={"tur": "exe", "surum": sv.SURUM, "tarih": datetime.now().strftime("%Y-%m-%d %H:%M")})
    _degistirici_baslat(mevcut, yeni, once)
    _kapat_planla()
    return {"yeniden": True, "mesaj": f"Kut {son['surum']} indirildi ve doğrulandı; yeniden başlıyor."}


def _geri_exe():
    mevcut, _, once = _exe_yollari()
    if not os.path.isfile(once):
        raise ValueError("Geri dönülecek önceki sürüm (Kut.prev.exe) yok.")
    _degistirici_baslat(mevcut, once, once)
    _kapat_planla()
    return {"yeniden": True, "mesaj": "Önceki sürüme dönülüyor; Kut yeniden başlıyor."}


def _sil(yol):
    try:
        os.remove(yol)
    except OSError:
        pass


# ---- git ----
def _git_hata(ne, err):
    return ValueError(f"{ne}: {err[:200]}" if err else ne)


def _uygula_git(son):
    uzak = git_uzak()
    if uzak is None:
        raise ValueError("Bu depo genel Kut deposunu (github.com/koraykutlu/kut) izlemiyor; güncelleme yalnız bildirilir.")
    if git_kirli():
        raise ValueError("Çalışma ağacında kaydedilmemiş değişiklik var; önce commit'le ya da geri al. Dokunulmadı.")
    rc, _, err = _git("fetch", "--tags", uzak)
    if rc != 0:
        raise _git_hata("git fetch başarısız", err)
    rc, hedef, _ = _git("rev-parse", "-q", "--verify", f"refs/tags/{son['etiket']}^{{commit}}", zaman=20)
    if rc != 0:
        hedef = ""
        for dal in ("main", "master"):
            rc, h, _ = _git("rev-parse", "-q", "--verify", f"refs/remotes/{uzak}/{dal}^{{commit}}", zaman=20)
            if rc == 0:
                hedef = h
                break
        if not hedef:
            raise ValueError("Yayın etiketi ya da uzak ana dal bulunamadı; güncellenemedi.")
    rc, simdi, _ = _git("rev-parse", "HEAD", zaman=20)
    if rc != 0:
        raise ValueError("Geçerli commit okunamadı.")
    if simdi == hedef:
        raise ValueError("Kod zaten bu sürümde.")
    if _git("merge-base", "--is-ancestor", "HEAD", hedef, zaman=20)[0] != 0:
        raise ValueError("Yerel geçmiş yayınla ileri sarılamıyor (yerel commit'ler var ya da dallar ayrışmış); dokunulmadı.")
    _ayar_yaz(onceki={"tur": "git", "commit": simdi, "surum": sv.SURUM, "tarih": datetime.now().strftime("%Y-%m-%d %H:%M")})
    rc, _, err = _git("merge", "--ff-only", hedef)
    if rc != 0:
        raise _git_hata("ileri sarma başarısız", err)
    _yeniden_baslat_planla()
    _kapat_planla()
    return {"yeniden": True, "mesaj": f"Kod {son['surum']} sürümüne alındı; Kut yeniden başlıyor."}


def _geri_git():
    o = _ayar().get("onceki")
    if not (isinstance(o, dict) and o.get("tur") == "git" and re.fullmatch(r"[0-9a-f]{7,64}", str(o.get("commit") or ""))):
        raise ValueError("Geri dönülecek önceki sürüm kaydı yok.")
    if git_kirli():
        raise ValueError("Çalışma ağacında kaydedilmemiş değişiklik var; geri dönüş reddedildi.")
    if _git("cat-file", "-e", o["commit"] + "^{commit}", zaman=20)[0] != 0:
        raise ValueError("Önceki commit depoda bulunamadı.")
    rc, _, err = _git("reset", "--hard", o["commit"])
    if rc != 0:
        raise _git_hata("geri dönüş başarısız", err)
    _ayar_yaz(onceki=None)
    _yeniden_baslat_planla()
    _kapat_planla()
    return {"yeniden": True, "mesaj": f"Önceki sürüme ({o.get('surum', '?')}) dönüldü; Kut yeniden başlıyor."}


# ---- genel giriş noktaları ----
def uygula():
    """Elle istenir: son sürümü yeniden sorar, kurulum türüne göre uygular. Hata ValueError (okunur Türkçe ileti)."""
    if not _mesgul.acquire(blocking=False):
        raise ValueError("Başka bir güncelleme işlemi sürüyor.")
    try:
        d = denetle(elle=True)
        if not d["yeni"]:
            raise ValueError("Zaten en son sürümdesin.")
        tur = d["kurulum"]
        engel = _engel(tur)
        if engel:
            raise ValueError(engel + (f" Sürüm sayfası: {d['son']['url']}" if tur == "kaynak" else ""))
        return _uygula_exe(d["son"]) if tur == "exe" else _uygula_git(d["son"])
    finally:
        _mesgul.release()


def geri():
    if not _mesgul.acquire(blocking=False):
        raise ValueError("Başka bir güncelleme işlemi sürüyor.")
    try:
        tur = kurulum_turu()
        if tur == "exe":
            return _geri_exe()
        if tur == "git":
            return _geri_git()
        raise ValueError("Bu kurulumda geri dönüş yok.")
    finally:
        _mesgul.release()
