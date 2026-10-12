"""WhatsApp sohbet dışa aktarması (.txt/.zip) ve telefon rehberi (.vcf) → aday kişiler.

Tamamen yerel çalışır, modele veya internete hiçbir şey göndermez. Mesaj İÇERİĞİ okunur ama saklanmaz:
yalnız katılımcı adı, mesaj sayısı, ilk/son tarih çıkarılır. Ham dosya diske yazılmaz (sunucu bellekte işler).
Adaylar veri klasörü dışında bekler (Windows: %LOCALAPPDATA%/agim, macOS: ~/.agim); kullanıcı seçtiklerini ağa ekler.
"""
import base64
import hashlib
import io
import json
import os
import quopri
import re
import zipfile
from datetime import date, datetime

from ag_cekirdek import sade

DEPO = os.path.join(os.environ["LOCALAPPDATA"], "agim") if os.environ.get("LOCALAPPDATA") else os.path.join(os.path.expanduser("~"), ".agim")
ADAYLAR = os.path.join(DEPO, "adaylar.json")
AYARLAR = os.path.join(DEPO, "ayarlar.json")

SATIR = re.compile(
    r"^[‎‏﻿]*\[?(\d{1,4})[./-](\d{1,2})[./-](\d{1,4}),?\s+(\d{1,2})[:.](\d{2})(?:[:.]\d{2})?\s*([AaPp]\.?\s?[Mm]\.?)?\]?\s*[-–]?\s*([^:]{1,80}?):\s"
)
GRUP_ADI = re.compile(r"(?:created group|changed the group name to|changed the subject to|grup adını|grubunu oluşturdu|grup konusunu)\s*[“\"]([^”\"]+)[”\"]|[“\"]([^”\"]+)[”\"]\s*(?:grubunu oluşturdu|olarak değiştirdi)", re.I)
SISTEM = re.compile(r"(uçtan uca|end-to-end|şifrelen|encrypted|gruba ekledi|added|ayrıldı|left|oluşturdu|created group|changed|değiştirdi)", re.I)


def tel_sade(t):
    d = re.sub(r"\D", "", t or "")
    return d[-10:] if len(d) >= 10 else d


def _json_oku(yol, bos):
    try:
        return json.load(open(yol, encoding="utf-8"))
    except (OSError, ValueError):
        return bos


def _json_yaz(yol, veri):
    os.makedirs(DEPO, exist_ok=True)
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)
    os.replace(gecici, yol)


def ayarlar():
    return _json_oku(AYARLAR, {"ben_adlari": []})


def ayar_yaz(a):
    _json_yaz(AYARLAR, a)


def adaylar():
    return _json_oku(ADAYLAR, {})


def adaylar_yaz(a):
    _json_yaz(ADAYLAR, a)


# ---------- WhatsApp ----------
def _sohbet_adi(dosya):
    ad = os.path.splitext(os.path.basename(dosya))[0]
    for kalip in (r"^WhatsApp Chat (?:with|-)\s*(.+)$", r"^WhatsApp Sohbeti\s*[-–]?\s*(.+)$", r"^(.+?) ile WhatsApp Sohbeti$",
                  r"^WhatsApp-Chat mit (.+)$", r"^Chat de WhatsApp con (.+)$"):
        m = re.match(kalip, ad, re.I)
        if m:
            return m.group(1).strip()
    return "" if ad.lower() in ("_chat", "chat") else ad


def _tarih(g, a, y, gun_once):
    g, a, y = int(g), int(a), int(y)
    if g > 31:  # yyyy-mm-dd
        g, a, y = y, a, g
    elif not gun_once:
        g, a = a, g
    if y < 100:
        y += 2000
    return date(y, a, g)


def whatsapp_coz(metin, dosya_adi, ben_adlari):
    satirlar = metin.replace("\r\n", "\n").split("\n")
    eslesen = [m for m in (SATIR.match(s) for s in satirlar) if m]
    if not eslesen:
        raise ValueError("WhatsApp satır biçimi tanınmadı (dışa aktarma .txt mi?)")
    # gün/ay sırası: '/' yoksa gün önce; '/' varsa alanlardaki >12 değerlerden anlaşılır (belirsizse TR: gün önce)
    egik = "/" in eslesen[0].group(0)[:14]
    gun_once = not egik or any(int(m.group(1)) > 12 for m in eslesen) or not any(int(m.group(2)) > 12 for m in eslesen)
    kisiler, akis = {}, []
    for m in eslesen:
        ad = m.group(7).strip().lstrip("~").strip()
        # iOS sistem satırları LRM ile başlar (gönderen olarak grup adı görünür)
        if SISTEM.search(ad) or m.string[m.end():].startswith("‎"):
            continue
        try:
            t = _tarih(m.group(1), m.group(2), m.group(3), gun_once)
            sa = int(m.group(4)) % 12 + (12 if (m.group(6) or "").lower().startswith("p") else 0) if m.group(6) else int(m.group(4))
            an = datetime(t.year, t.month, t.day, min(sa, 23), int(m.group(5)))
        except ValueError:
            continue
        k = kisiler.setdefault(ad, {"mesaj": 0, "ilk": t, "son": t})
        k["mesaj"] += 1
        k["ilk"], k["son"] = min(k["ilk"], t), max(k["son"], t)
        akis.append((ad, an))
    ben = {sade(b) for b in ben_adlari if b.strip()}
    ben_burada = [a for a in kisiler if sade(a) in ben]
    digerleri = {a: v for a, v in kisiler.items() if sade(a) not in ben}
    sohbet = _sohbet_adi(dosya_adi)
    grup = len(digerleri) > 1 or (sohbet and len(digerleri) == 1 and not ben_burada and sade(sohbet) != sade(next(iter(digerleri))))
    tum = list(kisiler.values())
    olcum = {} if grup or len(digerleri) != 1 else birebir_olcum(akis, set(ben_burada))
    adlar = [m.group(1) or m.group(2) for m in (GRUP_ADI.search(s) for s in satirlar) if m]
    if grup and adlar and (not sohbet or re.fullmatch(r"_?chat[\s\d()_-]*", sohbet, re.I)):
        sohbet = adlar[-1].strip()
    return {"sohbet": sohbet or (next(iter(digerleri)) if digerleri else dosya_adi), "grup": bool(grup),
            "ilk": min((v["ilk"] for v in tum), default=None), "son": max((v["son"] for v in tum), default=None),
            "kisiler": digerleri, "ben": ben_burada, "uyeler": list(digerleri), "ben_mesaj": sum(kisiler[a]["mesaj"] for a in ben_burada), "olcum": olcum}


def birebir_olcum(akis, benler, ara_saat=6):
    """Birebir sohbetten ilişki ölçümleri: oturum (6 saatten uzun ara = yeni konuşma), kimin başlattığı,
    medyan cevap süreleri, son 90 gün / önceki 90 gün mesaj oranı. İçerik kullanılmaz."""
    if not akis:
        return {}
    oturum = baslatan_o = 0
    cevap_o, cevap_ben = [], []
    onceki = None
    for ad, an in akis:
        ben_mi = ad in benler
        if onceki is None or (an - onceki[1]).total_seconds() > ara_saat * 3600:
            oturum += 1
            baslatan_o += 0 if ben_mi else 1
        elif (onceki[0] in benler) != ben_mi:
            dk = (an - onceki[1]).total_seconds() / 60
            (cevap_ben if ben_mi else cevap_o).append(dk)
        onceki = (ad, an)
    medyan = lambda x: round(sorted(x)[len(x) // 2]) if x else None
    bugun = datetime.now()
    son90 = sum(1 for _, an in akis if (bugun - an).days <= 90)
    onceki90 = sum(1 for _, an in akis if 90 < (bugun - an).days <= 180)
    return {"oturum": oturum, "baslatma_o": round(100 * baslatan_o / oturum) if benler else None,
            "cevap_o_dk": medyan(cevap_o), "cevap_ben_dk": medyan(cevap_ben), "son90": son90, "onceki90": onceki90}


ZIP_TEK_AZAMI = 60_000_000      # tek .txt açılmış boyutu
ZIP_TOPLAM_AZAMI = 150_000_000  # okunacak tüm .txt'lerin açılmış toplamı
ZIP_ORAN_AZAMI = 200            # açılmış/sıkıştırılmış oranı (zip bombası)


def _txt_metinleri(dosya_adi, ham):
    if ham[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(ham))
        except zipfile.BadZipFile:
            raise ValueError("ZIP dosyası bozuk")
        secilen = [i for i in z.infolist() if i.filename.lower().endswith(".txt") and not i.is_dir()]
        toplam = 0
        for i in secilen:   # hiçbir şey açılmadan ÖNCE: ../ ya da mutlak adlar, boyut ve oran
            if ".." in i.filename.replace("\\", "/").split("/") or i.filename.startswith(("/", "\\")) or os.path.isabs(i.filename):
                raise ValueError("ZIP içinde güvensiz dosya adı var; içe aktarılmadı")
            toplam += i.file_size
            if i.file_size > ZIP_TEK_AZAMI or toplam > ZIP_TOPLAM_AZAMI or i.file_size > ZIP_ORAN_AZAMI * max(i.compress_size, 1024):
                raise ValueError("ZIP beklenenden çok büyük açılıyor (zip bombası olabilir); içe aktarılmadı")
        for i in secilen:
            ic = os.path.basename(i.filename)
            with z.open(i) as f:
                veri = f.read(ZIP_TEK_AZAMI + 1)   # başlıktaki boyut yalan olabilir: gerçek okumayı da sınırla
            if len(veri) > ZIP_TEK_AZAMI:
                raise ValueError("ZIP beklenenden çok büyük açılıyor (zip bombası olabilir); içe aktarılmadı")
            yield (dosya_adi if ic.lower() in ("_chat.txt", "chat.txt") else ic), veri.decode("utf-8-sig", "replace")
    else:
        yield dosya_adi, ham.decode("utf-8-sig", "replace")


# ---------- VCF ----------
def vcf_coz(metin):
    satirlar = []
    for s in metin.replace("\r\n", "\n").split("\n"):
        if s[:1] in (" ", "\t") and satirlar:
            satirlar[-1] += s[1:]
        elif satirlar and satirlar[-1].endswith("=") and "QUOTED-PRINTABLE" in satirlar[-1].upper():
            satirlar[-1] = satirlar[-1][:-1] + s
        else:
            satirlar.append(s)
    kartlar, k = [], None
    for s in satirlar:
        if s.upper().startswith("BEGIN:VCARD"):
            k = {"telefon": [], "eposta": ""}
        elif s.upper().startswith("END:VCARD") and k is not None:
            if k.get("ad"):
                kartlar.append(k)
            k = None
        elif k is not None and ":" in s:
            bas, deger = s.split(":", 1)
            parca = bas.split(";")
            alan, param = parca[0].upper().split(".")[-1], ";".join(parca[1:]).upper()
            if "QUOTED-PRINTABLE" in param:
                deger = quopri.decodestring(deger.encode()).decode("utf-8", "replace")
            if alan == "FN":
                k["ad"] = deger.strip()
            elif alan == "N" and not k.get("ad"):
                p = deger.split(";") + ["", ""]
                k["ad"] = f"{p[1]} {p[0]}".strip()
            elif alan == "TEL" and deger.strip():
                k["telefon"].append(deger.strip())
            elif alan == "EMAIL" and not k["eposta"]:
                k["eposta"] = deger.strip()
            elif alan == "ORG":
                k["kurum"] = deger.replace(";", " · ").strip(" ·")
            elif alan == "TITLE":
                k["rol"] = deger.strip()
            elif alan == "PHOTO":
                try:
                    veri = deger.split(",", 1)[1] if deger.startswith("data:") else deger
                    if "http" not in veri[:8]:
                        ham = base64.b64decode(veri)
                        tip = "png" if ham[1:4] == b"PNG" else "jpeg"
                        k["foto"] = f"data:image/{tip};base64," + base64.b64encode(ham).decode()
                except (ValueError, IndexError):
                    pass
    return kartlar


# ---------- birleştirme ----------
def _aday_id(ad, telefonlar):
    t = next((tel_sade(x) for x in telefonlar if tel_sade(x)), "")
    return hashlib.sha1((t or sade(ad)).encode()).hexdigest()[:12]


def _bul(havuz, ad, telefonlar):
    tl = {tel_sade(x) for x in telefonlar if tel_sade(x)}
    for aid, a in havuz.items():
        if tl & {tel_sade(x) for x in a.get("telefon", [])}:
            return aid
    s = sade(ad)
    for aid, a in havuz.items():
        if tl and a.get("telefon"):
            continue  # aynı ad, farklı numara: farklı kişi
        if s and (sade(a["ad"]) == s or s in [sade(x) for x in a.get("diger_adlar", [])]):
            return aid
    return None



def _oneri(a):
    birebir = [k for k in a["kaynaklar"] if k["tip"] == "wa-birebir"]
    toplam = sum(k["mesaj"] + k.get("ben_mesaj", 0) for k in birebir)
    kucuk_grup = [k for k in a["kaynaklar"] if k["tip"] == "wa-grup" and k.get("boyut", 99) <= 8]
    if toplam >= 500 or any(k["mesaj"] >= 300 for k in kucuk_grup):
        y = 2
    elif birebir or kucuk_grup or any(k["tip"] == "rehber" for k in a["kaynaklar"]):
        y = 1
    else:
        y = 0
    sonlar = [k["son"] for k in birebir + kucuk_grup if k.get("son")]  # küçük grupta birlikte yazışmak da temas
    a["oneri_yakinlik"] = y
    a["oneri_son_temas"] = max(sonlar) if sonlar else ""


def ice_aktar(dosya_adi, ham, mevcut_kisiler, sakla=None):
    """Dosyayı çözümler, adayları birleştirir. sakla: verilirse WhatsApp metni asistan analizi için bu klasöre yazılır.
    Dönen: özet sözlüğü."""
    havuz = adaylar()
    ben_adlari = ben_adlari_al()
    bugun = date.today().isoformat()
    ozet = {"dosya": dosya_adi, "yeni": 0, "guncellenen": 0, "sohbetler": [], "uyari": ""}

    def birlestir(ad, telefonlar, kaynak, ek):
        aid = _bul(havuz, ad, telefonlar)
        if aid is None:
            aid = _aday_id(ad, telefonlar)
            havuz[aid] = {"id": aid, "ad": ad, "telefon": [], "kaynaklar": [], "durum": "yeni", "diger_adlar": []}
            ozet["yeni"] += 1
        else:
            ozet["guncellenen"] += 1
        a = havuz[aid]
        if ad and sade(ad) != sade(a["ad"]) and ad not in a["diger_adlar"]:
            if re.fullmatch(r"[+\d\s()-]{7,}", a["ad"]):
                a["diger_adlar"].append(a["ad"]); a["ad"] = ad
            else:
                a["diger_adlar"].append(ad)
        for t in telefonlar:
            if tel_sade(t) and tel_sade(t) not in {tel_sade(x) for x in a["telefon"]}:
                a["telefon"].append(t)
        for k, v in ek.items():
            if v and not a.get(k):
                a[k] = v
        a["kaynaklar"] = [k for k in a["kaynaklar"] if not (k["tip"] == kaynak["tip"] and k.get("sohbet") == kaynak.get("sohbet"))] + [kaynak]
        _oneri(a)

    if dosya_adi.lower().endswith(".vcf"):
        kartlar = vcf_coz(ham.decode("utf-8-sig", "replace"))
        for k in kartlar:
            birlestir(k["ad"], k["telefon"], {"tip": "rehber", "tarih": bugun},
                      {"eposta": k.get("eposta"), "kurum": k.get("kurum"), "rol": k.get("rol"), "foto": k.get("foto")})
        ozet["sohbetler"].append(f"rehber: {len(kartlar)} kişi")
    else:
        for ad, metin in _txt_metinleri(dosya_adi, ham):
            s = whatsapp_coz(metin, ad, ben_adlari)
            ham_yol = ""
            if sakla:
                os.makedirs(sakla, exist_ok=True)
                ham_yol = os.path.join(sakla, re.sub(r"\s+", "-", sade(s["sohbet"]))[:60] + ".txt")
                with open(ham_yol, "w", encoding="utf-8") as f:
                    f.write(metin)
            if not s["ben"]:
                ozet["uyari"] = (f"Sohbette senin adın ({', '.join(ben_adlari)}) bulunamadı; kendi adın aday olarak görünebilir. "
                                 "'WhatsApp'taki adım' alanına sohbette görünen adını yaz.")
            for kad, v in s["kisiler"].items():
                tel = [kad] if re.fullmatch(r"[+\d\s()-]{7,}", kad) else []
                kaynak = {"tip": "wa-grup" if s["grup"] else "wa-birebir", "sohbet": s["sohbet"], "mesaj": v["mesaj"],
                          "ilk": v["ilk"].isoformat(), "son": v["son"].isoformat(), "tarih": bugun}
                if s["grup"]:
                    kaynak.update(uyeler=s["uyeler"], boyut=len(s["uyeler"]) + 1)
                if not s["grup"]:  # birebirde tarih aralığı iki tarafın mesajlarını kapsar
                    kaynak.update(ben_mesaj=s["ben_mesaj"], ilk=s["ilk"].isoformat(), son=s["son"].isoformat(), **s["olcum"])
                if ham_yol:
                    kaynak["ham"] = os.path.basename(ham_yol)
                birlestir(kad, tel, kaynak, {})
            ozet["sohbetler"].append(f"{'grup' if s['grup'] else 'birebir'}: {s['sohbet']} ({len(s['kisiler'])} kişi)")

    # aynı adlı, numaraları çelişmeyen adayları birleştir (ör. önce numarayla, sonra adla gelen kişi)
    for aid in list(havuz):
        a = havuz.get(aid)
        if not a or a.get("durum") != "yeni":
            continue
        for bid in list(havuz):
            b = havuz.get(bid)
            if bid == aid or not b or b.get("durum") != "yeni" or sade(b["ad"]) != sade(a["ad"]):
                continue
            ta, tb = {tel_sade(x) for x in a["telefon"]}, {tel_sade(x) for x in b["telefon"]}
            if ta and tb and not ta & tb:
                continue
            a["telefon"] += [x for x in b["telefon"] if tel_sade(x) not in ta]
            a["diger_adlar"] = sorted(set(a.get("diger_adlar", []) + b.get("diger_adlar", [])))
            for k in b["kaynaklar"]:
                if not any(x["tip"] == k["tip"] and x.get("sohbet") == k.get("sohbet") for x in a["kaynaklar"]):
                    a["kaynaklar"].append(k)
            for alan in ("eposta", "kurum", "rol", "foto"):
                if b.get(alan) and not a.get(alan):
                    a[alan] = b[alan]
            _oneri(a)
            havuz.pop(bid)

    # ağda zaten olanları işaretle
    for a in havuz.values():
        if a.get("durum") != "yeni":
            continue
        a["eslesen"], a["eslesen_oneri"] = "", []
        tl = {tel_sade(x) for x in a["telefon"]}
        for k in mevcut_kisiler:
            if sade(k["ad"]) == sade(a["ad"]) or tl & {tel_sade(x) for x in k.get("telefon", [])}:
                a["eslesen"] = k["id"]
                break
        if not a["eslesen"]:
            parca = set(sade(a["ad"]).split())
            a["eslesen_oneri"] = [k["id"] for k in mevcut_kisiler if parca and parca <= set(sade(k["ad"]).split())]
    adaylar_yaz(havuz)
    return ozet


def ben_adlari_al():
    """Ayardaki WhatsApp adları; yoksa profildeki ad ve ilk adı."""
    adlar = [x for x in ayarlar().get("ben_adlari", []) if x.strip()]
    if adlar:
        return adlar
    import ag_cekirdek
    ad = (ag_cekirdek.ben().get("ad") or "").strip()
    return [x for x in {ad, ad.split()[0] if ad else ""} if x and x != "Ben"]


def grup_etiketi(sohbet):
    return "wa-" + re.sub(r"\s+", "-", sade(sohbet))[:40]
