"""Kut ses sistemi: sesli cevap (EMA Lightning) ve sesli girdi (Whisper), ikisi de bu bilgisayarda.

Modeller Kut'un kendi Python'unda değil, kurulu oldukları ortamlarda çalışır (ag_ses_isci.py). Ortamlar ayarlar.json →
"ses": {"oku_python": ..., "yaz_python": ..., "yaz_model": "large-v3"} ile verilir; verilmezse kasadaki bilinen yerlere bakılır.
İşçi ilk istekte açılır, modeli bellekte tutar, 15 dk boşta kalınca kapanır (ekran kartı belleği boşalsın).
Ses kaydı diske yazılmaz; metin internete gönderilmez.
"""
import atexit
import json
import os
import re
import subprocess
import sys
import threading
import time

import ag_ice_aktar as ia

KOK = os.path.dirname(os.path.abspath(__file__))
ISCI = os.path.join(KOK, "ag_ses_isci.py")
BOSTA = 15 * 60
PY = os.path.join("Scripts", "python.exe") if os.name == "nt" else os.path.join("bin", "python")
# kasada bilinen ortamlar (seslendir becerisi ve video-sunum projesi); bulunamazsa ses kapalı kalır
BILINEN = {"oku": [(".claude", "tools", "ema", ".venv")], "yaz": [("projeler", "video-sunum", ".venv")]}


def _ayar():
    return ia.ayarlar().get("ses") or {}


def python_yolu(tur):
    yol = _ayar().get(f"{tur}_python")
    if yol:
        return yol if os.path.isfile(yol) else None
    d = KOK
    for _ in range(4):
        for parca in BILINEN[tur]:
            aday = os.path.join(d, *parca, PY)
            if os.path.isfile(aday):
                return aday
        d = os.path.dirname(d)
    return None


class Isci:
    def __init__(self, tur):
        self.tur, self.p, self.kilit, self.son, self.hata = tur, None, threading.Lock(), 0.0, ""

    def _baslat(self):
        py = python_yolu(self.tur)
        if not py:
            raise RuntimeError("ses ortamı bulunamadı")
        arg = [py, "-I", ISCI, self.tur]
        if self.tur == "yaz":
            arg += [_ayar().get("yaz_model") or "large-v3", _ayar().get("yaz_hesap") or "int8_float16"]
        os.makedirs(ia.DEPO, exist_ok=True)
        gunluk = open(os.path.join(ia.DEPO, f"ses-{self.tur}.log"), "a", encoding="utf-8")
        self.p = subprocess.Popen(arg, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=gunluk, cwd=KOK,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        gunluk.close()
        satir = self.p.stdout.readline()
        ilk = json.loads(satir) if satir else {"hazir": False, "hata": f"işçi açılamadı (ses-{self.tur}.log)"}
        if not ilk.get("hazir"):
            self.durdur()
            self.hata = ilk.get("hata", "")
            raise RuntimeError("ses modeli yüklenemedi: " + self.hata)
        self.hata = ""

    def istek(self, g):
        with self.kilit:
            self.son = time.time()
            if not self.p or self.p.poll() is not None:
                self._baslat()
            self.p.stdin.write((json.dumps(g) + "\n").encode("utf-8"))
            self.p.stdin.flush()
            satir = self.p.stdout.readline()
            self.son = time.time()
            if not satir:
                self.durdur()
                raise RuntimeError("ses işçisi kapandı")
            r = json.loads(satir)
            if not r.get("ok"):
                raise RuntimeError(r.get("hata") or "ses hatası")
            return r

    def isit(self):
        """Modeli arka planda yükle (ör. mikrofon açılınca, kullanıcı konuşurken)."""
        def calis():
            with self.kilit:
                self.son = time.time()
                if not self.p or self.p.poll() is not None:
                    try:
                        self._baslat()
                    except Exception:
                        pass
        threading.Thread(target=calis, daemon=True).start()

    def durdur(self):
        if self.p and self.p.poll() is None:
            try:
                self.p.stdin.close()
                self.p.wait(timeout=5)
            except Exception:
                self.p.kill()
        self.p = None


ISCILER = {"oku": Isci("oku"), "yaz": Isci("yaz")}


def _bekci():
    while True:
        time.sleep(60)
        for i in ISCILER.values():
            if i.p and time.time() - i.son > BOSTA and i.kilit.acquire(blocking=False):
                try:
                    i.durdur()
                finally:
                    i.kilit.release()


threading.Thread(target=_bekci, daemon=True).start()
atexit.register(lambda: [i.durdur() for i in ISCILER.values()])


def durum():
    return {t: bool(python_yolu(t)) for t in ISCILER} | {"hata": {t: i.hata for t, i in ISCILER.items() if i.hata}}


def konusma_metni(md):
    """Kut'un Markdown cevabını sesli okunacak düz metne çevirir."""
    s = re.sub(r"```.*?```", " ", md, flags=re.S)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"\S+@\S+\.\w+", " ", s)
    satirlar = []
    for satir in s.splitlines():
        satir = re.sub(r"^\s*(#+|[-*+•]|\d+[.)]|>)\s*", "", satir)
        satir = re.sub(r"[*_~|#→←✓✦·]+", " ", satir)
        satir = " ".join(satir.split())
        if satir:
            satirlar.append(satir if satir[-1] in ".!?:;," else satir + ".")
    return " ".join(satirlar)[:2500]


def oku(metin, hiz=1.0):
    metin = konusma_metni(metin)
    if not metin:
        raise ValueError("okunacak metin yok")
    return ISCILER["oku"].istek({"metin": metin, "hiz": hiz})


def yaz(pcm_b64, ipucu=""):
    if len(pcm_b64) > 16_000_000:  # ~3 dk
        raise ValueError("kayıt çok uzun")
    return ISCILER["yaz"].istek({"pcm": pcm_b64, "ipucu": ipucu})


def isit(tur):
    if tur in ISCILER and python_yolu(tur):
        ISCILER[tur].isit()
