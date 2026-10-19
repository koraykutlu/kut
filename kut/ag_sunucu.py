"""Kut (eski adı Ağım): yalnız bu bilgisayarda (127.0.0.1) çalışan düzenlenebilir ağ sunucusu.

Kullanım: Kut kısayolu (veya `py -3 kut.pyw [--veri KLASÖR] [--tarayicisiz]`). Tarayıcıda açılır; sayfa kapandıktan ~20 dk sonra kendiliğinden durur.
Yazdığı her şey veri klasöründe Markdown: ben.md, kisiler/*.md, foto/, iliskiler.md. İnternete bir şey göndermez.
Güvenlik: yalnız 127.0.0.1'e bağlanır, Host başlığını denetler, her değişiklik isteği oturuma özel anahtar ister.
"""
import base64
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ag_cekirdek as c  # noqa: E402
import ag_ice_aktar as ia  # noqa: E402
import ag_takvim as tk  # noqa: E402
import ag_linkedin as li  # noqa: E402
import ag_ders_yapistir as dy  # noqa: E402
import ag_ice_ortak as ort  # noqa: E402
import ag_analiz as an  # noqa: E402
import ag_model as mdl  # noqa: E402
import ag_kaynak as kn  # noqa: E402
import ag_ders_girdi as dg  # noqa: E402
import ag_soz as sz  # noqa: E402
import ag_kapi as kapi  # noqa: E402
import ag_baglam as bg  # noqa: E402
import ag_tutarlilik as tu  # noqa: E402
import ag_vault as vault  # noqa: E402
import ag_kasa_kisi as kk  # noqa: E402
import ag_ses as ses  # noqa: E402
import ag_ses_kur as sesk  # noqa: E402
import ag_kilit as kl  # noqa: E402
import ag_hedef as hd  # noqa: E402
import ag_kesif as ks  # noqa: E402
import ag_strateji as st  # noqa: E402
import ag_ajanda as aj  # noqa: E402
import ag_guncelle as gu  # noqa: E402
import ag_dil  # noqa: E402
import ag_yol as yl  # noqa: E402
import ag_brifing as br  # noqa: E402
import ag_sonuc as sn  # noqa: E402
import ag_ozet as oz  # noqa: E402
import ag_bildirim as bd  # noqa: E402
import ag_demo  # noqa: E402
import goc  # noqa: E402

PORT = 47318
ANAHTAR = secrets.token_urlsafe(24)
BOSTA_DUR = 20 * 60
son_istek = time.time()
kilit = threading.Lock()
GUNLUK = os.path.join(ia.DEPO, "sunucu.log")


def hata_izi():
    """Günlüğe yalnız çağrı izi + hata türü (+ OSError iletisi) yazılır; istek gövdesi/kişi/sohbet içeriği taşıyabilecek ileti yazılmaz."""
    t, e, tb = sys.exc_info()
    ek = f" {e}"[:160] if isinstance(e, OSError) else ""
    return "".join(traceback.format_tb(tb)) + (t.__name__ if t else "?") + ek


def gunluk(m):
    os.makedirs(ia.DEPO, exist_ok=True)
    with open(GUNLUK, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {m}\n")


def statik_yenile():
    """Sunucusuz açılabilen ag.html anlık görüntüsünü de güncel tut. Kilit açıksa üretilmez (kilidi atlatırdı); eskisi kaldırılır."""
    if kl.kurulu():
        try:
            os.remove(os.path.join(c.VERI, "ag.html"))
        except FileNotFoundError:
            pass
        return
    try:
        with open(os.path.join(c.VERI, "ag.html"), "w", encoding="utf-8") as f:
            f.write(c.sayfa(c.veri_hazirla(), dil=ag_dil.etkin()))
    except Exception:
        gunluk("statik: " + hata_izi())


def kisi_bul(kid):
    yol = os.path.join(c.KISILER, f"{kid}.md")
    if not c.gecerli_id(kid) or not os.path.exists(yol):
        raise ValueError("kişi bulunamadı")
    return c.kisi_oku(yol)


def foto_coz(veri):
    if not veri:
        return None
    ham = base64.b64decode(veri.split(",", 1)[-1])
    if not (ham[:3] == b"\xff\xd8\xff" or ham[1:4] == b"PNG"):
        raise ValueError("fotoğraf JPEG veya PNG olmalı")
    if len(ham) > 3_000_000:
        raise ValueError("fotoğraf çok büyük")
    return ham


DUZENLENEBILIR = [a for a in c.ALAN_SIRASI if a != "foto"]


def ilk_ad():
    return (c.ben().get("ad") or "Ben").split()[0]


def ben_kaydet(g):
    alanlar = {k: g[k] for k in ("ad", "kurum", "rol", "asistan", "temas_basligi", "ilgiler", "karakter", "okul", "dersler", "dogum_gunu") if k in g}
    if alanlar.get("dogum_gunu") not in (None, ""):   # YYYY-AA-GG ya da AA-GG; başka hiçbir şey ben.md'ye yazılmaz
        dgn = str(alanlar["dogum_gunu"]).strip()
        if not re.fullmatch(r"(?:\d{4}-)?(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", dgn):
            raise ValueError("dogum_gunu: YYYY-AA-GG biçiminde olmalı")
        alanlar["dogum_gunu"] = dgn
    if "dersler" in alanlar:   # "bu dönem ISE 424 ve MATH 101 alıyorum" gibi serbest yazılan öğeler ders koduna ayrılır; kod olanlar aynen kalır
        alanlar["dersler"] = dg.liste_temizle(c.liste_yap(alanlar["dersler"]))
    ham = foto_coz(g.get("foto_veri"))
    if ham:
        alanlar["foto"] = c.foto_kaydet(c.ben_id(), ham)
    eski = c.ben()
    c.ben_yaz(alanlar)
    if any(k in alanlar and c.liste_yap(alanlar[k]) != c.liste_yap(eski.get(k)) for k in ("okul", "dersler")):
        threading.Thread(target=lambda: kaynak_doldur({"zorla": True}), daemon=True).start()  # hocalar ve bağları otomatik
    return {}


# ---------- işlemler ----------
def kisi_kaydet(g):
    ad = (g.get("ad") or "").strip()
    if not ad:
        raise ValueError("isim gerekli")
    kid = g.get("id")
    if kid:
        eski = kisi_bul(kid)
        govde = eski.pop("govde")
    else:
        kid = c.bos_slug(ad)
        eski = {}
        govde = c.yeni_govde(ad, g.get("kaynak") or f"{ilk_ad()}, ağ sayfasından eklendi ({date.today().isoformat()}).")
    alanlar = dict(eski)
    for a in DUZENLENEBILIR:
        if a in g:
            alanlar[a] = g[a]
    if "yakinlik" in g and str(g["yakinlik"]) != str(eski.get("yakinlik", "")):
        alanlar["yakinlik_kaynak"] = "sen"  # elle verilen yakınlığı içe aktarma ve asistan ezmez
    if g.get("not"):
        govde = govde.rstrip() + "\n\n" + str(g["not"]).strip() + "\n"
    ham = foto_coz(g.get("foto_veri"))
    if ham:
        alanlar["foto"] = c.foto_kaydet(kid, ham)
    alanlar.setdefault("foto", "")
    c.kisi_yaz(kid, alanlar, govde)
    return {"id": kid}


def temas(g):
    k = kisi_bul(g.get("id"))
    govde = k.pop("govde")
    tarih = g.get("tarih") or date.today().isoformat()
    date.fromisoformat(tarih)
    metin = " ".join(str(g.get("metin") or "").split())
    if not metin:
        raise ValueError("temas notu boş")
    kanal = (g.get("kanal") or "").strip()
    gun = datetime.strptime(tarih, "%Y-%m-%d").strftime("%d.%m.%Y")
    govde = c.temas_ekle(govde, f"{gun} · {kanal} · {metin}" if kanal else f"{gun} · {metin}")
    if not k.get("son_temas") or tarih > k["son_temas"]:
        k["son_temas"] = tarih
    if g.get("yakinlik") not in (None, ""):
        k["yakinlik"] = str(int(g["yakinlik"]))
    c.kisi_yaz(g["id"], k, govde)
    return {"id": g["id"]}


def kisi_arsivle(g):
    kid = g.get("id")
    kisi_bul(kid)
    hedef = os.path.join(c.ARSIV, "cikarilan")
    os.makedirs(hedef, exist_ok=True)
    yeni = os.path.join(hedef, f"{kid}-{date.today():%Y%m%d}.md")
    shutil.move(os.path.join(c.KISILER, f"{kid}.md"), yeni)
    os.utime(yeni, None)   # arşiv bakımı yaşı taşıma anından saysın (taşıma eski mtime'ı koruyabilir)
    return {"id": kid}


def iliski_ekle(g):
    a, b, tip = g.get("a"), g.get("b"), g.get("tip")
    if tip not in c.TIPLER:
        raise ValueError("bilinmeyen ilişki tipi")
    if a == b:
        raise ValueError("kişi kendisiyle ilişkilendirilemez")
    for x in (a, b):
        if x != c.ben_id():
            kisi_bul(x)
    iliskiler = [i for i in c.iliskileri_oku() if not ({i["a"], i["b"]} == {a, b} and i["tip"] == tip)]
    iliskiler.append({"a": a, "b": b, "tip": tip, "not": g.get("not", ""), "kaynak": g.get("kaynak") or ilk_ad(),
                      "tarih": date.today().isoformat()})
    c.iliskileri_yaz(iliskiler)
    return {}


def iliski_sil(g):
    iliskiler = c.iliskileri_oku()
    kalan = [i for i in iliskiler if not (i["a"] == g.get("a") and i["b"] == g.get("b") and i["tip"] == g.get("tip"))]
    c.iliskileri_yaz(kalan)
    return {"silinen": len(iliskiler) - len(kalan)}


def ice_aktar(g):
    ad = os.path.basename(g.get("ad") or "dosya.txt")
    ham = base64.b64decode(g.get("veri", "").split(",", 1)[-1])
    if len(ham) > 150_000_000:
        raise ValueError("dosya çok büyük")
    sakla = os.path.join(c.VERI, "gelen", "whatsapp") if g.get("sakla") else None
    return ia.ice_aktar(ad, ham, c.kisileri_oku(), sakla)


def adaylar_listesi(_=None):
    havuz = ia.adaylar()
    hl = c.haric_listesi()
    liste = []
    for a in havuz.values():
        if a.get("durum") != "yeni":
            continue
        b = dict(a)
        b["haric"] = c.haric_mi(a, hl)
        liste.append(b)
    puan = lambda a: -(sum(k.get("mesaj", 0) + k.get("ben_mesaj", 0) for k in a["kaynaklar"] if k["tip"] == "wa-birebir") * 10
                       + sum(k.get("mesaj", 0) for k in a["kaynaklar"] if k["tip"] == "wa-grup") + (50 if a.get("foto") else 0))
    liste.sort(key=puan)
    return {"adaylar": liste, "ayarlar": ia.ayarlar()}


def aday_ekle(g):
    havuz = ia.adaylar()
    eklenen, sohbet_kisileri = [], {}  # ham dosya → {sohbetteki ad: kişi id}
    benler = {c.sade(x) for x in ia.ben_adlari_al()}
    for s in g.get("secimler", []):
        a = havuz.get(s.get("id"))
        if not a or a.get("durum") != "yeni":
            continue
        if s.get("eslestir") == "ben" or c.sade(a["ad"]) in benler:
            a["durum"] = "ben"
            continue
        if c.gecerli_id(s.get("eslestir")) and s["eslestir"] != "yeni" and os.path.exists(os.path.join(c.KISILER, s["eslestir"] + ".md")):
            a["eslesen"] = s["eslestir"]
        elif s.get("eslestir") == "yeni":
            a["eslesen"] = ""
        ad = (s.get("ad") or a["ad"]).strip()
        hamlar = sorted({k["ham"] for k in a["kaynaklar"] if k.get("ham")})
        kaynak_metni = []
        temaslar = []
        nereden = ["whatsapp"] if any(k["tip"].startswith("wa") for k in a["kaynaklar"]) else []
        for k in a["kaynaklar"]:
            if k["tip"] == "rehber":
                kaynak_metni.append(f"telefon rehberi ({k['tarih']})")
                nereden.append("rehber")
            elif k["tip"] == "wa-birebir":
                kaynak_metni.append(f"WhatsApp birebir sohbet dışa aktarması ({k['tarih']})")
                temaslar.append(f"{datetime.strptime(k['son'], '%Y-%m-%d'):%d.%m.%Y} · WhatsApp · {k['mesaj'] + k.get('ben_mesaj', 0)} mesaj ({k['ilk']} – {k['son']})")
            else:
                kaynak_metni.append(f"WhatsApp grubu \"{k['sohbet']}\" ({k['tarih']})")
                nereden.append(ia.grup_etiketi(k["sohbet"]))
        wa = wa_alanlari(a)
        if hamlar:
            wa["wa_sohbetler"] = hamlar
        if a.get("eslesen") and os.path.exists(os.path.join(c.KISILER, a["eslesen"] + ".md")):
            # ağda zaten var: yalnız eksik alanları ve temas özetini ekle
            kid = a["eslesen"]
            k = c.kisi_oku(os.path.join(c.KISILER, kid + ".md"))
            govde = k.pop("govde")
            k["nereden"] = sorted(set((k.get("nereden") or []) + nereden))
            if s.get("yakinlik") not in (None, "") and k.get("yakinlik_kaynak") != "sen":
                k["yakinlik"] = str(max(int(k.get("yakinlik") or 0), int(s["yakinlik"])))
            if a["telefon"] and not k.get("telefon"):
                k["telefon"] = a["telefon"]
            for t in temaslar:
                if t not in govde:
                    govde = c.temas_ekle(govde, t)
            if a.get("oneri_son_temas") and a["oneri_son_temas"] > (k.get("son_temas") or ""):
                k["son_temas"] = a["oneri_son_temas"]
            if a.get("foto") and not k.get("foto"):
                k["foto"] = c.foto_kaydet(kid, foto_coz(a["foto"]))
            if hamlar:
                wa["wa_sohbetler"] = sorted(set((k.get("wa_sohbetler") or []) + hamlar))
            k.update(wa)
            c.kisi_yaz(kid, k, govde)
        else:
            kid = c.bos_slug(ad)
            alanlar = {
                "ad": ad, "foto": "", "tur": s.get("tur") if s.get("tur") in c.TURLER and s.get("tur") != "ben" else "cevre",
                "kurum": a.get("kurum", ""), "rol": a.get("rol", ""), "alan": [], "nereden": sorted(set(nereden)),
                "yakinlik": str(int(s.get("yakinlik", a.get("oneri_yakinlik", 1)))), "telefon": a["telefon"],
                "eposta": a.get("eposta", ""), "son_temas": a.get("oneri_son_temas", ""), "sonraki_adim": "",
            }
            alanlar.update(wa)
            if a.get("foto"):
                try:
                    alanlar["foto"] = c.foto_kaydet(kid, foto_coz(a["foto"]))
                except ValueError:
                    pass
            not_ = f" Sohbet metni: `gelen/whatsapp/{', '.join(hamlar)}`." if hamlar else " Mesaj içerikleri saklanmadı, yalnız sayı ve tarih."
            govde = c.yeni_govde(ad, "; ".join(kaynak_metni) + "." + not_, temaslar)
            c.kisi_yaz(kid, alanlar, govde)
        a["durum"] = "eklendi"
        a["kisi"] = kid
        eklenen.append(kid)
        for h in hamlar:
            sohbet_kisileri.setdefault(h, {})[a["ad"]] = kid
    ia.adaylar_yaz(havuz)
    bag = grup_baglari(havuz)
    isler = []
    if ia.ayarlar().get("otomatik_analiz", True) and mdl.hazir():
        for h, es in sohbet_kisileri.items():
            # sohbetin önceden eklenmiş üyeleri de analize girsin
            for a in havuz.values():
                if a.get("durum") == "eklendi" and any(k.get("ham") == h for k in a["kaynaklar"]):
                    es.setdefault(a["ad"], a["kisi"])
            sohbet = next((k["sohbet"] for a in havuz.values() for k in a["kaynaklar"] if k.get("ham") == h), h)
            isler.append(an.kuyruga_ekle(h, sohbet, es, c.VERI))
    return {"eklenen": eklenen, "bag": bag, "analiz": len(isler)}


def grup_baglari(havuz, azami=12):
    """Küçük WhatsApp gruplarının ağdaki üyeleri arasında 'tanisiyor' bağı kurar (zaten bağ varsa dokunmaz)."""
    gruplar = {}
    for a in havuz.values():
        if a.get("durum") != "eklendi" or not a.get("kisi") or not os.path.exists(os.path.join(c.KISILER, a["kisi"] + ".md")):
            continue
        for k in a["kaynaklar"]:
            if k["tip"] == "wa-grup" and k.get("boyut", 99) <= azami:
                gruplar.setdefault(k["sohbet"], set()).add(a["kisi"])
    iliskiler = c.iliskileri_oku()
    var = {frozenset((i["a"], i["b"])) for i in iliskiler}
    eklenen = 0
    for sohbet, uyeler in gruplar.items():
        uyeler = sorted(uyeler)
        for i, x in enumerate(uyeler):
            for y in uyeler[i + 1:]:
                if frozenset((x, y)) not in var:
                    iliskiler.append({"a": x, "b": y, "tip": "tanisiyor", "not": f"WhatsApp grubu: {sohbet}"[:80],
                                      "kaynak": "WhatsApp grubu", "tarih": date.today().isoformat()})
                    var.add(frozenset((x, y)))
                    eklenen += 1
    if eklenen:
        c.iliskileri_yaz(iliskiler)
    return eklenen


def analiz_baslat(g):
    """Kişi kartındaki 'Analiz et': kişinin kayıtlı sohbetleri için analiz kuyruğa girer."""
    k = kisi_bul(g.get("id"))
    if not kapi.Kapi().acik_mi(g.get("id")):
        raise ValueError("Bu kişi yapay zekâya gönderilmiyor (haric.md ya da kişi kartındaki kilit); analiz uzak modele gitmez.")
    hamlar = k.get("wa_sohbetler") or []
    if not hamlar:
        raise ValueError("Bu kişi için saklanmış WhatsApp sohbeti yok; önce sohbeti 'İçe aktar'dan yükle.")
    if not mdl.hazir():
        raise ValueError(mdl.hazir_degil_mesaji())
    havuz = ia.adaylar()
    isler = []
    for h in hamlar:
        es = {a["ad"]: a["kisi"] for a in havuz.values() if a.get("durum") == "eklendi" and a.get("kisi")
              and os.path.exists(os.path.join(c.KISILER, a["kisi"] + ".md")) and any(x.get("ham") == h for x in a["kaynaklar"])}
        es = es or {k["ad"]: g["id"]}
        sohbet = next((x["sohbet"] for a in havuz.values() for x in a["kaynaklar"] if x.get("ham") == h), h)
        isler.append(an.kuyruga_ekle(h, sohbet, es, c.VERI))
    return {"analiz": len(isler)}


def analiz_durumu(_=None):
    return an.durum_oku()


def wa_alanlari(a):
    """Birebir sohbet ölçümlerini kişi alanlarına çevirir (en çok mesajlı sohbet esas alınır)."""
    birebir = sorted((k for k in a["kaynaklar"] if k["tip"] == "wa-birebir"), key=lambda k: -k.get("mesaj", 0))
    if not birebir:
        return {}
    k = birebir[0]
    alan = {"wa_mesaj": k.get("mesaj", 0) + k.get("ben_mesaj", 0), "wa_oturum": k.get("oturum"), "wa_baslatma": k.get("baslatma_o"),
            "wa_cevap_dk": k.get("cevap_o_dk"), "wa_cevap_ben_dk": k.get("cevap_ben_dk"), "wa_son90": k.get("son90"),
            "wa_onceki90": k.get("onceki90"), "wa_ilk": k.get("ilk"), "wa_son": k.get("son")}
    return {x: str(v) for x, v in alan.items() if v is not None}


def aday_gizle(g):
    havuz = ia.adaylar()
    for aid in g.get("ids", []):
        if aid in havuz:
            havuz[aid]["durum"] = "gizli"
    ia.adaylar_yaz(havuz)
    return {}


def adaylari_temizle(_):
    """Bekleyen (eklenmemiş) adayları siler; telefon/ad listesi vault dışında bile tutulmasın isteyene."""
    havuz = {k: v for k, v in ia.adaylar().items() if v.get("durum") == "eklendi"}
    for v in havuz.values():
        v.pop("foto", None)
    ia.adaylar_yaz(havuz)
    return {}


def cikarim(g):
    """Asistan çıkarımına kullanıcı kararı: onay | duzelt | ret (soruda cevap = duzelt)."""
    r = c.cikarim_yanitla(g.get("no"), g.get("karar"), g.get("yanit", ""))
    tu.kuyrugu_temizle(r["kisi"])
    return {"kisi": r["kisi"], "durum": r["durum"]}


def belge_ekle(g):
    """Kişiye belge (dosya ya da yapıştırılan metin) ekler; asistan varsa özetletir (sonuç onay kuyruğuna girer)."""
    kid = g.get("id")
    kisi_bul(kid)
    if g.get("metin"):
        ad, ham = f"not-{datetime.now():%Y%m%d-%H%M%S}.txt", str(g["metin"]).encode("utf-8")
    else:
        ad = os.path.basename(g.get("ad") or "belge")
        ham = base64.b64decode((g.get("veri") or "").split(",", 1)[-1])
    uz = os.path.splitext(ad)[1].lower()
    if uz not in an.METIN_UZANTI | an.OKUNAN_UZANTI:
        raise ValueError("desteklenen: PDF, PNG/JPG ekran görüntüsü, .txt, .md, .html, .docx")
    if not ham or len(ham) > 25_000_000:
        raise ValueError("dosya boş ya da 25 MB'tan büyük")
    if uz in an.OKUNAN_UZANTI and g.get("ozetle", True) and mdl.hazir() and not mdl.SAGLAYICILAR[mdl.secili()]["belge"]:
        raise ValueError(f"{mdl.SAGLAYICILAR[mdl.secili()]['ad']} PDF/görsel belge okuyamaz; sağlayıcıyı Claude Code yap ya da belgeyi metin olarak ekle.")
    klasor = os.path.join(c.BELGELER, kid)
    os.makedirs(klasor, exist_ok=True)
    temel = re.sub(r"[^\w.-]+", "-", os.path.splitext(ad)[0], flags=re.U)[:60] or "belge"
    dosya = f"{date.today():%Y%m%d}-{temel}{uz}"
    i = 2
    while os.path.exists(os.path.join(klasor, dosya)):
        dosya = f"{date.today():%Y%m%d}-{temel}-{i}{uz}"; i += 1
    with open(os.path.join(klasor, dosya), "wb") as f:
        f.write(ham)
    kapali = not kapi.Kapi().acik_mi(kid)   # kişi yapay zekâya gönderilmiyorsa belge yalnız saklanır, özetlenmez
    analiz = bool(mdl.hazir()) and g.get("ozetle", True) and not kapali
    if analiz:
        an.belge_kuyruga_ekle(kid, dosya)
    return {"dosya": dosya, "analiz": analiz, "uzak_kapali": kapali}


def ozgecmis(g):
    c.ozgecmis_ekle(g.get("id"), g.get("donem", ""), g.get("baslik", ""), g.get("ayrinti", ""))
    return {}


def bolum_sil(g):
    if g.get("bolum") not in (c.OZGECMIS_BASLIK, c.HAKKINDA_BASLIK):
        raise ValueError("bölüm silinemez")
    c.bolum_satir_sil(g.get("id"), g["bolum"], g.get("sira", -1))
    return {}


def sor(g):
    if any(not isinstance(g.get(k) or "", str) for k in ("soru", "kisi", "oturum")):
        raise ValueError("soru, kisi ve oturum metin olmalı")
    soru = " ".join(str(g.get("soru") or "").split())[:4000]
    if not soru:
        raise ValueError("soru boş")
    onerilen = ders_onerisi(soru)   # kod bulunsa bile yazılmaz: kullanıcı sohbetteki düğmeyle onaylar; asıl soru yine cevaplanır
    soz_yerel = soz_onerisi(soru)   # yerel ayrıştırma; yazılmaz, kullanıcı sohbetteki düğmeyle onaylar
    try:
        r = an.sohbet(soru, g.get("kisi") or "", g.get("oturum") or "")
    except RuntimeError as e:
        raise ValueError(str(e))
    if onerilen:
        r["ders_onay"] = {"kodlar": onerilen, "soru": ders_onay_sorusu(onerilen)}
    liste = r.pop("kayitlar", [])
    model_soz = [o for o in liste if o.get("islem") == "soz"]   # modelin söz çıkarımı da yazılmaz, yalnız onay önerisi olur
    liste = [o for o in liste if o.get("islem") != "soz"]
    soz_onay = soz_onerileri_birlestir(soz_yerel, model_soz)
    if soz_onay:
        r["soz_onay"] = soz_onay
    r["kaydedilen"], r["atlanan"] = [], []
    if liste:
        with kilit:
            r["kaydedilen"], r["atlanan"] = kayitlari_uygula(liste)
            if r["kaydedilen"]:
                r["kapanan"] = len(tu.kuyrugu_temizle()["kapanan"])  # yeni beyanla cevaplanan sorular kapansın
                statik_yenile()
    return r


KAYIT_ALANLARI = {"kurum", "rol", "eposta", "telefon", "linkedin", "x"}


def _ad_bul(ad):
    """Tam ad (Türkçe karaktersiz) eşleşmesi; tek ad ya da birden çok aday belirsiz sayılır."""
    hedef = c.sade(ad)
    adaylar = [k["id"] for k in c.kisileri_oku() if c.sade(k.get("ad") or "") == hedef]
    return adaylar[0] if len(adaylar) == 1 else None


def kayitlari_uygula(liste):
    """Kullanıcının sohbette söylediği bilgileri (asistanın ayrıştırdığı <kayitlar>) kişi dosyalarına yazar.
    Bunlar kullanıcı beyanıdır; yazmadan önce her dosyanın sürümü arsiv/surum/'e alınır. Dönen: (kaydedilen, atlanan) özet satırları."""
    kaydedilen, atlanan, yeniler, yedekli = [], [], {}, set()
    bugun = date.today()
    for o in liste:
        if isinstance(o.get("yeni"), str):
            o["yeni"] = {"ad": o["yeni"]}
        try:
            islem = o.get("islem")
            kid = o.get("kisi")
            if not kid and isinstance(o.get("yeni"), dict):
                y = o["yeni"]
                ad = " ".join(str(y.get("ad") or "").split())[:80]
                if not ad:
                    raise ValueError("yeni kişinin adı yok")
                kid = yeniler.get(c.sade(ad)) or _ad_bul(ad)  # soyadsız akraba/tanıdık da açılabilir (ör. "Ayşe")
                if not kid and c.haric_mi({"ad": ad, "kurum": str(y.get("kurum") or ""), "rol": str(y.get("rol") or "")}):
                    raise ValueError(f"{ad} hariç listesindeki bir kurumla eşleşiyor; eklenmedi")
                if not kid:
                    tur = y.get("tur") if y.get("tur") in c.TURLER and y.get("tur") != "ben" else "cevre"
                    kid = kisi_kaydet({"ad": ad, "tur": tur, "kurum": str(y.get("kurum") or "")[:120], "rol": str(y.get("rol") or "")[:120],
                                       "kaynak": f"{ilk_ad()}, Kut sohbetinde söyledi ({bugun.isoformat()})."})["id"]
                    kaydedilen.append(f"Yeni kişi: {ad}")
                yeniler[c.sade(ad)] = kid
                yedekli.add(kid)
            if kid == c.ben_id() and islem == "iliski":  # "Ada'nın teyzesi benim de..." gibi: kaynak kullanıcının kendisi
                k = c.ben()
            else:
                k = kisi_bul(kid)
            ad = k.get("ad") or kid
            if c.haric_mi(k):
                raise ValueError(f"{ad} hariç listesinde")
            if islem == "ekle":  # yalnız kişiyi aç
                continue
            if kid not in yedekli and kid != c.ben_id():
                c.surum_al(kid)
                yedekli.add(kid)
            metin = " ".join(str(o.get("metin") or "").split())[:400]
            if islem == "temas":
                temas({"id": kid, "metin": metin, "kanal": str(o.get("kanal") or "")[:30], "tarih": o.get("tarih") or bugun.isoformat()})
                kaydedilen.append(f"{ad}: temas · {metin}")
            elif islem in ("beyan", "gorus", "siklik", "sonraki", "yakinlik", "alan"):
                govde = k.pop("govde")
                if islem == "beyan":
                    if not metin:
                        raise ValueError("boş beyan")
                    govde = c.bolume_ekle(govde, c.BEYAN_BASLIK, f"{bugun:%d.%m.%Y} · {metin} ({ilk_ad()}, Kut sohbeti)")
                    ozet = f"beyan · {metin}"
                elif islem == "gorus":
                    k["kullanici_gorusu"] = metin
                    ozet = f"görüşün · {metin}"
                elif islem == "siklik":
                    if o.get("deger") not in c.SIKLIK:
                        raise ValueError("bilinmeyen sıklık")
                    k["temas_sikligi"] = o["deger"]
                    ozet = f"görüşme sıklığı · {c.SIKLIK[o['deger']][1]}"
                elif islem == "sonraki":
                    tarih = str(o.get("tarih") or "")
                    if tarih:
                        date.fromisoformat(tarih)
                    k["sonraki_adim"], k["sonraki_tarih"] = metin, tarih
                    ozet = f"sonraki adım · {metin}{' (' + tarih + ')' if tarih else ''}"
                elif islem == "yakinlik":
                    d = int(o.get("deger"))
                    if d not in (0, 1, 2, 3):
                        raise ValueError("yakınlık 0–3")
                    k["yakinlik"], k["yakinlik_kaynak"] = str(d), "sen"
                    ozet = f"yakınlık · {d}"
                else:
                    alan, deger = o.get("alan"), " ".join(str(o.get("deger") or "").split())[:200]
                    if alan not in KAYIT_ALANLARI or not deger:
                        raise ValueError("bilinmeyen alan")
                    if alan == "telefon":
                        k["telefon"] = sorted(set(c.liste_yap(k.get("telefon")) + [deger]))
                    else:
                        k[alan] = deger
                    ozet = f"{alan} · {deger}"
                c.kisi_yaz(kid, k, govde)
                kaydedilen.append(f"{ad}: {ozet}")
            elif islem == "iliski":
                hedef = o.get("hedef")
                hy = o.get("hedef_yeni")
                hy = hy.get("ad") if isinstance(hy, dict) else hy
                if not hedef and isinstance(hy, str):
                    hedef = yeniler.get(c.sade(hy)) or _ad_bul(hy)
                    if not hedef:
                        raise ValueError(f"'{hy}' bulunamadı; önce yeni kişi olarak eklenmeli")
                hk = kisi_bul(hedef) if hedef != c.ben_id() else c.ben()
                if hedef != c.ben_id() and c.haric_mi(hk):
                    raise ValueError(f"{hk.get('ad')} hariç listesinde")
                iliski_ekle({"a": kid, "b": hedef, "tip": o.get("tip"), "not": metin[:80], "kaynak": ilk_ad()})
                kaydedilen.append(f"{ad} – {hk.get('ad')}: {c.TIPLER[o['tip']][0]}")
            else:
                raise ValueError(f"bilinmeyen işlem: {islem}")
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            kim = o.get("kisi") or (o["yeni"].get("ad") if isinstance(o.get("yeni"), dict) else "") or "?"
            atlanan.append(f"{kim} · {o.get('islem')}: {e}")
    if kaydedilen:
        gunluk(f"kut sohbeti kayıt: {len(kaydedilen)} işlem, {len(atlanan)} atlandı")
    return kaydedilen, atlanan


def kaynak_doldur(g):
    """Açık kaynaklardan doldur (ağ isteği kilit dışında; yazım ag_kaynak içinde kilitle), sonra bağlamdan bağları çıkar."""
    o = kn.doldur(kilit, statik_yenile, zorla=bool(g.get("zorla")))
    with kilit:
        b = bg.bag_cikar(kaydet=True)
        tu.kuyrugu_temizle()
        if b["yazilan"] or b["onerilen"]:
            statik_yenile()
    o["baglar"], o["bag_onerisi"] = b["yazilan"], b["onerilen"]
    return o


def _ders_modeli(istem):
    """Yerel ayıklama kod bulamazsa mevcut model katmanından ders kodu ister (yeni model çağrı yolu yok)."""
    return an._model(istem)


def ders_onerisi(soru):
    """Sohbet cümlesinde ders kodu varsa kodları döndürür; HİÇBİR ŞEY yazmaz. Belirsiz doğal dil cümlesi henüz kullanıcı beyanı değildir,
    kullanıcı onaylayınca (ders_onayla) beyan olur. Soru, olumsuz ve geçmiş cümlelerde boş."""
    return dg.ayikla(soru, model=_ders_modeli)


def ders_onay_sorusu(kodlar):
    ad = f"{', '.join(kodlar[:-1])} ve {kodlar[-1]}" if len(kodlar) > 1 else kodlar[0]
    return f"{ad}’i bu dönemki derslerine ekleyeyim mi?"


def ders_onayla(g):
    """Sohbetteki onay düğmesi: kodları profil derslerine ekler (artık kullanıcı beyanı), seçili okulun bağdaştırıcısıyla hocaları bulup ağa
    ekler (Doğrula'ya soru düşer). Okul seçili değilse önce okulu sorar. Gelen kodlar sunucuda yeniden doğrulanır."""
    ham = g.get("kodlar")
    if not isinstance(ham, list) or not ham or len(ham) > 20 or not all(isinstance(x, str) for x in ham):
        raise ValueError("kodlar: ders kodu listesi olmalı")
    kodlar = []
    for x in ham:
        x = " ".join(x.split()).upper()
        if not re.fullmatch(dg.KOD, x) or re.match(r"[^\W\d_]+", x).group(0) in dg.YASAK_ONEK:
            raise ValueError("geçersiz ders kodu: " + x[:20])
        if x not in kodlar:
            kodlar.append(x)
    oturum = str(g.get("oturum") or "")
    with kilit:
        mevcut = c.liste_yap(c.ben().get("dersler"))
        yeni = dg.birlestir(mevcut, kodlar)
        if yeni != mevcut:
            c.ben_yaz({"dersler": yeni})
        statik_yenile()
    cevap = {"oturum": oturum, "oneri": 0, "kaydedilen": [], "atlanan": [], "ders_kodlari": kodlar}
    ay = kn.okul_ayar()
    if not ay:
        liste = ", ".join(o["kisa"] if o.get("kisa") else o["ad"] for o in kn.OKULLAR.values())
        cevap["cevap"] = (f"{len(kodlar)} dersi profiline yazdım ({', '.join(kodlar)}). Hocalarını bulmam için hangi okulda olduğunu bilmem gerek: "
                          f"şu an desteklenenler {liste}. Ayarlar (⚙) → Kaynaklar → Okul bağdaştırıcısı'ndan seçersen hocalar kendiliğinden gelir. "
                          "Okulun listede yoksa söyle, README'deki rehberle bağdaştırıcı eklenebilir.")
        cevap["okul_sor"] = True
        return cevap
    try:
        hocalar, bulunamayan = kn.ders_hocalari(kodlar)
    except (OSError, ValueError) as e:
        cevap["cevap"] = f"{len(kodlar)} dersi profiline yazdım ama {ay['ad']} ders programına şu an ulaşamadım ({str(e)[:80]}). Sonra kendiliğinden yeniden denerim."
        return cevap
    o = kaynak_doldur({"zorla": False})
    parca = [f"{len(kodlar)} ders, {len(hocalar)} hoca buldum ({ay['ad']})"]
    if hocalar:
        parca.append(": " + ", ".join(sorted(hocalar)[:8]) + (" …" if len(hocalar) > 8 else ""))
    mesaj = "".join(parca) + "."
    if o.get("eklenen") or o.get("guncellenen"):
        mesaj += f" Ağa ekledim/güncelledim: {len(o.get('eklenen', []))} yeni, {len(o.get('guncellenen', []))} güncel kişi."
    if o.get("dogrulanacak"):
        mesaj += f" {len(o['dogrulanacak'])} akademik profil önerisi Doğrula'da onayını bekliyor."
    if bulunamayan:
        mesaj += " Programda bulamadıklarım: " + ", ".join(bulunamayan) + "."
    mesaj += " Hocalarla tanışıklığın hakkındaki sorular Doğrula'da."
    cevap["cevap"] = mesaj
    cevap["ders_ozeti"] = {"ders": len(kodlar), "hoca": len(hocalar), "bulunamayan": bulunamayan}
    return cevap


def soz_onerisi(soru):
    """Sohbet cümlesinde söz ("Ayşe'ye kitabı cuma göndereceğim") varsa yerel ayrıştırmayla öneri döndürür; HİÇBİR ŞEY yazmaz. Belirsiz doğal dil
    cümlesi henüz kullanıcı beyanı değildir, kullanıcı onaylayınca (soz_onayla) beyan olur. Soru, olumsuz, geçmiş ve koşullu cümlelerde boş."""
    return sz.oner(soru, c.kisileri_oku())


def soz_onerileri_birlestir(yerel, model):
    """Yerel ve modelin söz önerilerini doğrulayıp tekilleştirir (aynı kişi+yön yerelden kalır); zaten açık olan söz önerilmez. En çok 3."""
    kisiler = c.kisileri_oku()
    sonuc = list(yerel)
    for o in model:
        d = sz.oneri_dogrula(o, kisiler)
        if d and not any(x["kisi"] == d["kisi"] and x["yon"] == d["yon"] for x in sonuc):
            sonuc.append(d)
    acik = {}
    for o in sonuc:
        if o["kisi"] not in acik:
            try:
                acik[o["kisi"]] = {(s["yon"], c.sade(s["metin"])) for s in sz.acik_sozler(kisi_bul(o["kisi"]).get("govde", ""))}
            except ValueError:
                acik[o["kisi"]] = set()
    return [o for o in sonuc if (o["yon"], c.sade(o["metin"])) not in acik[o["kisi"]]][:sz.ONERI_AZAMI]


def _soz_yaz(kid, g):
    k = kisi_bul(kid)
    if c.haric_mi(k):
        raise ValueError(f"{k.get('ad') or kid} hariç listesinde")
    sz.kisi_ekle(kid, g.get("yon"), g.get("metin"), g.get("son") or "")
    return k.get("ad") or kid


def soz_ekle(g):
    """Kişi kartındaki Sözler formu (kullanıcı beyanı, doğrudan yazılır): {id, yon: ben|o, metin, son?}."""
    ad = _soz_yaz(g.get("id"), g)
    return {"id": g["id"], "cevap": f"{ad} için söz kaydedildi."}


def soz_onayla(g):
    """Sohbetteki onay düğmesi: önerilen sözü kişiye yazar (artık kullanıcı beyanı). Gelen öneri sunucuda yeniden doğrulanır
    (kişi ağda mı, hariç mi, yön, metin, tarih); {kisi, yon, metin, son?, oturum?}."""
    o = sz.oneri_dogrula(g, c.kisileri_oku())
    if not o:
        raise ValueError("söz önerisi geçersiz")
    ad = _soz_yaz(o["kisi"], o)
    gunluk("kut sohbeti söz onayı: 1 söz")
    return {"kisi": o["kisi"], "oturum": str(g.get("oturum") or ""),
            "cevap": f"{ad} için söz kaydedildi: {o['metin']}" + (f" (son: {o['son']})" if o["son"] else "")}


def soz_durum(g):
    """Kişi kartında 'Tamamla' / 'İptal': {id, sira, metin, durum: tamam|iptal}. Satır silinmez (kapanış tarihiyle kalır)."""
    kisi_bul(g.get("id"))
    sz.kisi_kapat(g["id"], g.get("sira"), g.get("durum"), g.get("metin"))
    return {"id": g["id"]}


def kisi_uzak(g):
    """Kişi kartındaki '🔒 Bu kişi yapay zekâya gönderilmez' anahtarı: {id, kapali: true|false} → `remote_allowed: false` (kapalıysa) ya da alanı kaldırır.
    Kapı imzası değiştiği için bellekteki sohbet geçmişi hemen silinir; istemci de Claude oturumunu sıfırlamalı (`oturum_sifirla`)."""
    k = kisi_bul(g.get("id"))
    if not isinstance(g.get("kapali"), bool):
        raise ValueError("kapali: true ya da false olmalı")
    govde = k.pop("govde")
    c.surum_al(g["id"])
    if g["kapali"]:
        k["remote_allowed"] = "false"
        if k.get("visibility") != "private":   # private'ı Kut koyacak (kisi_yaz): açarken yalnız Kut'un koyduğu kaldırılır, kullanıcının elle koyduğu kalır
            k["visibility_kut"] = "true"
    else:
        k.pop("remote_allowed", None)
        if k.pop("visibility_kut", None) and k.get("visibility") == "private":   # kapatırken Kut koymuştu; açınca ikinci beynin bağlamına geri döner
            k.pop("visibility")
    c.kisi_yaz(g["id"], k, govde)
    mdl.gecmis_temizle()
    mdl.claude_oturumlari_iptal_et()   # sunucu tarafı: istemci oturum kimliğini sıfırlamasa da eski Claude konuşması --resume edilmez
    return {"id": g["id"], "kapali": g["kapali"], "oturum_sifirla": True}


def _otomatik_doldur():
    try:   # keşif kaynakları (vekil haftalık, etkinlik 12 saatte bir) ve haftalık strateji okuması (aktif hedef varsa)
        ks.yenile(bitince=lambda: st.baslat() if st.gerekli() and mdl.hazir() and ia.ayarlar().get("otomatik_strateji", True) else None)
    except Exception:
        gunluk("keşif: " + hata_izi())
    try:
        if kn.otomatik_gerekli():
            o = kaynak_doldur({})
            gunluk("otomatik doldurma: " + json.dumps({x: len(y) for x, y in o.items()}, ensure_ascii=False))
        else:
            with kilit:
                if tu.kuyrugu_temizle()["kapanan"]:
                    statik_yenile()
    except Exception:
        gunluk(hata_izi())


def cikarim_hepsi(g):
    kisi_bul(g.get("id"))
    return {"onaylanan": c.tumunu_onayla(g["id"])}


def ses_oku(g):
    try:
        return ses.oku(str(g.get("metin") or "")[:6000], float(g.get("hiz") or 1.0))
    except RuntimeError as e:
        raise ValueError(str(e))


def ses_yaz(g):
    """Sesli girdi: tarayıcının gönderdiği 16 kHz ham sesi yerelde yazıya çevirir. Kişi adları Whisper'a ipucu olur."""
    adlar = [c.ben().get("ad") or ""] + [k.get("ad") or "" for k in c.kisileri_oku()]
    ipucu = "Kut, kişisel ağ notları. Kişiler: " + ", ".join(a for a in adlar if a) + "."
    try:
        return ses.yaz(str(g.get("pcm") or ""), ipucu)
    except RuntimeError as e:
        raise ValueError(str(e))


def ses_isit(g):
    ses.isit(g.get("tur"))
    return {}


def saglayici_ayarla(g):
    """Model sağlayıcı seçimi: {saglayici?, modeller?: {codex: "..."}}; kurulu olmayan seçilemez. Dönen: sağlayıcı durumu."""
    return mdl.ayarla(g)


def ses_kurulum_baslat(g):
    """Ses ortamı kurulumu: yalnız kullanıcının açık onayıyla ({onay: true}); parcalar boşsa eksik olanlar, yaz_model boşsa önerilen."""
    return sesk.baslat(g.get("parcalar") or ses.eksik() or None, g.get("yaz_model"), g.get("onay") is True)


def ses_kurulum_ayar(g):
    """Kurulum sorusuna cevap: {cevap: "sorma" | "sor"} (Bir daha sorma / yeniden sor)."""
    return sesk.soru_yaz(g.get("cevap"))


def ayar(g):
    a = ia.ayarlar()
    a["ben_adlari"] = [x.strip() for x in g.get("ben_adlari", []) if x.strip()]
    ia.ayar_yaz(a)
    return {}


ISLEMLER = {
    "/api/ben": ben_kaydet, "/api/kisi": kisi_kaydet, "/api/temas": temas, "/api/kisi/arsivle": kisi_arsivle,
    "/api/iliski": iliski_ekle, "/api/iliski/sil": iliski_sil,
    "/api/ice-aktar": ice_aktar, "/api/aday/ekle": aday_ekle, "/api/aday/gizle": aday_gizle,
    "/api/aday/temizle": adaylari_temizle, "/api/ayar": ayar, "/api/saglayici": saglayici_ayarla, "/api/analiz/baslat": analiz_baslat,
    "/api/cikarim": cikarim, "/api/sor": sor, "/api/cikarim/hepsi": cikarim_hepsi, "/api/belge": belge_ekle,
    "/api/ozgecmis": ozgecmis, "/api/bolum/sil": bolum_sil, "/api/kaynak/doldur": kaynak_doldur,
    "/api/ses/oku": ses_oku, "/api/ses/yaz": ses_yaz, "/api/ses/isit": ses_isit,
    "/api/ders/onayla": ders_onayla,
    "/api/soz": soz_ekle, "/api/soz/durum": soz_durum, "/api/soz/onayla": soz_onayla, "/api/kisi/uzak": kisi_uzak,
}
DEGISTIRMEYEN = {"/api/sor", "/api/analiz/baslat", "/api/ice-aktar", "/api/aday/gizle", "/api/aday/temizle", "/api/ayar", "/api/saglayici"}
KILITSIZ = {"/api/sor", "/api/ders/onayla", "/api/kaynak/doldur", "/api/ses/oku", "/api/ses/yaz", "/api/ses/isit"}  # uzun sürer; yazmazlar ya da kilidi kendileri alır


GUVENLIK_BASLIKLARI = (
    ("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob: data:; "
     "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; "
     "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
    ("X-Frame-Options", "DENY"), ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"),
)
KILIT_GOVDE_AZAMI = 4096
ISTEK_AZAMI = 220_000_000


class Isleyici(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _host_ok(self):
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def _oturum(self):
        return kl.cerez_oku(self.headers.get("Cookie"))

    def _acik(self, dokun=True):
        return kl.gecerli(self._oturum(), dokun)

    def _koken_ok(self):
        """Kilit isteklerinde (anahtarsız) başka bir siteden gelen form gönderimini reddet."""
        o = self.headers.get("Origin")
        return not o or o in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")

    def _govde(self, azami):
        """Content-Length'i denetleyip gövdeyi JSON olarak okur. Negatif/sayı olmayan → 400, azamiyi aşan → 413 (cevap burada gönderilir,
        None döner)."""
        try:
            uzunluk = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            uzunluk = -1
        if uzunluk < 0:
            self._gonder(400, {"hata": "Content-Length geçersiz"})
            return None
        if uzunluk > azami:
            self._gonder(413, {"hata": "çok büyük"})
            return None
        try:
            g = json.loads(self.rfile.read(uzunluk) or b"{}")
        except ValueError:
            self._gonder(400, {"hata": "geçersiz JSON"})
            return None
        if not isinstance(g, dict):
            self._gonder(400, {"hata": "geçersiz JSON"})
            return None
        return g

    def _kilit_islem(self, yol):
        g = self._govde(KILIT_GOVDE_AZAMI)
        if g is None:
            return
        try:
            if yol == "/api/kilit/kur":
                if kl.kurulu() and not self._acik():
                    return self._gonder(403, {"hata": "PIN zaten belirlenmiş"})
                if str(g.get("pin")) != str(g.get("pin2")):
                    return self._gonder(400, {"hata": "İki PIN aynı değil"})
                if kl.kurulu() and not kl.dogrula(g.get("eski")):   # var olan PIN'i değiştirmek şu anki PIN'i ister (sayaçlı)
                    return self._gonder(400, {"hata": "Şu anki PIN yanlış"})
                kl.pin_yaz(g.get("pin"))
                gunluk("kilit: PIN belirlendi")
                statik_yenile()   # eski ag.html anlık görüntüsü kalksın
                belirtec = kl.yeni_oturum()
            else:
                belirtec = kl.ac(g.get("pin"))
        except PermissionError as e:
            return self._gonder(429, {"hata": f"Çok fazla yanlış deneme; {e.args[0]} sn bekle", "bekle": e.args[0]})
        except ValueError as e:
            return self._gonder(400, {"hata": str(e)})
        return self._gonder(200, {"ok": True}, cerez=kl.cerez_yaz(belirtec))

    def _yonlendir(self, adres):
        self.send_response(302)
        self.send_header("Location", adres)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        for ad, deger in GUVENLIK_BASLIKLARI:
            self.send_header(ad, deger)
        self.end_headers()

    def _dil(self):
        """Sayfa dili: tarayıcının kut_dil çerezi (kilit ekranındaki seçim de buraya yazar) → ayarlar.json "dil" → Türkçe."""
        return ag_dil.cerezden(self.headers.get("Cookie")) or ag_dil.etkin()

    def _demo_sayfa(self):
        """Demo önizlemesi ("Deniz'in salısı"): yalnız kilit açıkken ve /api/demo/baslat sonrası. Sayfa gerçek oturum anahtarını DEĞİL,
        demo anahtarını taşır; gerçek uçlar onu reddeder. Veri geçici demo klasöründen gelir, kullanıcının verisine bakılmaz."""
        if not self._acik():
            return self._yonlendir("/")
        s = ag_demo.sayfa_verisi()
        if s is None:
            return self._yonlendir("/")
        veri, meta, demo_anahtar = s
        html = c.sayfa(veri, {"anahtar": demo_anahtar, "sihirbaz": {"bitti": True}, "arayuz_sesi": arayuz_sesi_acik(), "bilinen": {}, "demo": meta},
                       {"acik": True, "kurulu": True, "sure_dk": kl.sure_dk()}, dil=self._dil())
        return self._gonder(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _gonder(self, kod, govde, tip="application/json; charset=utf-8", cerez=None):
        veri = govde if isinstance(govde, bytes) else json.dumps(govde, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        if cerez:
            self.send_header("Set-Cookie", cerez)
        self.send_header("Content-Type", tip)
        self.send_header("Content-Length", str(len(veri)))
        self.send_header("Cache-Control", "no-store")
        for ad, deger in GUVENLIK_BASLIKLARI:
            self.send_header(ad, deger)
        self.end_headers()
        self.wfile.write(veri)

    def do_GET(self):
        global son_istek
        son_istek = time.time()
        if not self._host_ok():
            return self._gonder(403, {"hata": "host"})
        yol = self.path.split("?")[0]
        try:
            if yol == "/":
                if not self._acik():   # kilitli: kişisel veri yok, yalnız gök + açılış + kilit ekranı
                    html = c.sayfa(kl.bos_veri(), None, {"kurulu": kl.kurulu()}, dil=self._dil())
                    return self._gonder(200, html.encode("utf-8"), "text/html; charset=utf-8")
                with kilit:
                    html = c.sayfa(c.veri_hazirla(), {"anahtar": ANAHTAR, "sihirbaz": {"bitti": sihirbaz_bitti()}, "arayuz_sesi": arayuz_sesi_acik(), "bilinen": sihirbaz_bilinen(),
                                                      "dil_ayar": ag_dil.ayar_dili()},
                                   {"acik": True, "kurulu": True, "sure_dk": kl.sure_dk()}, dil=self._dil())
                return self._gonder(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if yol == "/api/nabiz":
                return self._gonder(200, {"ok": True})
            if yol == "/demo":
                return self._demo_sayfa()
            if not self._acik(dokun=yol not in ("/api/analiz", "/api/pusula/durum", "/api/ses/kurulum")):   # durum yoklamaları oturumu canlı tutmasın
                return self._gonder(401, {"hata": "kilitli"})
            if yol == "/api/demo/durum":   # demo sayfasının canlı tutma yoklaması (demo anahtarı)
                bek = ag_demo.anahtar()
                if not bek or self.headers.get("X-Ag-Anahtar") != bek:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, ag_demo.durum())
            if yol == "/api/demo/ses":   # ön üretimli anlatım sesi (varsa); çerez + etkin demo yeter, sahne kimliği beyaz listeden
                dosya = ag_demo.ses_dosyasi(parse_qs(urlsplit(self.path).query).get("s", [""])[0]) if ag_demo.aktif() else None
                if not dosya:
                    return self._gonder(404, {"hata": "yok"})
                with open(dosya, "rb") as f:
                    return self._gonder(200, f.read(), ag_demo.ses_tipi(dosya))
            if yol == "/api/ses":
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, {**ses.durum(), "mikrofon": (ia.ayarlar().get("ses") or {}).get("mikrofon", "")})
            if yol == "/api/ses/kurulum":   # ses ortamı kurulum durumu (ilerleme yoklaması); ?plan=1 boyutları ve Python durumunu da verir
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                q = parse_qs(urlsplit(self.path).query)
                d = sesk.ozet()
                if q.get("plan"):
                    d["plan"] = sesk.plan(q.get("parca", [""])[0].split(",") if q.get("parca") else None, q.get("model", [""])[0] or None)
                return self._gonder(200, d)
            if yol == "/api/pusula":
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, pusula())
            if yol == "/api/ajanda":   # Pusula → Takvim: tarihli her şeyin salt-okur akışı; bas/bit YYYY-AA-GG, geçersizse ValueError → 400
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                q = parse_qs(urlsplit(self.path).query)
                return self._gonder(200, aj.ajanda(q.get("bas", [""])[0], q.get("bit", [""])[0]))
            if yol == "/api/sonuclar":   # Pusula → Sonuçlar: Kut'un önerileri ve sonuçları (salt okur)
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, sonuclar_liste())
            if yol == "/api/bildirim":   # Ayarlar → "Kut sana gelsin": ayar + zamanlanmış görev gerçekten kurulu mu (salt okur)
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, bd.durum())
            if yol == "/api/guncelleme":
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, gu.durum())
            if yol == "/api/kaynaklar":
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, kaynaklar_liste(None))
            if yol == "/api/saglayici":
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, mdl.durum())
            if yol == "/api/pusula/durum":
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, {"kesif": ks.durum(), "strateji": st.durum()})
            if yol == "/api/analiz":
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, analiz_durumu())
            if yol == "/api/adaylar":
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                return self._gonder(200, adaylar_listesi())
            if yol in ("/api/vault", "/api/vault/kisi"):   # ikinci beyin köprüsü: salt okur, ayar yoksa kapalı
                if self.headers.get("X-Ag-Anahtar") != ANAHTAR:
                    return self._gonder(403, {"hata": "anahtar"})
                if yol == "/api/vault":
                    return self._gonder(200, vault.durum())
                kid = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
                return self._gonder(200, {"etkin": bool(vault.ayar()), "satirlar": vault.kisi_anilma(kid)})
            return self._gonder(404, {"hata": "yok"})
        except ValueError as e:   # geçersiz sorgu parametresi (ör. ses/kurulum?parca=zzz): sunucu hatası değil
            return self._gonder(400, {"hata": str(e)})
        except Exception as e:
            gunluk(hata_izi())
            return self._gonder(500, {"hata": str(e)})

    def do_POST(self):
        global son_istek
        son_istek = time.time()
        yol = self.path.split("?")[0]
        if yol in ("/api/kilit/ac", "/api/kilit/kur"):
            if not self._host_ok() or not self._koken_ok():
                return self._gonder(403, {"hata": "yetki"})
            return self._kilit_islem(yol)
        if yol == "/api/kilit/kapat" and self._host_ok() and self._koken_ok() and self.headers.get("X-Ag-Anahtar") != ANAHTAR:
            # pencere kapanırken sendBeacon özel başlık gönderemez; anahtar gövdede gelir
            g = self._govde(KILIT_GOVDE_AZAMI)
            if g is None:
                return
            if g.get("anahtar") == ANAHTAR:
                kl.kapat(self._oturum())
                ag_demo.kapat()   # oturum bitti: geçici demo verisi de silinir
                return self._gonder(200, {"ok": True}, cerez=kl.cerez_yaz("") + "; Max-Age=0")
            return self._gonder(403, {"hata": "yetki"})
        beklenen = ag_demo.anahtar() if yol in DEMO_ANAHTARLI else ANAHTAR   # demo uçları yalnız demo anahtarıyla, gerçek uçlar yalnız gerçek anahtarla
        if not self._host_ok() or not beklenen or self.headers.get("X-Ag-Anahtar") != beklenen:
            return self._gonder(403, {"hata": "yetki"})
        if yol == "/api/kilit/kapat":
            kl.kapat(self._oturum())
            ag_demo.kapat()
            return self._gonder(200, {"ok": True}, cerez=kl.cerez_yaz("") + "; Max-Age=0")
        if yol.startswith("/api/ses/kurulum/") and not self._koken_ok():   # indirme başlatan uçlar yalnız yerel sayfadan
            return self._gonder(403, {"hata": "yetki"})
        if not self._acik():
            return self._gonder(401, {"hata": "kilitli"})
        if yol in KOKEN_DENETIMLI and not self._koken_ok():
            return self._gonder(403, {"hata": "yetki"})
        if yol not in ISLEMLER:
            return self._gonder(404, {"hata": "yok"})
        yukleme = yol in YUKLEME_ONIZLE
        if yukleme and not _yukleme_isi.acquire(blocking=False):   # aynı anda en çok 1 yükleme işi (bellek + CPU)
            return self._gonder(429, {"hata": "Başka bir içe aktarma işleniyor; o bitince yeniden dene."})
        try:
            g = self._govde(YUKLEME_AZAMI.get(yol, ISTEK_AZAMI))
            if g is None:
                return
            if yol in KILITSIZ:
                sonuc = ISLEMLER[yol](g)
            else:
                with kilit:
                    sonuc = ISLEMLER[yol](g)
                    if yol not in DEGISTIRMEYEN:
                        statik_yenile()
            if not yol.startswith("/api/demo/"):   # demo gerçek ayar klasörüne (günlük dahil) hiçbir şey yazmaz
                gunluk(f"{yol} ok")
            return self._gonder(200, {"ok": True, **sonuc})
        except ValueError as e:
            return self._gonder(400, {"hata": str(e)})
        except Exception as e:
            if not yol.startswith("/api/demo/"):
                gunluk(hata_izi())
            return self._gonder(500, {"hata": str(e)})
        finally:
            if yukleme:
                _yukleme_isi.release()


def calisiyor_mu():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False


def bekci(sunucu):
    while True:
        time.sleep(60)
        if time.time() - son_istek > BOSTA_DUR and not (an._isci and an._isci.is_alive()) and not st.durum()["calisiyor"] and not sesk.calisiyor():
            gunluk("boşta, duruyor")
            sunucu.shutdown()
            return


PROFIL = os.path.join(ia.DEPO, "tarayici")


def profil_surecleri():
    """Kut'un ayrı tarayıcı profilini kullanan Edge/Chrome süreçleri (kullanıcının kendi tarayıcısına dokunulmaz)."""
    if os.name != "nt":
        return []
    komut = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | "
             "Where-Object { $_.CommandLine -like ('*--user-data-dir=' + $env:KUT_PROFIL + '*') } | ForEach-Object { $_.ProcessId }")
    p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", komut], capture_output=True, text=True,
                       env={**os.environ, "KUT_PROFIL": PROFIL}, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return [int(x) for x in p.stdout.split() if x.isdigit()]


def mikrofon_izni_yaz():
    """Kullanıcı Kut'ta mikrofona izin verdiyse, Kut profilinde bu adres için izni kalıcı 'izinli' yapar.
    Yalnız profil kapalıyken yazılır (açıkken tarayıcı çıkışta dosyanın üstüne yazar)."""
    yol = os.path.join(PROFIL, "Default", "Preferences")
    if not os.path.isfile(yol) or profil_surecleri():
        return False
    with open(yol, encoding="utf-8") as f:
        p = json.load(f)
    zaman = str(int((time.time() + 11644473600) * 1_000_000))   # Chromium zamanı: 1601'den beri mikrosaniye
    ist = p.setdefault("profile", {}).setdefault("content_settings", {}).setdefault("exceptions", {}).setdefault("media_stream_mic", {})
    for kok in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
        ist[f"{kok},*"] = {"last_modified": zaman, "setting": 1}
    p["profile"]["exit_type"], p["profile"]["exited_cleanly"] = "Normal", True   # zorla kapatıldıysa "düzgün kapanmadı" çubuğu çıkmasın
    gecici = yol + ".kut"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False)
    os.replace(gecici, yol)
    return True


def mikrofon(g):
    """Kut'un sorduğu izne kullanıcının cevabı. 'onar': tarayıcı daha önce engellediyse Kut penceresini kapatıp izni yazar, yeniden açar."""
    a = ia.ayarlar()
    ses_ayar = a.setdefault("ses", {})
    ses_ayar["mikrofon"] = "izinli" if g.get("izin") else "sonra"
    ia.ayar_yaz(a)
    if g.get("izin") and g.get("onar"):
        def yeniden():
            time.sleep(0.8)   # cevap tarayıcıya ulaşsın
            for pid in profil_surecleri():
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for _ in range(20):
                if not profil_surecleri():
                    break
                time.sleep(0.25)
            mikrofon_izni_yaz()
            tarayici_ac(f"http://127.0.0.1:{PORT}/")
        threading.Thread(target=yeniden, daemon=True).start()
    return {"yeniden": bool(g.get("izin") and g.get("onar"))}


def kilit_degistir(g):
    """Profilim → Kilit: PIN değiştirme (eski PIN gerekir) ve otomatik kilit süresi (0 = yalnız elle / yeniden başlayınca)."""
    try:
        if not kl.dogrula(g.get("eski")):
            raise ValueError("Şu anki PIN yanlış")
    except PermissionError as e:
        raise ValueError(f"Çok fazla yanlış deneme; {e.args[0]} sn bekle")
    sure = int(g.get("sure_dk", kl.sure_dk()))
    if sure not in (0, 5, 15, 30, 60):
        raise ValueError("bilinmeyen süre")
    if g.get("yeni"):
        if str(g["yeni"]) != str(g.get("yeni2")):
            raise ValueError("İki yeni PIN aynı değil")
        kl.pin_yaz(g["yeni"], sure)
    else:
        kl.sure_yaz(sure)   # ag_kilit'in doğrulama kilidi altında: kalıcı hata sayacını ezmez
    gunluk("kilit: ayar değişti")
    return {"sure_dk": sure}


def pusula(_=None):
    """Hedefler + keşif (vekil, etkinlik) + son strateji okuması; sayfadaki Pusula penceresi için."""
    hedefler = hd.hepsi()
    etkin = [h for h in hedefler if h.get("durum") in ("aktif", "taslak")]
    hedefler = [{k: v for k, v in h.items() if k != "govde"} for h in hedefler]
    try:
        vekil = ks.vekil_adaylari(etkin, bekle=False)
    except Exception as e:
        gunluk("keşif vekil: " + hata_izi())
        vekil = {"veri_yok": True, "hedefler": [], "hata": str(e)[:200]}
    return {"hedefler": hedefler, "durumlar": hd.DURUMLAR, "turler": hd.TURLER, "vekil": vekil,
            "etkinlik": ks.etkinlik_onerileri(etkin), "kesif_durum": ks.durum(), "vekilpedia_acik": ks.vekilpedia_acik(),
            "kaynaklar": ks.kaynaklar_durum(),
            "strateji": st.son(), "strateji_durum": st.durum(), "strateji_model": st.model_adi(),
            "sonuclar": st.SONUCLAR, "kararlar": ks.kararlar()}


def hedef_kaydet(g):
    return {"id": hd.kaydet(g, kaynak=f"{ilk_ad()}, Kut arayüzü ({date.today().isoformat()})")}


def hedef_ilerleme(g):
    hd.ilerleme_ekle(g.get("id"), g.get("metin"))
    return {}


def hedef_arsivle(g):
    hd.arsivle(g.get("id"))
    return {}


def kesif_yenile(g):
    return {"basladi": ks.yenile(bool(g.get("zorla")))}


def kesif_vekilpedia(g):
    ks.vekilpedia_ayarla(bool(g.get("acik")))
    if g.get("acik"):
        ks.yenile()
    return {"acik": ks.vekilpedia_acik()}


def kaynaklar_ayarla(g):
    """Kaynaklar paneli: {id, acik} kaynağı açar/kapatır; {id: "okul", okul: anahtar|""} profildeki okulu seçer (ben.md, /api/ben yolu)."""
    if g.get("id") == "okul":
        okul = c.sade(g.get("okul") or "")
        if okul and okul not in kn.OKULLAR:
            raise ValueError("bilinmeyen okul")
        ben_kaydet({"okul": okul})
        return kaynaklar_liste(None)
    ks.kaynak_ayarla(g.get("id"), bool(g.get("acik")))
    if g.get("acik"):
        if g.get("id") == "akademik":   # okul doldurmasının parçası: okul ve ders varsa şimdi çalıştır
            threading.Thread(target=lambda: kaynak_doldur({"zorla": True}), daemon=True).start()
        else:
            ks.yenile()
    return kaynaklar_liste(None)


def kaynaklar_yenile(g):
    if g.get("id") not in ks.KAYNAK_AYARLARI:
        raise ValueError("bilinmeyen kaynak")
    if not ks.KAYNAK_AYARLARI[g["id"]]["acik"]():
        raise ValueError("Önce kaynağı aç.")
    if g["id"] == "akademik":
        threading.Thread(target=lambda: kaynak_doldur({"zorla": True}), daemon=True).start()
        return {"basladi": True}
    return {"basladi": ks.yenile(True)}


def kaynaklar_liste(_):
    return ks.kaynaklar_durum()


def kasa_kisi_onizle(_):
    """Kasadaki `kind: person` notlarını yazmadan listeler (yeni / güncelleme / güncel). Kasaya yazılmaz."""
    return kk.onizle()


def kasa_kisi_al(g):
    """Önizlemede seçilen kasa notlarını Kut kişilerine yazar (kasaya yazılmaz); yollar yeniden taranan listeyle doğrulanır.
    Başarıyla alındıysa sihirbaz bu adımı bir daha sormasın diye ayarlar.json → kasa_alindi işaretlenir."""
    sonuc = kk.al(g.get("yollar"))
    if g.get("yollar"):
        a = ia.ayarlar()
        if not a.get("kasa_alindi"):
            a["kasa_alindi"] = True
            ia.ayar_yaz(a)
    return sonuc


def kesif_karar(g):
    ks.karar_yaz(g.get("anahtar"), g.get("karar"), g.get("not", ""))
    return {}


def strateji_baslat(_):
    if not mdl.hazir():
        raise ValueError(mdl.hazir_degil_mesaji())
    if not hd.hepsi(("aktif", "taslak", "beklemede")):
        raise ValueError("Önce en az bir hedef ekle.")
    return {"basladi": st.baslat()}


def strateji_sonuc(g):
    return {"hamle": st.sonuc_yaz(g.get("dosya"), g.get("no"), g.get("sonuc", ""), g.get("not", ""))}


ISLEMLER.update({"/api/hedef": hedef_kaydet, "/api/hedef/ilerleme": hedef_ilerleme, "/api/hedef/arsivle": hedef_arsivle,
                 "/api/kesif/yenile": kesif_yenile, "/api/kesif/vekilpedia": kesif_vekilpedia, "/api/kesif/karar": kesif_karar,
                 "/api/kaynaklar": kaynaklar_ayarla, "/api/kaynaklar/yenile": kaynaklar_yenile,
                 "/api/strateji/baslat": strateji_baslat, "/api/strateji/sonuc": strateji_sonuc})
DEGISTIRMEYEN.update({"/api/hedef", "/api/hedef/ilerleme", "/api/hedef/arsivle", "/api/kesif/yenile", "/api/kesif/vekilpedia", "/api/kesif/karar",
                      "/api/kaynaklar/yenile", "/api/strateji/baslat", "/api/strateji/sonuc"})   # ağ sayfası değişmez; Pusula ve Ayarlar kendi verisini çeker
ISLEMLER.update({"/api/vault/kisiler/onizle": kasa_kisi_onizle, "/api/vault/kisiler/al": kasa_kisi_al})
DEGISTIRMEYEN.add("/api/vault/kisiler/onizle")
KOKEN_DENETIMLI = {"/api/vault/kisiler/onizle", "/api/vault/kisiler/al", "/api/ders/onayla", "/api/saglayici", "/api/ses/kurulum/ayar",
                   "/api/soz", "/api/soz/durum", "/api/soz/onayla", "/api/kisi/uzak", "/api/sihirbaz"}   # anahtara ek olarak Origin de bu sunucudan gelmeli
ISLEMLER["/api/kilit/degistir"] = kilit_degistir
DEGISTIRMEYEN.add("/api/kilit/degistir")
ISLEMLER["/api/ses/mikrofon"] = mikrofon
DEGISTIRMEYEN.add("/api/ses/mikrofon")
ISLEMLER.update({"/api/ses/kurulum/baslat": ses_kurulum_baslat, "/api/ses/kurulum/iptal": lambda g: sesk.iptal(),
                 "/api/ses/kurulum/kaldir": lambda g: ses.kaldir(), "/api/ses/kurulum/ayar": ses_kurulum_ayar})
DEGISTIRMEYEN.update({"/api/ses/kurulum/baslat", "/api/ses/kurulum/iptal", "/api/ses/kurulum/kaldir", "/api/ses/kurulum/ayar"})
KILITSIZ.update({"/api/ses/kurulum/baslat", "/api/ses/kurulum/iptal", "/api/ses/kurulum/kaldir"})   # süreç/disk işi; veri kilidini tutmasınlar


def guncelleme_ayar(g):
    """Güncelleme izni (ilk açılışta sorulur ya da Ayarlar → Kaynaklar): {otomatik: bool}. Evet ise ilk denetim arka planda başlar."""
    if not isinstance(g.get("otomatik"), bool):
        raise ValueError("otomatik: true/false olmalı")
    gu.otomatik_ayarla(g["otomatik"])
    if g["otomatik"]:
        threading.Thread(target=gu.otomatik_denetim, daemon=True).start()
    return gu.durum()


ISLEMLER.update({"/api/guncelleme/ayar": guncelleme_ayar, "/api/guncelleme/denetle": lambda g: gu.denetle(elle=True),
                 "/api/guncelleme/uygula": lambda g: gu.uygula(), "/api/guncelleme/geri": lambda g: gu.geri()})
DEGISTIRMEYEN.update({"/api/guncelleme/ayar", "/api/guncelleme/denetle", "/api/guncelleme/uygula", "/api/guncelleme/geri"})
KILITSIZ.update({"/api/guncelleme/denetle", "/api/guncelleme/uygula", "/api/guncelleme/geri"})   # ağ/süreç işi; veri kilidini tutmasınlar


# ---------- veri entegrasyonları: takvim (.ics), LinkedIn CSV, ders listesi yapıştırma (yerel; ağ yok) ----------
# Önizleme uçları hiçbir şey yazmaz (sonuç bellekte, belirteçle); uygula uçları yalnız onayla yazar. Hepsi POST + anahtar + Origin ister.
def _yuklenen(d, azami):
    ham = base64.b64decode(str((d or {}).get("veri") or "").split(",", 1)[-1])
    if len(ham) > azami:
        raise ValueError("dosya çok büyük")
    return os.path.basename(str((d or {}).get("ad") or "dosya")), ham


def takvim_onizle(g):
    ad, ham = _yuklenen(g, tk.DOSYA_AZAMI)
    ben = g.get("ben") if isinstance(g.get("ben"), list) else str(g.get("ben") or "").split(",")
    secenek = {"ben": [str(x).strip() for x in ben if str(x).strip()][:20], "buyuk_dahil": g.get("buyuk_dahil") is True}
    if isinstance(g.get("baslik"), bool):
        secenek["baslik"] = g["baslik"]
    if isinstance(g.get("buyuk_esik"), (int, float)) and not isinstance(g.get("buyuk_esik"), bool):
        secenek["buyuk_esik"] = int(g["buyuk_esik"])
    return tk.onizle(ad, ham, secenek)


def linkedin_onizle(g):
    dosyalar = g.get("dosyalar")
    if not isinstance(dosyalar, list) or not 1 <= len(dosyalar) <= 3:
        raise ValueError("dosyalar: 1-3 dosya olmalı")
    return li.onizle([_yuklenen(d, li.DOSYA_AZAMI) for d in dosyalar])


def ders_yapistir_onizle(g):
    return dy.onizle(str(g.get("metin") or "")[:dy.METIN_AZAMI])


def _secimler(g):
    s = g.get("secimler")
    return s if isinstance(s, dict) else {}


ISLEMLER.update({"/api/takvim/onizle": takvim_onizle, "/api/takvim/uygula": lambda g: tk.uygula(g.get("token"), _secimler(g)),
                 "/api/linkedin/onizle": linkedin_onizle, "/api/linkedin/uygula": lambda g: li.uygula(g.get("token"), _secimler(g)),
                 "/api/ders-yapistir/onizle": ders_yapistir_onizle, "/api/ders-yapistir/uygula": lambda g: dy.uygula(g.get("token"), _secimler(g))})
DEGISTIRMEYEN.update({"/api/takvim/onizle", "/api/linkedin/onizle", "/api/ders-yapistir/onizle"})
# Önizlemeler hiçbir şey yazmaz (sonuç `ag_ice_ortak` içinde kendi kilitli sözlüğünde durur) ve uzun sürebilir (büyük .ics): genel veri kilidini
# tutmasınlar, yoksa bütün arayüz kilitlenir. Kişi dosyalarını okuyan kısa bölüm `ort.okuma_kilidi()` ile bu `kilit` altında çalışır (yarım yazılmış
# dosya okumasın); ağır ayrıştırma kilitsizdir. Aynı anda en çok bir yükleme işi çalışır (_yukleme_isi), meşgulse 429.
YUKLEME_ONIZLE = {"/api/takvim/onizle", "/api/linkedin/onizle", "/api/ders-yapistir/onizle"}
KILITSIZ.update(YUKLEME_ONIZLE)
_yukleme_isi = threading.BoundedSemaphore(1)
ort.okuma_kilidi_ayarla(kilit)
KOKEN_DENETIMLI.update({"/api/takvim/onizle", "/api/takvim/uygula", "/api/linkedin/onizle", "/api/linkedin/uygula",
                        "/api/ders-yapistir/onizle", "/api/ders-yapistir/uygula"})
YUKLEME_AZAMI = {"/api/takvim/onizle": 85_000_000, "/api/linkedin/onizle": 125_000_000, "/api/ders-yapistir/onizle": 400_000,
                 "/api/takvim/uygula": 6_000_000, "/api/linkedin/uygula": 6_000_000, "/api/ders-yapistir/uygula": 1_000_000}   # base64 gövde sınırı


def sihirbaz_bitti():
    """İlk açılış sihirbazı (kurulum + özellik turu) tamamlandı mı? Kalıcı durum ayarlar.json → "sihirbaz"."""
    return bool((ia.ayarlar().get("sihirbaz") or {}).get("bitti"))


def sihirbaz_ayar(g):
    """İlk açılış sihirbazının durumu: {durum: "bitti"} (tamamlandı ya da kapatıldı: bir daha kendiliğinden açılmaz) | "sifirla" (yeniden açılsın).
    Menüdeki "Kurulum ve tanıtım" bu durumdan bağımsız elle açılır."""
    d = g.get("durum")
    if d not in ("bitti", "sifirla"):
        raise ValueError("durum: bitti ya da sifirla olmalı")
    a = ia.ayarlar()
    a["sihirbaz"] = {"bitti": True, "tarih": datetime.now().strftime("%Y-%m-%d %H:%M")} if d == "bitti" else {"bitti": False}
    ia.ayar_yaz(a)
    return {"bitti": d == "bitti"}


ISLEMLER["/api/sihirbaz"] = sihirbaz_ayar
DEGISTIRMEYEN.add("/api/sihirbaz")


def sihirbaz_bilinen():
    """Sihirbazın yeniden sormaması gereken, sunucuda bilinen şeyler (ad/fotoğraf/okul ben.md'den, ses arayüzden gelir):
    yz = sağlayıcı açıkça seçilmiş; kasa = kasadan kişiler bir kez alınmış."""
    a = ia.ayarlar()
    return {"yz": a.get("saglayici") in mdl.SAGLAYICILAR, "kasa": bool(a.get("kasa_alindi"))}


def arayuz_sesi_acik():
    """Arayüz sesleri (tık, geçiş, pencere) açık mı? Varsayılan AÇIK. YALNIZ bu sesleri etkiler: açılıştaki Kut sesi bu ayara bakmaz."""
    return (ia.ayarlar().get("arayuz") or {}).get("ses", True) is not False


def arayuz_sesi_ayar(g):
    """{acik: true|false} → ayarlar.json → arayuz.ses. Mantıksal olmayan değer reddedilir."""
    acik = g.get("acik")
    if not isinstance(acik, bool):
        raise ValueError("acik: true ya da false olmalı")
    a = ia.ayarlar()
    a["arayuz"] = {**(a.get("arayuz") or {}), "ses": acik}
    ia.ayar_yaz(a)
    return {"acik": acik}


ISLEMLER["/api/arayuz/ses"] = arayuz_sesi_ayar


def dil_ayar(g):
    """{dil: "tr" | "en"} → ayarlar.json → dil (arayüz, MCP çıktısı ve model cevap dili). Veri dosyaları her iki dilde de aynıdır."""
    return {"dil": ag_dil.dil_ayarla(g.get("dil"))}


ISLEMLER["/api/dil"] = dil_ayar
DEGISTIRMEYEN.add("/api/dil")
KOKEN_DENETIMLI.add("/api/dil")
DEGISTIRMEYEN.add("/api/arayuz/ses")
KOKEN_DENETIMLI.add("/api/arayuz/ses")   # sihirbaz ucu gibi: anahtara ek olarak Origin de bu sunucudan gelmeli


# ---------- tanıştırma yolu, brifing, sonuç döngüsü, haftalık özet, bildirim (ag_yol, ag_brifing, ag_sonuc, ag_ozet, ag_bildirim) ----------
# Yerel ve deterministik: model ve ağ yok. Kişi verisi her istekte c.veri_hazirla(foto_gom=False); hariç kişi hiçbir çıktıda yoktur.
# İstemci girdisi sıkı doğrulanır (bilinmeyen alan, tür, uzunluk, kişi kimliği); hesaplama işlevleri saftır, demo da aynılarını çağırır.
YOL_AMAC_AZAMI, YOL_ARAMA_AZAMI, SONUC_METIN_AZAMI, SONUC_KANAL_AZAMI = 120, 80, 200, 30
SONUC_LISTE_AZAMI = 60
_dene_kilit = threading.Lock()
_bildirim_kilit = threading.Lock()   # zamanlayıcı/PowerShell alt süreçleri (≤20 sn) veri kilidini tutmasın; kendi küçük kilidi ayar yazımlarını sıraya koyar


def _izinli_alanlar(g, izinli):
    for a in g:
        if a not in izinli:
            raise ValueError("Bilinmeyen alan: " + str(a)[:30])


def _satir(g, alan, ad, azami, zorunlu=False):
    """İstemci metni: dize olmalı, tek satıra indirgenir, en çok `azami` karakter. Boşsa '' (zorunluysa hata)."""
    v = g.get(alan)
    if v is None or v == "":
        if zorunlu:
            raise ValueError(f"{ad} boş olamaz.")
        return ""
    if not isinstance(v, str):
        raise ValueError(f"{ad} metin olmalı.")
    v = " ".join(v.split())
    if len(v) > azami:
        raise ValueError(f"{ad} en çok {azami} karakter olabilir.")
    if zorunlu and not v:
        raise ValueError(f"{ad} boş olamaz.")
    return v


def _mantiksal(g, alan, varsayilan=False):
    v = g.get(alan, varsayilan)
    if not isinstance(v, bool):
        raise ValueError(f"{alan}: true ya da false olmalı.")
    return v


def _kisi_id(g, alan="id"):
    kid = g.get(alan)
    if not isinstance(kid, str) or not c.gecerli_id(kid):
        raise ValueError("geçersiz kişi")
    return kid


def yol_hesapla(g, veri):
    """{id? | ara?, amac?} → tanıştırma yolu (`mod: "yol"`) ya da arama sonucu (`mod: "ara"`). Saf: veri sözlüğünden hesaplar."""
    _izinli_alanlar(g, {"id", "ara", "amac"})
    amac = _satir(g, "amac", "Amaç", YOL_AMAC_AZAMI)
    if g.get("id") and g.get("ara"):
        raise ValueError("Ya kişi ya da arama ver, ikisini birden değil.")
    if g.get("id"):
        return {"mod": "yol", **yl.yollar(veri, _kisi_id(g), 3, amac)}
    ara = _satir(g, "ara", "Arama", YOL_ARAMA_AZAMI, zorunlu=True)
    return {"mod": "ara", **yl.ara(veri, ara, amac)}


def brifing_hesapla(g, veri, sonuclar, hedefler, strateji):
    """{id} → görüşme brifingi + Markdown. Saf: parametreleri hiçbir yerden kendisi okumaz (gerçek ve demo girdisi çağırandan gelir)."""
    _izinli_alanlar(g, {"id"})
    b = br.brifing(veri, _kisi_id(g), sonuclar=sonuclar, hedefler=hedefler, strateji=strateji)
    return {"brifing": b, "markdown": br.markdown(b)}


def _veri_oku():
    return c.veri_hazirla(foto_gom=False)


def yol_uc(g):
    return yol_hesapla(g, _veri_oku())


def brifing_uc(g):
    return brifing_hesapla(g, _veri_oku(), sn.oku(), hd.hepsi(("aktif", "taslak")), st.son() or {})


def _strateji_sonuclari():
    """Son okumalardaki sonucu işaretlenmiş strateji hamleleri (istatistiğe 'strateji' kaynağı olarak katılır; yalnız okur)."""
    sonuc = []
    try:
        for f in st.okumalar()[:8]:
            try:
                j = st.oku(f)
            except (ValueError, OSError):
                continue
            for h in j.get("hamleler") or []:
                if isinstance(h, dict) and h.get("sonuc"):
                    sonuc.append({"sonuc": h["sonuc"], "sonuc_tarih": h.get("sonuc_tarih") or str(j.get("tarih") or "")[:10]})
    except OSError:
        pass
    return sonuc


def _kayit_bul(no):
    return next((r for r in sn.oku() if r["no"] == no), None)


def sonuc_isaretle(g):
    """{no, sonuc, not?, temas?, kanal?, neden?} → kaydın sonucunu işaretler; temas=true ise kişinin temas bölümüne satır eklenir (hariç kişiye eklenmez).
    sonuc "reddedildi" ("Uymuyor") için `neden` (sn.RED_NEDENLERI kodu) zorunludur; `not` isteğe bağlı kısa açıklamadır."""
    _izinli_alanlar(g, {"no", "sonuc", "not", "temas", "kanal", "neden"})
    no = g.get("no")
    if isinstance(no, bool) or not isinstance(no, int) or no < 1:
        raise ValueError("geçersiz kayıt numarası")
    if not isinstance(g.get("sonuc"), str) or g["sonuc"] not in sn.SONUCLAR:
        raise ValueError("bilinmeyen sonuç")
    neden = g.get("neden", "")
    if not isinstance(neden, str) or (neden and neden not in sn.RED_NEDENLERI):
        raise ValueError("bilinmeyen neden")
    r = sn.isaretle(no, g["sonuc"], _satir(g, "not", "Not", SONUC_METIN_AZAMI), _mantiksal(g, "temas"), _satir(g, "kanal", "Kanal", SONUC_KANAL_AZAMI),
                    neden=neden if g["sonuc"] == "reddedildi" else "")
    return {**r, "kayit": _kayit_bul(no)}


def sonuc_kaydet(g):
    """{kaynak: "yol"|"brifing", kisi, oneri} → önerilen adımı 'bekliyor' olarak deftere yazar ("Bu adımı takip et"). Hariç kişi için 400."""
    _izinli_alanlar(g, {"kaynak", "kisi", "oneri"})
    if g.get("kaynak") not in ("yol", "brifing"):
        raise ValueError("Bu kaynaktan kayıt açılamaz.")
    kid = _kisi_id(g, "kisi")
    k = kisi_bul(kid)
    if not k:
        raise ValueError("kişi bulunamadı")
    if c.haric_mi(k):
        raise ValueError("Bu kişi hariç listende; öneri kaydedilmez.")
    no = sn.kaydet(g["kaynak"], kid, _satir(g, "oneri", "Öneri", SONUC_METIN_AZAMI, zorunlu=True))
    return {"no": no, "kayit": _kayit_bul(no)}


def sonuclar_liste():
    """Pusula → Sonuçlar: son 60 kayıt (yeniden eskiye; hariç kişininkiler yok), son 8 hafta istatistiği (strateji sonuçları dahil), etiketler."""
    kisi = {k["id"]: k for k in _veri_oku()["kisiler"][1:]}
    kayitlar = []
    for r in sorted(sn.oku(), key=lambda r: (r.get("tarih") or "", r["no"]), reverse=True):
        k = kisi.get(r["kisi"])
        if k and k.get("haric"):
            continue
        kayitlar.append({**r, "kisi_ad": k["ad"] if k else ""})
        if len(kayitlar) == SONUC_LISTE_AZAMI:
            break
    return {"kayitlar": kayitlar, "istatistik": sn.istatistik(strateji_sonuclari=_strateji_sonuclari()), "etiketler": sn.SONUCLAR,
            "red_nedenleri": sn.RED_NEDENLERI}


def ozet_uret(g):
    """{yenile?} → bu haftanın özeti (yoksa üretilir ve deftere yazılır). Kayıtlı özette sonradan hariç listesine girenler çıkarılır; istatistiğe strateji sonuçları katılır."""
    _izinli_alanlar(g, {"yenile"})
    o = oz.olustur(yenile=_mantiksal(g, "yenile"))
    haric = {k["id"] for k in _veri_oku()["kisiler"][1:] if k.get("haric")}
    for alan, anahtar in (("maddeler", "id"), ("sozler", "id"), ("sonuc_bekleyen", "kisi")):
        o[alan] = [m for m in o.get(alan) or [] if m.get(anahtar) not in haric]
    o["bos"] = not o["maddeler"] and not o["sozler"]
    o["istatistik"] = sn.istatistik(strateji_sonuclari=_strateji_sonuclari())
    return {"ozet": o, "goruldu": oz.gorulen() == o.get("hafta"), "red_nedenleri": sn.RED_NEDENLERI}


def ozet_goruldu(g):
    _izinli_alanlar(g, {"hafta"})
    hafta = g.get("hafta")
    m = re.fullmatch(r"(\d{4})-W(\d{2})", hafta) if isinstance(hafta, str) else None
    try:
        date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)   # 01–53 ve o yılda gerçekten var olan hafta
    except (AttributeError, ValueError):
        raise ValueError("geçersiz hafta (YYYY-Www)") from None
    oz.goruldu(hafta)
    return {}


def bildirim_ayarla(g):
    """{acik?, siklik?, gun?, saat?, adlar?} → zamanlanmış görevi kurar/kaldırır, ayarı yazar, durumu döndürür. Kurulum hatası anlaşılır 400 olur."""
    with _bildirim_kilit:
        try:
            return bd.ayarla(g)
        except bd.KurulumHatasi as e:
            raise ValueError(str(e))


def bildirim_dene(g):
    """Deneme bildirimi (içerik sabit: ad, not, söz yok). Aynı anda tek deneme."""
    _izinli_alanlar(g, set())
    if not _dene_kilit.acquire(blocking=False):
        raise ValueError("Bir deneme bildirimi zaten gösteriliyor; birkaç saniye bekle.")
    try:
        return {"gosterildi": bd.bildir("Kut", "Bu bir deneme bildirimi. Haftalık özet hazır olunca Kut sana böyle haber verecek.")}
    finally:
        _dene_kilit.release()


ISLEMLER.update({"/api/yol": yol_uc, "/api/brifing": brifing_uc, "/api/ozet": ozet_uret, "/api/ozet/goruldu": ozet_goruldu,
                 "/api/sonuc": sonuc_isaretle, "/api/sonuc/kaydet": sonuc_kaydet, "/api/bildirim": bildirim_ayarla, "/api/bildirim/dene": bildirim_dene})
DEGISTIRMEYEN.update({"/api/yol", "/api/brifing", "/api/ozet", "/api/ozet/goruldu", "/api/sonuc/kaydet", "/api/bildirim", "/api/bildirim/dene"})   # harita sayfası değişmez
KILITSIZ.update({"/api/bildirim", "/api/bildirim/dene"})   # schtasks/PowerShell/osascript bekler (≤20 sn); veri kilidini tutmasınlar
KOKEN_DENETIMLI.update({"/api/ozet", "/api/ozet/goruldu", "/api/sonuc", "/api/sonuc/kaydet", "/api/bildirim", "/api/bildirim/dene"})   # yazanlar: Origin de bu sunucudan gelmeli


# ---------- demo önizlemesi: "Deniz'in salısı" (ag_demo.py). Yalıtım ve gerekçe modülün başındadır ----------
# /api/demo/baslat gerçek anahtarla (sayfa açık ve kilit açıkken), diğerleri DEMO anahtarıyla çalışır; ikisi de kilit + yerel Origin ister.
# Hiçbiri veri kilidini tutmaz, statik yenileme/günlük yazmaz: yazdıkları yalnız geçici demo klasörüdür.
def demo_yol(g):
    return yol_hesapla(g, ag_demo.ornek()["veri"])


def demo_brifing(g):
    o = ag_demo.ornek()
    return brifing_hesapla(g, o["veri"], o["sonuclar"], o["hedefler"], o["strateji"])   # hiçbiri gerçek veriden okunmaz


DEMO_UCLARI = {"/api/demo/baslat": lambda g: ag_demo.baslat(), "/api/demo/kapat": lambda g: ag_demo.kapat(), "/api/demo/sor": ag_demo.sor,
               "/api/demo/soz": ag_demo.soz_onayla, "/api/demo/isinma": ag_demo.isinma, "/api/demo/yol": demo_yol, "/api/demo/brifing": demo_brifing}
DEMO_ANAHTARLI = set(DEMO_UCLARI) - {"/api/demo/baslat"}
ISLEMLER.update(DEMO_UCLARI)
DEGISTIRMEYEN.update(DEMO_UCLARI)
KILITSIZ.update(DEMO_UCLARI)
KOKEN_DENETIMLI.update(DEMO_UCLARI)


def tarayici_ac(url):
    """Kut'u Edge/Chrome uygulama penceresinde açar: ayrı profil (yalnız Kut), giriş sesi kendiliğinden çalabilir.
    Tarayıcı bulunamazsa ya da ayarlar.json'da "tarayici": "varsayilan" ise varsayılan tarayıcı kullanılır."""
    if ((ia.ayarlar().get("ses") or {}).get("mikrofon")) == "izinli":
        try:
            mikrofon_izni_yaz()   # kullanıcı bir kez izin verdi: her açılışta izinli kalsın
        except Exception:
            gunluk("mikrofon izni: " + hata_izi())
    if ia.ayarlar().get("tarayici") != "varsayilan" and os.name == "nt":
        adaylar = [os.path.join(os.environ.get(k, ""), *p) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")
                   for p in (("Microsoft", "Edge", "Application", "msedge.exe"), ("Google", "Chrome", "Application", "chrome.exe"))]
        exe = next((a for a in adaylar if os.path.isfile(a)), None)
        if exe:
            try:
                subprocess.Popen([exe, f"--app={url}", "--autoplay-policy=no-user-gesture-required", "--no-first-run",
                                  "--user-data-dir=" + PROFIL], close_fds=True)
                return
            except OSError:
                pass
    webbrowser.open(url)


def main():
    global PORT
    if "--ozet" in sys.argv[1:]:   # doğrudan `ag_sunucu.py --ozet` çalıştırılırsa da sunucu açılmaz (normal giriş ag_giris.py'dir)
        sys.exit(bd.calistir(sys.argv))
    if os.environ.get("AGIM_PORT", "").isdigit():  # test için; --port önceliklidir
        PORT = int(os.environ["AGIM_PORT"])
    if "--port" in sys.argv:  # test ya da ikinci veri klasörü için
        PORT = int(sys.argv[sys.argv.index("--port") + 1])
    if "--veri" in sys.argv:
        c.veri_klasoru(sys.argv[sys.argv.index("--veri") + 1])
    url = f"http://127.0.0.1:{PORT}/"
    if calisiyor_mu():
        tarayici_ac(url)
        return
    try:
        goc.calistir(c.VERI)   # yalnız bekleyen veri göçü varsa (önce yedek); şimdilik hiç yok
    except Exception:
        gunluk("veri göçü: " + hata_izi())
    try:
        gunluk("arşiv bakımı: " + json.dumps(c.arsiv_bakimi(), ensure_ascii=False))
    except Exception:
        gunluk("arşiv bakımı: " + hata_izi())
    sunucu = ThreadingHTTPServer(("127.0.0.1", PORT), Isleyici)
    gu.KAPAT, gu.PORT_AL = sunucu.shutdown, lambda: PORT
    threading.Thread(target=gu.otomatik_denetim, daemon=True).start()   # yalnız kullanıcı izin verdiyse ve haftada bir
    threading.Thread(target=bekci, args=(sunucu,), daemon=True).start()
    gunluk("başladı")
    threading.Thread(target=_otomatik_doldur, daemon=True).start()
    if "--tarayicisiz" not in sys.argv:
        threading.Timer(0.4, lambda: tarayici_ac(url)).start()
    sunucu.serve_forever()


if __name__ == "__main__":
    main()
