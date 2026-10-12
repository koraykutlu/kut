"""Kut hedefleri: tavsiyelerin bağlandığı kullanıcı hedefleri. Kaynak Markdown: <veri>/hedefler/<id>.md.

Frontmatter: baslik, durum (taslak|aktif|beklemede|tamam|birakildi), tur, son_tarih, oncelik (1 yüksek–3), olcut (başarı ölçütü),
anahtar[] (keşif eşleştirmesi için konu kelimeleri), neden, kaynak. Gövdede `## İlerleme` (tarihli satırlar) ve serbest notlar.
"taslak" = asistanın notlardan çıkardığı öneri; kullanıcı onaylayınca "aktif" olur. Hedefi kullanıcı yazar, asistan yalnız önerir.
"""
import os
import shutil
from datetime import date

import ag_cekirdek as c

DURUMLAR = {"taslak": "Taslak (onay bekliyor)", "aktif": "Aktif", "beklemede": "Beklemede", "tamam": "Tamamlandı", "birakildi": "Bırakıldı"}
TURLER = {"ag": "Ağ ve ilişkiler", "kariyer": "Kariyer", "akademik": "Akademik / sınav", "proje": "Proje / ürün",
          "etkinlik": "Etkinlik / yarışma", "finans": "Finans", "kisisel": "Kişisel"}
ALANLAR = ["baslik", "durum", "tur", "son_tarih", "oncelik", "olcut", "anahtar", "neden", "kaynak", "olusturma"]
ILERLEME = "İlerleme"


def klasor():
    return os.path.join(c.VERI, "hedefler")


def _yol(hid):
    if not c.gecerli_id(hid):
        raise ValueError("geçersiz hedef")
    return os.path.join(klasor(), hid + ".md")


def oku(hid):
    yol = _yol(hid)
    if not os.path.exists(yol):
        raise ValueError("hedef bulunamadı")
    h = c.kisi_oku(yol)
    h["id"] = hid
    h["anahtar"] = c.liste_yap(h.get("anahtar"))
    h["ilerleme"] = [x[2:].strip() for x in c.bolum_oku(h.get("govde"), ILERLEME).splitlines() if x.startswith("- ")]
    return h


def hepsi(durumlar=None):
    if not os.path.isdir(klasor()):
        return []
    liste = []
    for f in sorted(os.listdir(klasor())):
        if f.endswith(".md") and c.gecerli_id(f[:-3]):
            try:
                h = oku(f[:-3])
            except (ValueError, OSError):
                continue
            if not durumlar or h.get("durum") in durumlar:
                liste.append(h)
    sira = {"aktif": 0, "taslak": 1, "beklemede": 2, "tamam": 3, "birakildi": 4}
    return sorted(liste, key=lambda h: (sira.get(h.get("durum"), 5), str(h.get("oncelik") or "2"), h.get("son_tarih") or "9999"))


def _yaz(hid, alanlar, govde):
    satirlar = []
    for k in ALANLAR:
        v = alanlar.get(k, "")
        if k == "anahtar":
            v = "[" + ", ".join(c._temiz(x).replace(",", " ").replace("[", "(").replace("]", ")") for x in c.liste_yap(v) if c._temiz(x)) + "]"
        else:
            v = c._temiz(v)
            if v.startswith("["):
                v = "(" + v[1:]
        satirlar.append(f"{k}: {v}".rstrip())
    os.makedirs(klasor(), exist_ok=True)
    with open(_yol(hid), "w", encoding="utf-8", newline="\n") as f:
        f.write("---\n" + "\n".join(satirlar) + "\n---\n" + govde.strip() + "\n")


def kaydet(g, kaynak="kullanıcı, Kut arayüzü"):
    """Yeni hedef ya da düzenleme (kullanıcı beyanı). Dönen: id."""
    baslik = " ".join(str(g.get("baslik") or "").split())[:140]
    if not baslik:
        raise ValueError("hedefin başlığı gerekli")
    durum = g.get("durum") or "aktif"
    if durum not in DURUMLAR:
        raise ValueError("bilinmeyen durum")
    tur = g.get("tur") or "proje"
    if tur not in TURLER:
        raise ValueError("bilinmeyen tür")
    son = str(g.get("son_tarih") or "")
    if son:
        date.fromisoformat(son)
    oncelik = str(g.get("oncelik") or "2")
    if oncelik not in ("1", "2", "3"):
        raise ValueError("öncelik 1–3")
    anahtar = g.get("anahtar") or []
    if isinstance(anahtar, str):
        anahtar = [x for x in anahtar.replace(";", ",").split(",")]
    anahtar = [" ".join(x.split()).lower()[:40] for x in anahtar if x.strip()][:20]
    hid = g.get("id")
    if hid:
        eski = oku(hid)
        govde = eski.get("govde") or ""
        olusturma, kaynak = eski.get("olusturma") or date.today().isoformat(), eski.get("kaynak") or kaynak
    else:
        hid = c.slug(baslik)[:60].strip("-") or "hedef"
        t, i = hid, 2
        while os.path.exists(_yol(t)):
            t, i = f"{hid}-{i}", i + 1
        hid, govde, olusturma = t, f"# {baslik}\n\n## {ILERLEME}\n", date.today().isoformat()
    alanlar = {"baslik": baslik, "durum": durum, "tur": tur, "son_tarih": son, "oncelik": oncelik,
               "olcut": " ".join(str(g.get("olcut") or "").split())[:300], "anahtar": anahtar,
               "neden": " ".join(str(g.get("neden") or "").split())[:400], "kaynak": kaynak, "olusturma": olusturma}
    _yaz(hid, alanlar, govde)
    return hid


def ilerleme_ekle(hid, metin, tarih=None):
    h = oku(hid)
    metin = " ".join(str(metin or "").split())[:300]
    if not metin:
        raise ValueError("ilerleme notu boş")
    gun = (date.fromisoformat(tarih) if tarih else date.today()).strftime("%d.%m.%Y")
    govde = c.bolume_ekle(h.pop("govde") or "", ILERLEME, f"{gun} · {metin}")
    _yaz(hid, h, govde)


def arsivle(hid):
    yol = _yol(hid)
    if not os.path.exists(yol):
        raise ValueError("hedef bulunamadı")
    hedef = os.path.join(c.ARSIV, "hedefler")
    os.makedirs(hedef, exist_ok=True)
    shutil.move(yol, os.path.join(hedef, f"{hid}-{date.today():%Y%m%d}.md"))


def istem_blogu(hedefler=None):
    """Modele giden kısa hedef listesi."""
    hedefler = hepsi(("aktif", "taslak", "beklemede")) if hedefler is None else hedefler
    satir = []
    for h in hedefler:
        kalan = ""
        if h.get("son_tarih"):
            g = (date.fromisoformat(h["son_tarih"]) - date.today()).days
            kalan = f" · son tarih {h['son_tarih']} ({g} gün)"
        son = h["ilerleme"][-2:] if h.get("ilerleme") else []
        satir.append(f"- [{h['id']}] {h.get('baslik')} · {DURUMLAR.get(h.get('durum'), h.get('durum'))} · {TURLER.get(h.get('tur'), '')}"
                     f" · öncelik {h.get('oncelik') or 2}{kalan}"
                     f"{' · ölçüt: ' + h['olcut'] if h.get('olcut') else ''}{' · neden: ' + h['neden'] if h.get('neden') else ''}"
                     f"{' · son ilerleme: ' + ' | '.join(son) if son else ' · ilerleme kaydı yok'}")
    return "\n".join(satir) or "(hedef yok)"
