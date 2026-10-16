"""Kut ajandası: koddaki tarihli her şeyi tek, SALT-OKUR bir takvim akışında toplar (Pusula → Takvim görünümü).

Model yok, ağ yok, hiçbir şey yazmaz; yalnız yerel veri klasörünü ve keşif önbelleğini (zaten diskte olan etkinlikler.json) okur.
Kaynaklar (her öğe: tarih, tur, baslik, hedef, kisi, durum, alt, ayrinti):
- hamle   : strateji okumasındaki hamlenin `son_tarih`'i; sonucu işaretliyse `tamam`. Son okumanın tüm hamleleri, eski okumalardan yalnız sonuç tarihi olanlar.
- hedef   : hedefin `son_tarih`'i (alt `son_tarih`) ve `## İlerleme` satırları (alt `ilerleme`, tamam).
- soz     : açık sözün `son:` tarihi (gecikmiş/bugün/yaklaşan), tarihsiz ama uzun süredir açık söz (alt `tarihsiz`, bugüne konur), kapanan sözün kapanış tarihi.
- kisi    : `sonraki_adim`/`sonraki_tarih` (alt `sonraki_adim`) ve sonraki tarihi olmayan kişide ihmal eşiğinin dolacağı gün (alt `ihmal`; `ag_cekirdek.IHMAL_GUN`).
- etkinlik: keşif kararı `katilacagim`/`ilgileniyorum` olan etkinlikler; tarih keşif önbelleğindeki (`kesif/etkinlikler.json`) `baslangic`'tan gelir.
            Önbellekte olmayan ya da tarihi okunamayan karar `tarihsiz` sayısına girer (öğe üretilmez).
- temas   : kişi dosyalarındaki `## Temas` satırları (alt `gecmis`, tamam; geçmiş günlerde soluk gösterim için).
`haric.md` ile eşleşen kişi hiçbir öğede (ne kendi ne de ona bağlı hamle/söz/temas) görünmez.
Durum: gecikmis | bugun | yaklasan | tamam. Aralık sınırlıdır (AZAMI_GUN) ve girdiler `YYYY-AA-GG` olarak doğrulanır.
"""
import json
import os
import re
from datetime import date, timedelta

import ag_cekirdek as c
import ag_hedef as hd
import ag_kesif as ks
import ag_soz
import ag_strateji as st

TURLER = ("hamle", "hedef", "soz", "kisi", "etkinlik", "temas")
DURUMLAR = ("gecikmis", "bugun", "yaklasan", "tamam")
AZAMI_GUN = 400          # tek istekte en çok bu kadar günlük aralık
GECIKMIS_AZAMI = 60      # aralığın öncesinden taşınan gecikmiş öğe sayısı sınırı
OKUMA_AZAMI = 5          # bakılan en son strateji okuması sayısı
BASLIK_AZAMI = 160
ETKINLIK_KARARLARI = ("katilacagim", "ilgileniyorum")
_TARIH = re.compile(r"\d{4}-\d{2}-\d{2}")


def tarih_oku(s):
    """Yalnız `YYYY-AA-GG` (fromisoformat'ın 'YYYYMMDD' gibi biçimlerini kabul etmez); geçersizse None."""
    s = str(s or "").strip()
    if not _TARIH.fullmatch(s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def aralik(bas=None, bit=None, bugun=None):
    """Girdileri doğrular. Boşsa bugünün ayı. Dönen: (bas, bit) date; geçersizse ValueError (sunucuda 400)."""
    bugun = bugun or date.today()
    if not bas and not bit:
        ilk = bugun.replace(day=1)
        return ilk, (ilk + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    b, t = tarih_oku(bas), tarih_oku(bit)
    if not b or not t:
        raise ValueError("bas ve bit YYYY-AA-GG olmalı")
    if t < b:
        raise ValueError("bit, bas'tan önce olamaz")
    if (t - b).days > AZAMI_GUN:
        raise ValueError(f"aralık en çok {AZAMI_GUN} gün olabilir")
    return b, t


def _kisa(m, n=BASLIK_AZAMI):
    m = " ".join(str(m or "").split())
    return m if len(m) <= n else m[:n - 1].rstrip() + "…"


def _durum(gun, bugun, kapali=False):
    if kapali:
        return "tamam"
    return "gecikmis" if gun < bugun else "bugun" if gun == bugun else "yaklasan"


def _oge(gun, tur, baslik, durum, alt, hedef="", kisi="", ayrinti=None, kimlik=""):
    return {"id": kimlik or f"{tur}:{alt}:{gun.isoformat()}:{hedef or kisi}", "tarih": gun.isoformat(), "tur": tur, "alt": alt, "baslik": _kisa(baslik),
            "hedef": hedef, "kisi": kisi, "durum": durum, "ayrinti": {k: v for k, v in (ayrinti or {}).items() if v not in ("", None, [])}}


def _gg_aa_yyyy(s):
    m = re.match(r"\s*(\d{2})\.(\d{2})\.(\d{4})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _kisiler():
    """Okunabilen kişiler + hariç kümesi. Hariç kişi `haric` kümesinde; öğe üreten her kaynak bu kümeye bakar.
    Kişiler okunamazsa `haric` None döner: hangi kişinin hariç olduğu bilinemez, hamleler de gösterilmez (kapalı kalır)."""
    try:
        kisiler = c.kisileri_oku()
    except OSError:
        return [], None
    hl = c.haric_listesi()
    return kisiler, {k["id"] for k in kisiler if c.haric_mi(k, hl)}


def _vekil_partileri():
    """{vekil:<slug>: parti} keşfin diskteki vekil dizininden (CSV'leri yeniden işlemez, ağ yok). Okunamazsa {}."""
    try:
        d = json.load(open(os.path.join(ks.KLASOR, "vekil-dizin.json"), encoding="utf-8"))
        return {"vekil:" + c.slug(ad): str((x.get("bilgi") or {}).get("parti") or "") for ad, x in (d.get("veri") or {}).items()}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def _hamleler(bugun, haric, hedef_ad, kisiler=()):
    """Hariç süzgeci üç yoldan: kişi id'si (kim / kim_uzerinden), vekilin partisi (strateji sonradan genişleyen haric.md'yi
    bilmez; partisi çözülemeyen vekil hamlesi hariç liste doluyken gösterilmez) ve metinde hariç kişinin adı."""
    if haric is None:
        return []
    out, hl = [], c.haric_listesi()
    partiler = _vekil_partileri() if hl else {}
    haric_adlar = [c.sade(k.get("ad") or "") for k in kisiler if k["id"] in haric and len(c.sade(k.get("ad") or "")) > 3]
    okumalar = st.okumalar()[:OKUMA_AZAMI]
    for sira, dosya in enumerate(okumalar):
        try:
            j = st.oku(dosya)
        except (ValueError, OSError, TypeError, AttributeError):
            continue
        if not isinstance(j, dict):
            continue
        for no, h in enumerate(j.get("hamleler") or []):
            if not isinstance(h, dict):
                continue
            kim = str(h.get("kim") or "")
            ids = {kim, str(h.get("kim_uzerinden") or "")}
            if ids & haric:
                continue
            if hl and kim.startswith("vekil:") and (kim not in partiler or c.haric_mi({"parti": partiler[kim]}, hl)):
                continue
            if haric_adlar:
                metin = " " + c.sade(" ".join(str(h.get(a) or "") for a in ("baslik", "ilk_adim", "neden_simdi", "taslak", "gormedigin"))) + " "
                if any(f" {a} " in metin for a in haric_adlar):
                    continue
            sonuc = str(h.get("sonuc") or "")
            son, sonuc_gun = tarih_oku(h.get("son_tarih")), tarih_oku(h.get("sonuc_tarih"))
            if sira > 0 and not (sonuc and sonuc_gun):   # eski okumalar yalnız kapanmış hamleyle katkı verir
                continue
            gun = son or sonuc_gun
            if not gun:
                continue
            kapali = bool(sonuc)
            kisi = kim if kim and c.gecerli_id(kim) and not kim.startswith(("vekil:", "etkinlik:")) else ""
            out.append(_oge(gun, "hamle", h.get("baslik") or "Hamle", _durum(gun, bugun, kapali), "sonuc" if kapali and not son else "son_tarih",
                            hedef=h.get("hedef") or "", kisi=kisi, kimlik=f"hamle:{dosya[:-3]}:{no}",
                            ayrinti={"ilk_adim": _kisa(h.get("ilk_adim"), 300), "hedef_baslik": hedef_ad.get(h.get("hedef"), ""), "guven": h.get("guven"),
                                     "sonuc": st.SONUCLAR.get(sonuc, ""), "sonuc_not": _kisa(h.get("sonuc_not"), 200), "kim": kim if not kisi else "",
                                     "neden_simdi": _kisa(h.get("neden_simdi"), 300)}))
    return out


def _hedefler(bugun):
    out, ad = [], {}
    for h in hd.hepsi():
        ad[h["id"]] = h.get("baslik") or h["id"]
        if h.get("durum") == "birakildi":
            continue
        kapali = h.get("durum") == "tamam"
        son = tarih_oku(h.get("son_tarih"))
        if son:
            out.append(_oge(son, "hedef", h.get("baslik") or h["id"], _durum(son, bugun, kapali), "son_tarih", hedef=h["id"], kimlik=f"hedef:{h['id']}:son",
                            ayrinti={"olcut": _kisa(h.get("olcut"), 300), "hedef_durum": hd.DURUMLAR.get(h.get("durum"), ""), "oncelik": h.get("oncelik")}))
        for i, x in enumerate(h.get("ilerleme") or []):
            gun = _gg_aa_yyyy(x)
            if gun:
                metin = x.split("·", 1)[1].strip() if "·" in x else x
                out.append(_oge(gun, "hedef", f"{h.get('baslik') or h['id']}: {metin}", "tamam", "ilerleme", hedef=h["id"], kimlik=f"hedef:{h['id']}:ilerleme:{i}"))
    return out, ad


def _kisi_ogeleri(kisiler, haric, bugun):
    """sonraki adım + ihmal eşiği + sözler + geçmiş temaslar; hariç kişi atlanır."""
    out = []
    for k in kisiler:
        kid, ad = k["id"], k.get("ad") or k["id"]
        if kid in haric:
            continue
        st_gun = tarih_oku(k.get("sonraki_tarih"))
        if st_gun:
            out.append(_oge(st_gun, "kisi", f"{ad}: {k.get('sonraki_adim') or 'Sonraki adım'}", _durum(st_gun, bugun), "sonraki_adim", kisi=kid,
                            kimlik=f"kisi:{kid}:sonraki", ayrinti={"sonraki_adim": _kisa(k.get("sonraki_adim"), 300), "ad": ad}))
        else:
            esik, son = c.IHMAL_GUN.get(k.get("yakinlik", 0)), c.etkin_son_temas(k, bugun)
            if esik and son:
                gun = son + timedelta(days=esik)
                out.append(_oge(gun, "kisi", f"{ad}: temas eşiği ({esik} gün)", _durum(gun, bugun), "ihmal", kisi=kid, kimlik=f"kisi:{kid}:ihmal",
                                ayrinti={"son_temas": son.isoformat(), "esik_gun": esik, "ad": ad}))
        govde = k.get("govde") or ""
        for s in ag_soz.oku(govde):
            if s["durum"] == "iptal":
                continue
            yon = ag_soz.ETIKET[s["yon"]]
            baslik = f"{ad}: {s['metin']}"
            ayr = {"yon": yon, "metin": s["metin"], "ad": ad, "verildi": s["tarih"]}
            if s["durum"] == "tamam":
                gun = tarih_oku(s["kapanis"]) or tarih_oku(s["son"]) or tarih_oku(s["tarih"])
                if gun:
                    out.append(_oge(gun, "soz", baslik, "tamam", "tamam", kisi=kid, kimlik=f"soz:{kid}:{s['sira']}", ayrinti=ayr))
                continue
            son_g = tarih_oku(s["son"])
            if son_g:
                out.append(_oge(son_g, "soz", baslik, _durum(son_g, bugun), "son_tarih", kisi=kid, kimlik=f"soz:{kid}:{s['sira']}", ayrinti=ayr))
            else:
                ver = tarih_oku(s["tarih"])
                if ver and (bugun - ver).days >= ag_soz.TARIHSIZ_UYARI_GUN:
                    out.append(_oge(bugun, "soz", baslik, "gecikmis", "tarihsiz", kisi=kid, kimlik=f"soz:{kid}:{s['sira']}",
                                    ayrinti={**ayr, "acik_gun": (bugun - ver).days}))
        for sat in c.bolum_oku(govde, "Temas").splitlines():
            gun = _gg_aa_yyyy(sat[2:]) if sat.startswith("- ") else None
            if gun:
                parca = [p.strip() for p in sat[2:].split("·")]
                kanal, ozet = (parca[1] if len(parca) > 1 else ""), (parca[2] if len(parca) > 2 else "")
                out.append(_oge(gun, "temas", f"{ad}" + (f" · {kanal}" if kanal else ""), "tamam", "gecmis", kisi=kid,
                                kimlik=f"temas:{kid}:{gun.isoformat()}:{len(out)}", ayrinti={"kanal": kanal, "ozet": _kisa(ozet, 200), "ad": ad}))
    return out


def _etkinlikler(bugun):
    """Karar `katilacagim`/`ilgileniyorum` olan etkinlikler. Dönen: (öğeler, tarihsiz karar sayısı)."""
    kararlar = {a: v for a, v in ks.kararlar().items() if a.startswith("etkinlik:") and v.get("karar") in ETKINLIK_KARARLARI}
    if not kararlar:
        return [], 0
    yol = os.path.join(ks.KLASOR, "etkinlikler.json")
    try:
        with open(yol, encoding="utf-8") as f:
            onbellek = {e.get("anahtar"): e for e in (json.load(f).get("etkinlikler") or []) if isinstance(e, dict)}
    except (OSError, ValueError):
        onbellek = {}
    out, tarihsiz = [], 0
    for anahtar, v in sorted(kararlar.items()):
        e = onbellek.get(anahtar)
        gun = tarih_oku(str((e or {}).get("baslangic") or "")[:10])
        if not e or not gun:
            tarihsiz += 1
            continue
        saat = str(e["baslangic"])[11:16] if len(str(e["baslangic"])) >= 16 else ""
        bitis = tarih_oku(str(e.get("bitis") or "")[:10])
        son = bitis if bitis and bitis >= gun else gun
        durum = "tamam" if son < bugun else "bugun" if gun <= bugun <= son else "yaklasan"   # etkinlik gecikmiş olmaz; süren etkinlik bugündür
        out.append(_oge(gun, "etkinlik", e.get("ad") or "Etkinlik", durum, "baslangic", kimlik=f"etkinlik:{anahtar}",
                        ayrinti={"anahtar": anahtar, "karar": v["karar"], "yer": _kisa(e.get("yer"), 160), "cevrimici": bool(e.get("cevrimici")), "saat": saat,
                                 "bitis": bitis.isoformat() if bitis else "", "url": e.get("url") if str(e.get("url") or "").startswith(("http://", "https://")) else "",
                                 "duzenleyen": _kisa(e.get("duzenleyen"), 80)}))
    return out, tarihsiz


def topla(bugun=None):
    """Tüm tarihli öğeler (süzülmemiş) ve notlar. Dönen: (öğeler, {tarihsiz_etkinlik})."""
    bugun = bugun or date.today()
    kisiler, haric = _kisiler()
    hedef_ogeler, hedef_ad = _hedefler(bugun)
    etk, tarihsiz = _etkinlikler(bugun)
    ogeler = _hamleler(bugun, haric, hedef_ad, kisiler) + hedef_ogeler + _kisi_ogeleri(kisiler, haric or set(), bugun) + etk
    return ogeler, {"tarihsiz_etkinlik": tarihsiz}


def ajanda(bas=None, bit=None, bugun=None):
    """`/api/ajanda` cevabı: aralıktaki öğeler (tarihe, sonra türe göre sıralı) + aralığın öncesinden kalan gecikmişler (`gecikmisler`)."""
    bugun = bugun or date.today()
    b, t = aralik(bas, bit, bugun)
    tum, not_ = topla(bugun)
    sira = {k: i for i, k in enumerate(TURLER)}
    anahtar = lambda o: (o["tarih"], sira[o["tur"]], o["baslik"])
    ici = sorted((o for o in tum if b.isoformat() <= o["tarih"] <= t.isoformat()), key=anahtar)
    onceki = sorted((o for o in tum if o["durum"] == "gecikmis" and o["tarih"] < b.isoformat()), key=anahtar, reverse=True)
    return {"bas": b.isoformat(), "bit": t.isoformat(), "bugun": bugun.isoformat(), "ogeler": ici, "gecikmisler": onceki[:GECIKMIS_AZAMI],
            "gecikmis_toplam": len(onceki), **not_}
