"""Bağlamdan otomatik ilişki (bağ) kuran kural motoru. Model kullanmaz, ağ isteği yapmaz.

Kaynak: kadro önbelleği (ag_kaynak, kadro-<site>-<bölüm>.json), ben.md dersleri, kişi dosyaları (## Dersler, kurum, wa_sohbetler).
Kurallar:
  a. Aynı bölüm kadro listesinde birlikte görünen ağdaki kişiler → birlikte-calisiyor (resmi kaynak: doğrudan yazılır).
  b. Kullanıcının profil dersini veren hoca → hocasi (a = hoca, b = ben; resmi ders programı: doğrudan yazılır).
  b2. Kişinin "## Senin beyanların" bölümünde "<Ad Soyad> ve <Ad Soyad>'ın/'nin asistanı" varsa → asistan (a = asistan,
      b = hoca; kullanıcının doğrudan beyanı: doğrudan yazılır; ağda eşleşmeyen ad yazılmaz).
  c. Çıkarım gerektirenler (aynı WhatsApp sohbeti, aynı kurum/bölüm belirsiz, asistanın kime bağlı olduğu) → cikarimlar.md önerisi.
     Aynı çiftte iliskiler.md'de herhangi bir bağ ya da bekleyen herhangi bir bağ önerisi varsa WhatsApp önerisi üretilmez.
  d. Aynı çiftte aynı/daha güçlü bağ varsa eklenmez; kullanıcının bağına dokunulmaz (yalnız satır eklenir);
     reddedilen/bekleyen öneri tekrarlanmaz; hariç listesindeki kişiye bağ önerilmez.
bag_cikar(kaydet=False) yalnız raporlar.
"""
import re
from datetime import date

import ag_cekirdek as c
import ag_kaynak as kaynak
import ag_tutarlilik as tu

KAYNAK_ETIKET = "Kut · bağlam kuralı"
# aynı çiftte mevcut bağın gücü: eşit ya da yüksek varsa yenisi eklenmez
GUC = {"tanisiyor": 0, "arkadas": 1, "birlikte-calisiyor": 1}
WA_GRUP_ENCOK = 6  # daha büyük sohbetlerde çift öneri üretme (grup = doğrudan tanışıklık değil)
# sade() sonrası "<adlar> <ek> asistani": "Ada Deneme ve Deniz Örnek'in asistanı" → "... deniz ornek in asistani"
_ASISTAN_BEYAN = re.compile(r"^(?:\d{1,2} \d{1,2} \d{4} )?(.+?) (?:in|nin|un|nun) asistani(?: |$)")
_BEYAN_TARIH = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _guc(tip):
    return GUC.get(tip, 2)


def _cift(a, b):
    return frozenset((a, b))


def _mevcut(iliskiler):
    m = {}
    for i in iliskiler:
        m.setdefault(_cift(i["a"], i["b"]), []).append(i["tip"])
    return m


def _kararlar(cikarimlar):
    """{(kisi, tip, hedef): durum} reddedilen/düzeltilen/bekleyen bağ önerileri."""
    s = {}
    for r in cikarimlar:
        if r["alan"] == "iliski":
            tip, _, hedef = r["deger"].partition(" ")
            s[(r["kisi"], tip, hedef)] = r["durum"]
    return s


def _onceden_karar(kararlar, a, b, tip, bekleyen_da=False):
    for x, y in ((a, b), (b, a)):
        d = kararlar.get((x, tip, y))
        if d in ("reddedildi", "duzeltildi") or (bekleyen_da and d == "bekliyor"):
            return d
    return None


def _ders_anahtarlari(satirlar):
    """Metindeki 'ISE 256-1' biçimli ders şubeleri → {('ISE 256', '1')}."""
    return {(f"{m.group(1)} {m.group(2)}".upper(), m.group(3)) for m in re.finditer(r"\b([A-Za-z]{2,5}) (\d{3}[A-Za-z]?)-(\d+)\b", satirlar or "")}


def _ben_dersleri():
    sonuc = set()
    for d in c.liste_yap(c.ben().get("dersler")):
        kod, sube = kaynak._ders_coz(d)
        if kod:
            sonuc.add((kod, sube))
    return sonuc


def _ders_eslesir(kisi_dersleri, ben_dersleri):
    """Ortak dersler (şubesi belirtilmemişse kod yeterli) → sıralı 'ISE 256-1' listesi."""
    out = []
    for kod, sube in sorted(kisi_dersleri):
        if any(kod == bk and (bs is None or bs == sube) for bk, bs in ben_dersleri):
            out.append(f"{kod}-{sube}")
    return out


def _tarih_tr(iso):
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return str(iso or "")


def _asistan_beyanlari(govde):
    """Kişinin beyanlarındaki "<Ad> ve <Ad>'ın/'nin asistanı" satırları → [(["sade ad", ...], "GG.AA.YYYY" ya da "")]."""
    out = []
    for satir in c.bolum_oku(govde or "", c.BEYAN_BASLIK).splitlines():
        m = _ASISTAN_BEYAN.match(c.sade(satir))
        if m:
            t = _BEYAN_TARIH.search(satir)
            out.append(([x.strip() for x in m.group(1).split(" ve ") if x.strip()], t.group(0) if t else ""))
    return out


def _bekleyen_ciftler(cikarimlar):
    """Bekleyen (durum bekliyor) bağ önerilerinin çiftleri."""
    s = set()
    for r in cikarimlar:
        if r["alan"] == "iliski" and r["durum"] == "bekliyor":
            s.add(_cift(r["kisi"], r["deger"].partition(" ")[2].strip()))
    return s


def bag_cikar(kaydet=False):
    """Bağlamdan bağ adayları. Dönen: {"yazilan": [...], "onerilen": [...], "atlanan": [...]} (insan okunur satırlar).
    kaydet=False: yalnız rapor (hiçbir dosya değişmez)."""
    yazilan, onerilen, atlanan = [], [], []
    BI = c.ben_id()
    kisiler = c.kisileri_oku()
    kmap = {k["id"]: k for k in kisiler}
    ad = lambda i: (kmap.get(i) or {}).get("ad") or ("Sen" if i == BI else i)
    hl = c.haric_listesi()
    haric = {k["id"] for k in kisiler if c.haric_mi(k, hl)}
    iliskiler = c.iliskileri_oku()
    mevcut = _mevcut(iliskiler)
    cikarimlar = c.cikarimlari_oku()
    kararlar = _kararlar(cikarimlar)
    bugun = date.today().isoformat()
    yeni_bag, oneriler = [], []

    def dogrudan(a, b, tip, notu, kaynak_adi, kural):
        """Doğrudan yazılacak bağı kurallara göre ekler ya da atlanan listesine koyar."""
        etiket = f"{ad(a)} – {ad(b)} · {tip}"
        if a in haric or b in haric:
            atlanan.append(f"{etiket}: hariç listesinde, atlandı ({kural})")
            return
        var = mevcut.get(_cift(a, b), [])
        if any(v == tip for v in var):
            atlanan.append(f"{etiket}: zaten var ({kural})")
            return
        if any(_guc(v) >= _guc(tip) for v in var):
            atlanan.append(f"{etiket}: ikisi arasında zaten {'/'.join(var)} bağı var ({kural})")
            return
        if _onceden_karar(kararlar, a, b, tip):
            atlanan.append(f"{etiket}: daha önce reddedildi/düzeltildi ({kural})")
            return
        yeni_bag.append({"a": a, "b": b, "tip": tip, "not": notu, "kaynak": kaynak_adi, "tarih": bugun})
        mevcut.setdefault(_cift(a, b), []).append(tip)
        yazilan.append(f"{ad(a)} → {ad(b)} · {c.TIPLER[tip][0].split(' (')[0]}{': ' + notu if notu else ''} [{kaynak_adi}]")

    def oner(a, b, tip, gerekce, kural):
        etiket = f"{ad(a)} – {ad(b)} · {tip}"
        if a in haric or b in haric:
            atlanan.append(f"{etiket}: hariç listesinde, atlandı ({kural})")
            return
        var = mevcut.get(_cift(a, b), [])
        if any(_guc(v) >= _guc(tip) for v in var):
            atlanan.append(f"{etiket}: ikisi arasında zaten {'/'.join(var)} bağı var ({kural})")
            return
        d = _onceden_karar(kararlar, a, b, tip, bekleyen_da=True)
        if d:
            atlanan.append(f"{etiket}: önceden {d} ({kural})")
            return
        if any(o["kisi"] == a and o["deger"] == f"{tip} {b}" or o["kisi"] == b and o["deger"] == f"{tip} {a}" for o in oneriler):
            return
        oneriler.append({"kisi": a, "alan": "iliski", "deger": f"{tip} {b}", "gerekce": gerekce[:80], "kaynak": KAYNAK_ETIKET})
        onerilen.append(f"{ad(a)} – {ad(b)} · {tip}: {gerekce} [{KAYNAK_ETIKET}]")

    # --- a: kadro listesinde birlikte görünenler ---
    kadro_cift = set()
    onbellek = kaynak.kadro_onbellek_oku()
    if not onbellek:
        atlanan.append("kadro önbelleği yok: 'Kaynaktan doldur' çalışınca kadro kuralı (a) devreye girer")
    for kayit in onbellek:
        uyeler = []
        for kart in kayit["kartlar"]:
            k = kaynak.kart_esle(kart, kisiler, kayit.get("bolum_adi") or "")
            if k and k["id"] not in uyeler:
                uyeler.append(k["id"])
        bolum = kayit.get("bolum_adi") or kayit.get("onek") or kayit.get("bolum")
        notu = f"{bolum} kadrosu"
        kaynak_adi = f"Kut · kadro sayfası ({_tarih_tr(kayit.get('tarih'))})"
        for i, x in enumerate(uyeler):
            for y in uyeler[i + 1:]:
                kadro_cift.add(_cift(x, y))
                dogrudan(*sorted((x, y)), "birlikte-calisiyor", notu, kaynak_adi, "kural a")

    # --- b: profil dersini veren hoca → hocasi ---
    ben_d = _ben_dersleri()
    for k in kisiler:
        ortak = _ders_eslesir(_ders_anahtarlari(c.bolum_oku(k.get("govde"), "Dersler")), ben_d)
        if ortak:
            dogrudan(k["id"], BI, "hocasi", f"{', '.join(ortak)} dersini veriyor", f"Kut · ders programı ({(kaynak.okul_ayar() or {}).get('ders_kaynak') or 'okul'})", "kural b")

    # --- b2: kullanıcı beyanı "<Ad> ve <Ad>'ın asistanı" → asistan (a = asistan, b = hoca) ---
    adlar = {}
    for k in kisiler:
        adlar.setdefault(c.sade(k.get("ad") or ""), []).append(k["id"])
    for k in kisiler:
        for isimler, tarih in _asistan_beyanlari(k.get("govde")):
            for isim in isimler:
                hedef = [i for i in adlar.get(isim, []) if i != k["id"]]
                if len(hedef) != 1:
                    atlanan.append(f"{ad(k['id'])}: beyandaki '{isim}' ağdaki bir kişiyle eşleşmedi, asistan bağı yazılmadı (kural b2)")
                    continue
                dogrudan(k["id"], hedef[0], "asistan", "", f"Kut · kullanıcı beyanı ({tarih or _tarih_tr(bugun)})", "kural b2")

    # --- c: çıkarım gerektirenler ---
    # c1: aynı WhatsApp sohbet dosyasındaki kişiler (çifte herhangi bir bağ ya da bekleyen bağ önerisi varsa üretilmez)
    bekleyen_cift = _bekleyen_ciftler(cikarimlar)
    gruplar = {}
    for k in kisiler:
        for s in c.liste_yap(k.get("wa_sohbetler")):
            gruplar.setdefault(s, []).append(k["id"])
    for s, uyeler in sorted(gruplar.items()):
        if len(uyeler) > WA_GRUP_ENCOK:
            atlanan.append(f"{s}: {len(uyeler)} kişilik sohbet, çift önerisi üretilmedi")
            continue
        for i, x in enumerate(sorted(uyeler)):
            for y in sorted(uyeler)[i + 1:]:
                if mevcut.get(_cift(x, y)):
                    atlanan.append(f"{ad(x)} – {ad(y)} · tanisiyor: ikisi arasında zaten {'/'.join(mevcut[_cift(x, y)])} bağı var (kural c1)")
                elif _cift(x, y) in bekleyen_cift:
                    atlanan.append(f"{ad(x)} – {ad(y)} · tanisiyor: bu çift için bekleyen bağ önerisi var (kural c1)")
                else:
                    oner(x, y, "tanisiyor", f"Aynı WhatsApp sohbetinde ({s})", "kural c1")
    # c2: aynı kurum, bölüm belirsiz / kadro dışı (siyaset hariç)
    def kurum_parcalari(k):
        p = [x.strip() for x in (k.get("kurum") or "").split("·")]
        return c.sade(p[0]), c.sade(" ".join(p[:2]))
    aday = [k for k in kisiler if k.get("tur") != "siyaset" and kurum_parcalari(k)[0]]
    for i, x in enumerate(aday):
        for y in aday[i + 1:]:
            if _cift(x["id"], y["id"]) in kadro_cift:
                continue
            kx, ky = kurum_parcalari(x), kurum_parcalari(y)
            if kx[0] != ky[0] or kx[0] in hl:
                continue
            # Yalnız aynı bölüm. "Aynı kurum → tanışıyor" bilerek yok: büyük kurumda aynı yerde çalışmak tanışıklık değildir.
            if kx[1] == ky[1] and kx[1] != kx[0]:
                oner(x["id"], y["id"], "birlikte-calisiyor", f"Aynı kurum ve bölüm: {x['kurum']} (kadro listesinde doğrulanmadı)", "kural c2")
    # c3: rolü asistan olan kişi kimin asistanı? (kayıtta yok: uydurma, sor)
    var_asistan = {i["a"] for i in iliskiler if i["tip"] == "asistan"}
    for k in kisiler:
        beyan = c.sade(c.bolum_oku(k.get("govde") or "", c.BEYAN_BASLIK))
        asistan_mi = "asistan" in c.sade(k.get("rol") or "").split()
        if asistan_mi and k["id"] not in var_asistan and k["id"] not in haric and "asistan" not in beyan:  # kullanıcı söylediyse sorma
            soru = f"{k['ad']} hangi hocaların asistanı? Söylersen bağı 'asistan' olarak eklerim."
            if any(r["kisi"] == k["id"] and r["alan"] == "soru" and c.sade(r["deger"]) == c.sade(soru) for r in cikarimlar):
                atlanan.append(f"{k['ad']}: asistan sorusu zaten sorulmuş (kural c3)")
                continue
            oneriler.append({"kisi": k["id"], "alan": "soru", "kaynak": KAYNAK_ETIKET, "deger": soru})
            onerilen.append(f"{k['ad']}: kimin asistanı olduğu kayıtta yok, soru önerilecek [{KAYNAK_ETIKET}]")

    if kaydet:
        if yeni_bag:
            c.iliskileri_yaz(iliskiler + yeni_bag)
        if oneriler:
            oneriler, _ = tu.filtrele(oneriler)  # bilinen bağlamla çelişen öneri kuyruğa girmesin
            c.cikarim_ekle(oneriler)
    return {"yazilan": yazilan, "onerilen": onerilen, "atlanan": atlanan}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(bag_cikar(kaydet="--kaydet" in sys.argv), ensure_ascii=False, indent=1))
