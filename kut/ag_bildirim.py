"""Kut sana gelsin: Kut kapalıyken de işletim sistemi bildirimiyle haber verir (haftada bir ya da her sabah, yalnız o gün bir şey varsa).

Varsayılan KAPALI. Yalnız kullanıcı Ayarlar'dan açınca zamanlanmış görev kurulur (Windows Görev Zamanlayıcı, macOS launchd, Linux systemd --user),
kapatınca kaldırılır. Zamanlanmış görev `kut.pyw --ozet --veri <veri>` çalıştırır: `calistir` özeti üretir (ag_ozet.olustur), gerekiyorsa bildirir;
sunucu AÇILMAZ, model ve ağ yok. Bildirim metni yalnız sayı taşır; kişi adı yalnız `adlar` açıksa (ilk 2 kişinin ilk adı), not/söz/taslak içeriği hiçbir zaman.
Kut'un PIN kilidi bildirim merkezini koruyamaz; bu yüzden adlar varsayılan kapalıdır.

Ayar (ayarlar.json → "bildirim"): acik, siklik (haftalik|gunluk), gun (0 = Pzt), saat (HH:MM), adlar, veri (mutlak yol), kurulum ("zamanlayici"|""), son.
Bildirim metni komut satırına gömülmez: Windows'ta toast XML'i ortam değişkeniyle, macOS'ta osascript argv ile, Linux'ta notify-send argümanıyla gider.
"""
import base64
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape

import ag_cekirdek as c
import ag_ice_aktar as ia

SIKLIKLAR = ("haftalik", "gunluk")
ALANLAR = ("acik", "siklik", "gun", "saat", "adlar")
VARSAYILAN = {"acik": False, "siklik": "haftalik", "gun": 0, "saat": "09:00", "adlar": False, "veri": "", "kurulum": "", "son": ""}
SAAT_DESENI = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")
ZAMAN_ASIMI = 20          # sn: bildirim betiği / platform araçları
BASLIK_AZAMI, METIN_AZAMI = 80, 220

WIN_GOREV = {"haftalik": "Kut\\Haftalik ozet", "gunluk": "Kut\\Gunluk ozet"}
WIN_GUN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")   # Task Scheduler XML DaysOfWeek öğeleri
WIN_XML_AD = "http://schemas.microsoft.com/windows/2004/02/mit/task"
WIN_AUMID = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"   # yedek: PowerShell'in kayıtlı AUMID'i
# Kut'un kendi uygulama kimliği: bildirim başlığında "Windows PowerShell" yerine "Kut" adı ve kün simgesi görünsün diye. Paketsiz uygulamalar için
# Windows 10/11'in tanıdığı kayıt: HKCU\Software\Classes\AppUserModelId\<kimlik> → DisplayName, IconUri (yalnız kullanıcı, yönetici gerekmez).
KUT_AUMID = "KorayKutlu.Kut"
WIN_KIMLIK_ANAHTAR = "Software\\Classes\\AppUserModelId\\" + KUT_AUMID
SIMGE_AD = "kut-bildirim.png"
TOAST_KIMLIK_ORTAM = "KUT_TOAST_APPID"
MAC_ETIKET = "com.koraykutlu.kut.ozet"
LINUX_BIRIM = "kut-ozet"
LINUX_GUN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
TOAST_ORTAM = "KUT_TOAST_XML"

# Saf ASCII (PowerShell 5.1). Toast XML'i ortam değişkeninden okur; çıkış kodu: 0 gösterildi, 2 hata. (NotificationSetting PS 5.1'de null döner; 'bildirimler kapalı' denetimi yapılamaz.)
PS_BETIK = """$ErrorActionPreference = 'Stop'
try {
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
  [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
  $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
  $xml.LoadXml($env:KUT_TOAST_XML)
  $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
  $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:KUT_TOAST_APPID)
  $notifier.Show($toast)
} catch { exit 2 }
exit 0
"""

_UNVANLAR = {"dr", "prof", "doc", "av", "sayin", "uzm", "yrd", "op", "mt"}   # c.sade biçimi; ilk ad değildir
_SAYGI = {"hoca", "bey", "hanim", "abla", "abi"}                              # ilk adla birlikte kalır


class KurulumHatasi(RuntimeError):
    """Zamanlanmış görev kurulamadı/kaldırılamadı; iletisi kullanıcıya gösterilebilir (içerik taşımaz)."""


# ---------- küçük yardımcılar ----------
def _platform():
    p = sys.platform
    return "windows" if p == "win32" else "macos" if p == "darwin" else "linux" if p.startswith("linux") else "diger"


def _ev():
    return os.path.expanduser("~")


def _uid():
    return os.getuid() if hasattr(os, "getuid") else 0


def _sistem32(exe, *alt):
    """Windows araçlarını PATH'ten değil System32'den ara (yoksa adıyla bırak)."""
    kok = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    yol = os.path.join(kok, "System32", *alt, exe)
    return yol if os.path.isfile(yol) else exe


def _powershell():
    return _sistem32("powershell.exe", "WindowsPowerShell", "v1.0")


def _calistir(args, ortam=None, zaman_asimi=ZAMAN_ASIMI):
    """Kabuksuz alt süreç; pencere açmaz. OSError/TimeoutExpired çağırana gider."""
    return subprocess.run(args, capture_output=True, timeout=zaman_asimi, env=ortam,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)


def _metne(b):
    if isinstance(b, str):
        return b
    for kodlama in (("oem",) if os.name == "nt" else ()) + ("utf-8",):
        try:
            return (b or b"").decode(kodlama, "replace")
        except LookupError:
            continue
    return ""


def _hata_ozeti(p):
    """Alt süreç çıktısından tek satır (≤ 160): kullanıcıya 'neden' göstermek için."""
    for kaynak in (getattr(p, "stderr", b""), getattr(p, "stdout", b"")):
        for satir in _metne(kaynak).splitlines():
            if satir.strip():
                return re.sub(r"\s+", " ", satir).strip()[:160]
    return ""


def _kontrol_siz(s, azami):
    """Tek satıra indir: kontrol karakterleri/yarım vekil çiftler atılır, boşluklar birleşir, azamiye kırpılır."""
    s = re.sub(r"[\x00-\x1f\x7f\ud800-\udfff\ufffe\uffff]+", " ", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= azami else s[:azami - 1].rstrip() + "…"


def _gunluk(m):
    """ia.DEPO/sunucu.log'a tek satır; içerik yok (yalnız hata türü)."""
    try:
        os.makedirs(ia.DEPO, exist_ok=True)
        with open(os.path.join(ia.DEPO, "sunucu.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} ozet-bildirim: {m}\n")
    except OSError:
        pass


def _atomik_yaz(yol, icerik):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    gecici = yol + ".tmp"
    with open(gecici, "wb") as f:
        f.write(icerik if isinstance(icerik, bytes) else icerik.encode("utf-8"))
    os.replace(gecici, yol)


# ---------- ayar ----------
def ayar():
    """ayarlar.json → bildirim, eksik/bozuk alanlar varsayılana düşer (elle düzenleme olabilir)."""
    ham = ia.ayarlar()
    ham = ham.get("bildirim") if isinstance(ham, dict) else None
    ham = ham if isinstance(ham, dict) else {}
    a = dict(VARSAYILAN)
    for k in ("acik", "adlar"):
        a[k] = ham.get(k) is True
    if ham.get("siklik") in SIKLIKLAR:
        a["siklik"] = ham["siklik"]
    g = ham.get("gun")
    if isinstance(g, int) and not isinstance(g, bool) and 0 <= g <= 6:
        a["gun"] = g
    if isinstance(ham.get("saat"), str) and SAAT_DESENI.fullmatch(ham["saat"]):
        a["saat"] = ham["saat"]
    for k in ("veri", "kurulum", "son"):
        if isinstance(ham.get(k), str):
            a[k] = ham[k]
    if a["kurulum"] not in ("", "zamanlayici"):
        a["kurulum"] = ""
    return a


def _ayar_yaz(a):
    tum = ia.ayarlar()
    tum = tum if isinstance(tum, dict) else {}
    tum["bildirim"] = {k: a.get(k, v) for k, v in VARSAYILAN.items()}
    ia.ayar_yaz(tum)


def _dogrula(g):
    """İstemciden gelen {acik, siklik, gun, saat, adlar} → mevcut ayarla birleşmiş yeni ayar. Eksik alan mevcut değeri korur; geçersiz/bilinmeyen alan ValueError."""
    if not isinstance(g, dict):
        raise ValueError("Geçersiz istek.")
    for k in g:
        if k not in ALANLAR:
            raise ValueError("Bilinmeyen alan: " + _kontrol_siz(k, 30))
    yeni = ayar()
    for k in ("acik", "adlar"):
        if k in g:
            if not isinstance(g[k], bool):
                raise ValueError(f"'{k}' doğru ya da yanlış olmalı.")
            yeni[k] = g[k]
    if "siklik" in g:
        if g["siklik"] not in SIKLIKLAR:
            raise ValueError("Sıklık 'haftalik' ya da 'gunluk' olmalı.")
        yeni["siklik"] = g["siklik"]
    if "gun" in g:
        if not isinstance(g["gun"], int) or isinstance(g["gun"], bool) or not 0 <= g["gun"] <= 6:
            raise ValueError("Gün 0 (Pazartesi) ile 6 (Pazar) arasında bir sayı olmalı.")
        yeni["gun"] = g["gun"]
    if "saat" in g:
        if not isinstance(g["saat"], str) or not SAAT_DESENI.fullmatch(g["saat"]):
            raise ValueError("Saat SS:DD biçiminde olmalı (ör. 09:00).")
        yeni["saat"] = g["saat"]
    return yeni


# ---------- komut ----------
def komut_listesi(a=None):
    """Zamanlanmış görevin çalıştıracağı argüman listesi (kabuksuz). Kaynak kurulumda pythonw.exe (Windows) + <depo>/kut.pyw; .exe'de sys.executable."""
    a = a or ayar()
    veri = os.path.abspath(a.get("veri") or c.VERI)
    exe = os.path.abspath(sys.executable)
    if c.DONDURULDU:
        return [exe, "--ozet", "--veri", veri]
    if _platform() == "windows" and os.path.basename(exe).lower() != "pythonw.exe":
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(pyw):
            exe = pyw
    return [exe, os.path.join(c.DEPO, "kut.pyw"), "--ozet", "--veri", veri]


def _komut_yazisi(a):
    l = komut_listesi(a)
    return subprocess.list2cmdline(l) if _platform() == "windows" else shlex.join(l)


def _komut_denetle(liste):
    for arg in liste:
        if re.search(r"[\x00-\x1f]", arg):
            raise KurulumHatasi("Yol satır sonu ya da denetim karakteri içeriyor; zamanlanmış görev kurulamaz.")
    if not c.DONDURULDU and not os.path.isfile(liste[1]):
        raise KurulumHatasi("kut.pyw bulunamadı; zamanlanmış görev kurulamaz.")


def _win_arguman(liste):
    """Exec <Arguments> değeri: komuttan sonraki argümanlar, Windows komut satırı kurallarıyla tırnaklanmış (yollarda boşluk/Unicode olabilir).
    Komut (<Command>) ayrı verildiği için eski schtasks /TR 261 karakter sınırı yoktur."""
    if any('"' in a for a in liste):
        raise KurulumHatasi("Yolda çift tırnak var; zamanlanmış görev kurulamaz.")
    return subprocess.list2cmdline(liste[1:])


def _win_baslangic(a, simdi=None):
    """İlk tetikleme (yerel saat): şimdiden sonraki ilk uygun an. Geçmiş bir başlangıç tarihi 'kaçırılmış çalıştırma' sayılıp görev kurulur kurulmaz çalışmasın."""
    simdi = simdi or datetime.now()
    saat, dakika = (int(x) for x in a["saat"].split(":"))
    gun = simdi.replace(hour=saat, minute=dakika, second=0, microsecond=0)
    for _ in range(8):
        if gun > simdi and (a["siklik"] == "gunluk" or gun.weekday() == a["gun"]):
            return gun
        gun += timedelta(days=1)
    return gun


def _win_xml(a, liste, simdi=None):
    """Görev tanımı (Task Scheduler XML 1.2): pilde de başlar, kaçırılan çalıştırma sonradan yapılır, tek örnek, 5 dk sınır, yalnız oturum açıkken (InteractiveToken)."""
    arg, baslangic = _win_arguman(liste), _win_baslangic(a, simdi).strftime("%Y-%m-%dT%H:%M:%S")
    sik = ("<ScheduleByWeek><DaysOfWeek><%s /></DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek>" % WIN_GUN[a["gun"]]
           if a["siklik"] == "haftalik" else "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>")
    return ('<?xml version="1.0" encoding="UTF-16"?>\n<Task version="1.2" xmlns="%s">\n'
            "  <RegistrationInfo><Description>Kut sana gelsin: ozet bildirimi</Description></RegistrationInfo>\n"
            "  <Triggers><CalendarTrigger><StartBoundary>%s</StartBoundary><Enabled>true</Enabled>%s</CalendarTrigger></Triggers>\n"
            '  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>\n'
            "  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
            "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable>"
            "<RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled>"
            "<Hidden>false</Hidden><ExecutionTimeLimit>PT5M</ExecutionTimeLimit><Priority>7</Priority></Settings>\n"
            '  <Actions Context="Author"><Exec><Command>%s</Command><Arguments>%s</Arguments></Exec></Actions>\n</Task>\n'
            % (WIN_XML_AD, baslangic, sik, escape(liste[0]), escape(arg)))


# ---------- destek ----------
def _destek():
    """(var mı, yoksa nedeni)."""
    p = _platform()
    if p == "windows":
        if not shutil.which("schtasks") and _sistem32("schtasks.exe") == "schtasks.exe":
            return False, "Görev Zamanlayıcı (schtasks) bulunamadı."
        return True, ""
    if p == "macos":
        return (True, "") if shutil.which("launchctl") and shutil.which("osascript") else (False, "launchctl/osascript bulunamadı.")
    if p == "linux":
        if not shutil.which("systemctl"):
            return False, "systemd (systemctl) bulunamadı."
        if not shutil.which("notify-send"):
            return False, "notify-send bulunamadı (libnotify kur)."
        return True, ""
    return False, "Bu işletim sistemi desteklenmiyor."


# ---------- Windows ----------
def _schtasks():
    return _sistem32("schtasks.exe")


def _win_var(ad):
    return _calistir([_schtasks(), "/Query", "/TN", ad]).returncode == 0


def _win_kur(a, liste):
    ad = WIN_GOREV[a["siklik"]]
    xml = _win_xml(a, liste)
    dosya = None
    try:
        fd, dosya = tempfile.mkstemp(prefix="kut-gorev-", suffix=".xml")
        with os.fdopen(fd, "wb") as f:
            f.write(b"\xff\xfe" + xml.encode("utf-16-le"))   # Görev Zamanlayıcı UTF-16 LE (BOM'lu) bekler
        p = _calistir([_schtasks(), "/Create", "/F", "/TN", ad, "/XML", dosya])
    finally:
        if dosya:
            try:
                os.remove(dosya)
            except OSError:
                pass
    if p.returncode != 0:
        raise KurulumHatasi(f"Görev Zamanlayıcı'ya görev eklenemedi (kod {p.returncode}). {_hata_ozeti(p)}".strip())
    diger = WIN_GOREV["gunluk" if a["siklik"] == "haftalik" else "haftalik"]
    try:
        if _win_var(diger):
            _calistir([_schtasks(), "/Delete", "/F", "/TN", diger])
    except (OSError, subprocess.SubprocessError):
        pass   # eski sıklığın görevi kalırsa calistir ayara bakar; asıl kurulum tamam


def _win_kaldir():
    for ad in WIN_GOREV.values():
        if not _win_var(ad):
            continue
        p = _calistir([_schtasks(), "/Delete", "/F", "/TN", ad])
        if p.returncode != 0 and _win_var(ad):
            raise KurulumHatasi(f"Görev Zamanlayıcı'dan görev kaldırılamadı (kod {p.returncode}). {_hata_ozeti(p)}".strip())


# ---------- macOS ----------
def _mac_plist():
    return os.path.join(_ev(), "Library", "LaunchAgents", MAC_ETIKET + ".plist")


def _mac_kur(a, liste):
    saat, dakika = (int(x) for x in a["saat"].split(":"))
    zaman = {"Hour": saat, "Minute": dakika}
    if a["siklik"] == "haftalik":
        zaman["Weekday"] = (a["gun"] + 1) % 7   # launchd: 1 = Pzt ... 6 = Cmt, 0 = Pazar
    icerik = plistlib.dumps({"Label": MAC_ETIKET, "ProgramArguments": liste, "StartCalendarInterval": zaman,
                             "RunAtLoad": False, "ProcessType": "Background"})
    yol = _mac_plist()
    _atomik_yaz(yol, icerik)
    alan = f"gui/{_uid()}"
    _calistir(["launchctl", "bootout", f"{alan}/{MAC_ETIKET}"])   # yüklü değilse hata verir: önemsenmez
    p = _calistir(["launchctl", "bootstrap", alan, yol])
    if p.returncode != 0:
        raise KurulumHatasi(f"launchd görevi yüklenemedi (kod {p.returncode}). {_hata_ozeti(p)}".strip())


def _mac_kaldir():
    yol = _mac_plist()
    p = _calistir(["launchctl", "bootout", f"gui/{_uid()}/{MAC_ETIKET}"])
    if p.returncode != 0 and _mac_yuklu():
        raise KurulumHatasi(f"launchd görevi kaldırılamadı (kod {p.returncode}). {_hata_ozeti(p)}".strip())
    try:
        os.remove(yol)
    except FileNotFoundError:
        pass


def _mac_yuklu():
    return _calistir(["launchctl", "print", f"gui/{_uid()}/{MAC_ETIKET}"]).returncode == 0


# ---------- Linux ----------
def _linux_dizin():
    return os.path.join(_ev(), ".config", "systemd", "user")


def _systemd_tirnak(arg):
    """ExecStart argümanı: \\ " için ters bölü, % ve $ ikilenir (systemd belirteç/ortam açılımı)."""
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'


def _linux_birimler(a, liste):
    gun = (LINUX_GUN[a["gun"]] + " ") if a["siklik"] == "haftalik" else ""
    servis = ("[Unit]\nDescription=Kut ozet bildirimi\n\n[Service]\nType=oneshot\n"
              "ExecStart=" + " ".join(_systemd_tirnak(x) for x in liste) + "\n")
    zamanlayici = ("[Unit]\nDescription=Kut ozet zamanlayicisi\n\n[Timer]\n"
                   f"OnCalendar={gun}*-*-* {a['saat']}:00\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n")
    return servis, zamanlayici


def _linux_kur(a, liste):
    servis, zamanlayici = _linux_birimler(a, liste)
    d = _linux_dizin()
    _atomik_yaz(os.path.join(d, LINUX_BIRIM + ".service"), servis)
    _atomik_yaz(os.path.join(d, LINUX_BIRIM + ".timer"), zamanlayici)
    for args in (["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", LINUX_BIRIM + ".timer"]):
        p = _calistir(args)
        if p.returncode != 0:
            raise KurulumHatasi(f"systemd zamanlayıcısı etkinleştirilemedi (kod {p.returncode}). {_hata_ozeti(p)}".strip())


def _linux_kaldir():
    d = _linux_dizin()
    var = any(os.path.exists(os.path.join(d, LINUX_BIRIM + s)) for s in (".timer", ".service"))
    if not var:
        return
    _calistir(["systemctl", "--user", "disable", "--now", LINUX_BIRIM + ".timer"])   # etkin değilse hata: önemsenmez
    for s in (".timer", ".service"):
        try:
            os.remove(os.path.join(d, LINUX_BIRIM + s))
        except FileNotFoundError:
            pass
    _calistir(["systemctl", "--user", "daemon-reload"])


def _linux_kurulu():
    d = _linux_dizin()
    return (os.path.isfile(os.path.join(d, LINUX_BIRIM + ".timer"))
            and _calistir(["systemctl", "--user", "is-enabled", LINUX_BIRIM + ".timer"]).returncode == 0)


# ---------- genel API ----------
def _kurulu(a):
    p = _platform()
    if p == "windows":
        return _win_var(WIN_GOREV[a["siklik"]])
    if p == "macos":
        return os.path.isfile(_mac_plist()) and _mac_yuklu()
    if p == "linux":
        return _linux_kurulu()
    return False


def kur(a):
    """Platforma göre zamanlanmış görevi kurar (varsa yenisiyle değiştirir). Başarısızlıkta KurulumHatasi."""
    a = {**VARSAYILAN, **a}
    destek, neden = _destek()
    if not destek:
        raise KurulumHatasi("Bu bilgisayarda zamanlanmış görev kurulamıyor: " + neden)
    liste = komut_listesi(a)
    _komut_denetle(liste)
    try:
        {"windows": _win_kur, "macos": _mac_kur, "linux": _linux_kur}[_platform()](a, liste)
    except KurulumHatasi:
        raise
    except subprocess.TimeoutExpired:
        raise KurulumHatasi("Zamanlayıcı aracı zamanında yanıt vermedi.")
    except OSError as e:
        raise KurulumHatasi("Zamanlanmış görev kurulamadı: " + _kontrol_siz(e.strerror or type(e).__name__, 120))


def kaldir():
    """Zamanlanmış görevi kaldırır; yoksa sessizce biter."""
    if not _destek()[0]:
        return
    try:
        {"windows": _win_kaldir, "macos": _mac_kaldir, "linux": _linux_kaldir}[_platform()]()
        if _platform() == "windows":
            _win_kimlik_sil()
    except KurulumHatasi:
        raise
    except subprocess.TimeoutExpired:
        raise KurulumHatasi("Zamanlayıcı aracı zamanında yanıt vermedi.")
    except OSError as e:
        raise KurulumHatasi("Zamanlanmış görev kaldırılamadı: " + _kontrol_siz(e.strerror or type(e).__name__, 120))


def durum():
    """ayar + destek/platform/kurulu (görev gerçekten var mı) + komut (gösterim için). İstisna fırlatmaz."""
    a = ayar()
    destek, neden = _destek()
    d = {**a, "destek": destek, "destek_neden": neden, "platform": _platform(), "kurulu": False, "komut": ""}
    try:
        d["komut"] = _komut_yazisi(a)
    except Exception:
        pass
    if destek:
        try:
            d["kurulu"] = bool(_kurulu(a))
        except Exception:
            pass
    return d


def ayarla(g):
    """Girdiyi sıkı doğrular; açılınca kurar, kapanınca kaldırır, ayarı yazar, durum() döndürür.
    Kurulum başarısızsa ayar 'acik' kalmaz (yazılır: kapalı) ve KurulumHatasi fırlar; geçersiz girdi ValueError."""
    yeni = _dogrula(g)
    yeni["veri"] = os.path.abspath(c.VERI)
    if yeni["acik"]:
        try:
            kur(yeni)
        except KurulumHatasi:
            yeni["acik"], yeni["kurulum"] = False, ""
            try:
                kaldir()   # yarım/eski görev kalmasın (en iyi çaba)
            except Exception:
                pass
            _ayar_yaz(yeni)
            raise
        yeni["kurulum"] = "zamanlayici"
    else:
        try:
            kaldir()
        except KurulumHatasi:
            yeni["acik"] = False   # görev kalsa da calistir kapalı ayarda bir şey yapmaz
            _ayar_yaz(yeni)
            raise
        yeni["kurulum"] = ""
    _ayar_yaz(yeni)
    return durum()


# ---------- bildirim ----------
def _toast_xml(baslik, metin):
    ent = {'"': "&quot;", "'": "&apos;"}
    return ('<toast><visual><binding template="ToastGeneric"><text>' + escape(baslik, ent) + "</text><text>" + escape(metin, ent)
            + "</text></binding></visual></toast>")


def _arg_guvenli(s):
    """macOS/Linux argümanı '-' ile başlayıp seçenek sayılmasın."""
    return s.lstrip("- ") or "Kut"


def _simge_yolu():
    """Kut simgesinin (kut.ico) en büyük PNG karesi ayar klasörüne çıkarılır: .exe'de varlıklar geçici klasördedir, bildirim simgesi kalıcı yol ister."""
    hedef = os.path.join(ia.DEPO, SIMGE_AD)
    if os.path.isfile(hedef):
        return hedef
    import struct
    for kok in (getattr(c, "VARLIK", None), os.path.dirname(os.path.abspath(__file__))):
        ico = os.path.join(kok or "", "kut.ico")
        try:
            with open(ico, "rb") as f:
                d = f.read()
            say = struct.unpack("<HHH", d[:6])[2]
            kareler = [struct.unpack("<BBBBHHII", d[6 + 16 * i:22 + 16 * i]) for i in range(say)]
            w, _, _, _, _, _, boy, yer = max(kareler, key=lambda x: x[0] or 256)
            png = d[yer:yer + boy]
            if png[:4] != b"\x89PNG":
                continue
            os.makedirs(ia.DEPO, exist_ok=True)
            gecici = hedef + ".yeni"
            with open(gecici, "wb") as f:
                f.write(png)
            os.replace(gecici, hedef)
            return hedef
        except (OSError, struct.error, ValueError):
            continue
    return ""


def _win_kimlik():
    """Kut'un bildirim kimliğini kaydeder (idempotent) ve kullanılacak AppId'yi döner; olmazsa PowerShell'in kimliğine düşer (bildirim yine çıkar)."""
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WIN_KIMLIK_ANAHTAR) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "Kut")
            simge = _simge_yolu()
            if simge:
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, simge)
            winreg.SetValueEx(k, "IconBackgroundColor", 0, winreg.REG_SZ, "FF0B2547")   # Kut laciverti
        return KUT_AUMID
    except Exception:
        return WIN_AUMID


def _win_kimlik_sil():
    """Bildirim kapatılınca Kut'un kimlik kaydını ve çıkarılan simgeyi kaldırır (iz bırakmaz)."""
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, WIN_KIMLIK_ANAHTAR)
    except Exception:
        pass
    try:
        os.remove(os.path.join(ia.DEPO, SIMGE_AD))
    except OSError:
        pass


def bildir(baslik, metin):
    """İşletim sistemi bildirimi gösterir. Başarılıysa True; hata, zaman aşımı, kapalı bildirim ya da desteksiz platformda False (asla istisna)."""
    try:
        baslik, metin = _kontrol_siz(baslik, BASLIK_AZAMI), _kontrol_siz(metin, METIN_AZAMI)
        if not baslik and not metin:
            return False
        p = _platform()
        if p == "windows":
            kodlu = base64.b64encode(PS_BETIK.encode("utf-16-le")).decode("ascii")
            ortam = {**os.environ, TOAST_ORTAM: _toast_xml(baslik, metin), TOAST_KIMLIK_ORTAM: _win_kimlik()}
            sonuc = _calistir([_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", kodlu], ortam)
        elif p == "macos":
            sonuc = _calistir(["osascript", "-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                               "-e", "end run", _arg_guvenli(baslik), _arg_guvenli(metin)])
        elif p == "linux":
            sonuc = _calistir(["notify-send", "-a", "Kut", "--", baslik or "Kut", metin or baslik])
        else:
            return False
        return sonuc.returncode == 0
    except Exception:
        return False


def _ilk_ad(ad):
    """Hitap (ag_ozet ile aynı kural): baştaki unvanlar atlanır, 'Selin Hoca' gibi saygı eki ilk adla kalır; en çok 30 karakter."""
    j = _kontrol_siz(ad, 80).split()
    while len(j) > 1 and c.sade(j[0]) in _UNVANLAR:
        j.pop(0)
    if len(j) > 1 and c.sade(j[1]) in _SAYGI:
        return " ".join(j[:2])[:30]
    return j[0][:30] if j else ""


def _bekliyor(oge):
    """Sonuç işaretlenmemiş (ag_ozet `sonuc`: defterden taze). Yaptım/İşe yaradı/Ertelendi/Atlandı işaretli madde bildirime girmez; alan yoksa bekliyor sayılır."""
    return oge.get("sonuc") in (None, "", "bekliyor")


def _liste(x):
    return [i for i in x if isinstance(i, dict) and _bekliyor(i)] if isinstance(x, list) else []


def metin(ozet, adlar=False, siklik="haftalik"):
    """(başlık, gövde) ya da gösterilecek bir şey yoksa None. Yalnız sayı; `adlar` True ise madde sahibi en çok 2 kişinin ilk adı + (+N).
    Not, söz metni, taslak, neden, adım hiçbir zaman girmez. Sonucu işaretlenmiş (bekliyor dışı) maddeler sayılmaz."""
    if not isinstance(ozet, dict) or ozet.get("bos"):
        return None
    maddeler, sozler = _liste(ozet.get("maddeler")), _liste(ozet.get("sozler"))
    kisiler = []
    for m in maddeler:
        anahtar = m.get("id") or m.get("ad")
        if anahtar and anahtar not in [k[0] for k in kisiler]:
            kisiler.append((anahtar, m.get("ad")))
    k_say, s_say = len(kisiler) or len(maddeler), len(sozler)
    if not k_say and not s_say:
        return None
    zaman = "Bugün" if siklik == "gunluk" else "Bu hafta"
    adlar_listesi = [x for x in (_ilk_ad(a) for _, a in kisiler[:2]) if x] if adlar is True else []
    if adlar_listesi:
        ek = f" (+{k_say - len(adlar_listesi)})" if k_say > len(adlar_listesi) else ""
        govde = f"{zaman} {' ve '.join(adlar_listesi)} seni bekliyor{ek}." + (f" {s_say} söz de var." if s_say else "")
    elif k_say and s_say:
        govde = f"{zaman} {k_say} kişi ve {s_say} söz seni bekliyor."
    elif k_say:
        govde = f"{zaman} {k_say} kişi seni bekliyor."
    else:
        govde = f"{zaman} {s_say} söz seni bekliyor."
    return "Kut", govde + " Özet Kut'ta hazır."


# ---------- zamanlanmış çalışma ----------
_VADE_ADIM = re.compile(r"\((?:bugün|\d+ gün gecikti)\)\s*$")
_VADE_SOZ = re.compile(r"^[^:]{1,40}: (?:bugün|\d+ gün gecikti)(?: · |$)")


def _tarih_gecti(deger, bugun):
    try:
        return bool(deger) and date.fromisoformat(str(deger)[:10]) <= bugun
    except ValueError:
        return False


def _vadesi_geldi(oge, bugun):
    """Özet öğesi bugün tarihli ya da gecikmiş ve sonucu hâlâ bekliyor mu?
    ag_ozet her kişi/söz maddesine `tarih` (ISO; ihmalde "") ve `sonuc` verir: `tarih` ≤ bugün VE sonuç bekliyor.
    Geriye uyum (yalnız `tarih` alanı hiç yoksa): yapısal alanlar (gecikmis, durum, vade/son/sonraki_tarih/son_tarih), sonra bu_hafta neden kalıbı."""
    if not isinstance(oge, dict) or not _bekliyor(oge):
        return False
    if "tarih" in oge:
        return _tarih_gecti(oge["tarih"], bugun)
    if oge.get("gecikmis") is True or oge.get("durum") in ("gecikmis", "bugun"):
        return True
    if any(_tarih_gecti(oge.get(alan), bugun) for alan in ("vade", "son", "sonraki_tarih", "son_tarih")):
        return True
    neden = oge.get("neden")
    return isinstance(neden, str) and bool(_VADE_ADIM.search(neden) or _VADE_SOZ.search(neden))


def _gunluk_suz(ozet, bugun):
    m = [x for x in _liste(ozet.get("maddeler")) if _vadesi_geldi(x, bugun)]
    s = [x for x in _liste(ozet.get("sozler")) if _vadesi_geldi(x, bugun)]
    return {**ozet, "maddeler": m, "sozler": s, "bos": not (m or s)}


def _haric_suz(ozet):
    """İkinci savunma katmanı (ag_ozet zaten süzer): maddenin kişi dosyası okunup haric.md ile eşleşiyorsa ya da dosya yoksa/okunamıyorsa madde sayılmaz."""
    liste = c.haric_listesi()

    def temiz(m):
        kid = m.get("id")
        if not c.gecerli_id(kid):
            return False
        try:
            k = c.kisi_oku(os.path.join(c.KISILER, f"{kid}.md"))
        except (OSError, ValueError):
            return False
        return k is not None and not k.get("haric") and not c.haric_mi(k, liste)

    return {**ozet, "maddeler": [m for m in _liste(ozet.get("maddeler")) if temiz(m)], "sozler": [m for m in _liste(ozet.get("sozler")) if temiz(m)]}


def _arg_deger(argv, ad):
    for i, a in enumerate(argv):
        if a == ad and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(ad + "="):
            return a[len(ad) + 1:]
    return ""


def calistir(argv, bugun=None):
    """`kut.pyw --ozet [--veri X] [--sessiz]`: veri klasörünü uygular, özeti üretir (ag_ozet.olustur), ayara göre bildirir. Sunucu açmaz, ağa çıkmaz.
    Ayar kapalıysa hiçbir şey yapmaz. Dönüş: 0 tamam, 1 beklenmeyen hata, 2 veri klasörü yok, 3 bildirim gösterilemedi.
    Hata günlüğe (ia.DEPO/sunucu.log) yalnız hata türüyle, içeriksiz yazılır."""
    try:
        argv = [str(x) for x in (argv or [])]
        veri = _arg_deger(argv, "--veri")
        if veri:
            if not os.path.isdir(veri):
                _gunluk("veri klasoru yok")   # eski/taşınmış yolu sessizce yeniden yaratma
                return 2
            c.veri_klasoru(veri)
        a = ayar()
        if not a["acik"]:
            return 0
        import ag_ozet   # geç içe aktarma: başka modül, yalnız bu yolda gerekli
        ozet = ag_ozet.olustur(bugun)
        if "--sessiz" in argv:
            return 0
        ozet = _haric_suz(ozet if isinstance(ozet, dict) else {})
        if a["siklik"] == "gunluk":
            ozet = _gunluk_suz(ozet, bugun or date.today())
        m = metin(ozet, a["adlar"], a["siklik"])
        if m is None:
            return 0
        if not bildir(*m):
            _gunluk("bildirim gosterilemedi")
            return 3
        son = ayar()   # ayarlar.json'a yazmadan hemen önce yeniden oku (sunucu arada ayar yazmış olabilir)
        son["son"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _ayar_yaz({**son, "veri": son["veri"] or a["veri"]})
        return 0
    except Exception as e:
        _gunluk("hata: " + type(e).__name__)
        return 1
