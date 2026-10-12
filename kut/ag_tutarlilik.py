"""Bağlam tutarlılık katmanı: asistanın çıkarım/soru önerilerini, kullanıcının zaten bildirdiği ya da ağda kayıtlı
bağlamla karşılaştırır. Çelişen, cevaplanmış ya da gereksiz öneri kullanıcıya hiç gösterilmez (kuyruğa girmez ya da kapanır).

- bilinen_baglam(kid): modele verilecek "KESİN BİLİNENLER" metni.
- celisiyor_mu(oneri, baglam): kural tabanlı kapı, model çağrısı yok.
- filtrele(oneriler): kapıyı toplu uygular (ag_analiz.uygula / belge / sohbet akışları).
- kuyrugu_temizle(kid=None): bekleyen kuyruğu tarar; çelişenleri SİLMEZ, durumunu "kapandi" yapar.
  Kısmen geçerli etiket önerisi kapatılır, kalan meşru etiketlerle yeni öneri eklenir.

Yalnız ag_cekirdek'e bağlıdır (ag_analiz bunu içe aktarır). Model çağrısı yok.
"""
import os
import re

import ag_cekirdek as c

KAPANDI = "kapandi"
KAPANIS_ONEKI = "Kut: bilinen bağlamla çelişiyor — "
# bağ gücü (yalnız pozitif/nötr tipler karşılaştırılır; rakip/gerginlik kıyaslanmaz)
GUC = {"tanisiyor": 1, "arkadas": 2, "birlikte-calisiyor": 2, "mentor": 2, "yonetici": 2, "is-ortagi": 2, "akraba": 3, "partner": 3}
YAKIN_BAG = ("partner", "akraba")

# sade() çıktısına uygulanır (küçük harf, aksansız)
# Yalnız sıklık / kanal / birebir-grup kalıpları. 'görüşme, konuştu, iletişim, temas, ne zaman görüş' gibi genel sözcükler
# yanlış pozitif verir ("sınav takvimi hakkında konuştunuz mu?", "e-posta güncel mi?", "ne zaman görüşmeyi planlıyorsun?").
_TEMAS = re.compile(r"ne siklikla|ne kadar sik|birebir|grup disi|grup uzerinden|en son ne zaman|yuz yuze mi|hangi kanal")
# günlük yaşam / hobi etiketi: AGENTS.md "günlük yaşam alışkanlığı etiket değildir". Etiketin bir sözcüğü hobi sözcüğüyse ve
# etiket mesleki bir sözcük taşımıyorsa hobidir ('oyun-gelistirme' mesleki kalır, 'oyun-geoguessr' hobidir).
_HOBI = re.compile(r"^(?:oyun\w*|geoguessr|kosu|kosucu|kosusu|dizi|diziler|film\w*|yemek\w*|kedi\w*|kopek\w*|cilt|seyahat|gezi\w*|tatil\w*|sinema"
                   r"|futbol|fitness|yoga|kamp|dans|hobi\w*|evcil|uyku|diyet|alisveris|temizlik|bahce\w*|rutin|aliskanlik\w*|guzellik)$")
_MESLEKI = re.compile(r"gelistir|tasarim|muhendis|yazilim|programla|uretim|analiz|girisim|arastirma|akademi|egitim|proje|hackathon")
_HOBI_METIN = re.compile(r"\b(?:oyun\w*|geoguessr|kosu|kosusu|kosuyor\w*|dizi|diziler|film\w*|seyahat\w*|hobi\w*|tatil\w*|kedi\w*|kopek\w*|cilt bakim\w*)\b")
# kullanıcı beyanını tekrar eden özet kalıpları (sıklık, birlikte yaşama)
_OZET_TEKRAR = re.compile(r"her gun|gunluk|haftalik|haftada|sik yazis\w*|sik gorus\w*|siklikla|birlikte yasi\w*|ayni evde|ayni ev\b")
_TANISMA = re.compile(r"nasil tanis|tanisiyor musunuz|dogrudan tanis|nasil bir iliski|aranizdaki bag|aranizdaki iliski")
_OZEL = re.compile(r"\b(ev ici|evde|ayni ev|ayni evde|birlikte yasi\w*|yasiyoruz|ev arkadas\w*|kavga\w*|baris\w*|bosan\w*|ayril\w*|kiskan\w*"
                   r"|sevgili\w*|aldat\w*|yemek|alisveris|temizlik|uyku\w*|evcil|kedi|kopek|diyet|bakim|ev isleri|aliskanlik\w*|rutin\w*"
                   r"|dindar\w*|ateist\w*|etnik\w*|escinsel\w*|cinsel\w*|teshis\w*|zaaf\w*|hastalig\w*|depresyon\w*)\b")
_BIRLIKTE_YASIYOR = re.compile(r"birlikte yasi|ayni evde|ayni yerde kal|beraber yasi|ayni ev")
_KIZ_ARK = re.compile(r"kiz arkadas|erkek arkadas|sevgili|nisanli|\besi\b")


def _belirtec(s):
    return {w[:5] for w in c.sade(s).split() if len(w) > 2}


def _benzerlik(a, b):
    x, y = _belirtec(a), _belirtec(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def _bag_cifti(deger):
    """'arkadas ada-deneme' -> ('arkadas', 'ada-deneme')"""
    tip, _, hedef = str(deger or "").strip().partition(" ")
    return tip, hedef.strip()


# ---------- bilinen bağlam ----------
def baglam_yapisi(kid):
    """Kişi için kesin bilinenlerin yapısı (kural filtresi bunu kullanır)."""
    yol = os.path.join(c.KISILER, f"{kid}.md")
    k = c.kisi_oku(yol) if c.gecerli_id(kid) and os.path.exists(yol) else None
    k = k or {}
    govde = k.get("govde") or ""
    beyanlar = [re.sub(r"^-\s*", "", s).strip() for s in c.bolum_oku(govde, c.BEYAN_BASLIK).splitlines() if s.strip()]
    ben = c.ben_id()
    baglar, ben_baglari = [], []
    for i in c.iliskileri_oku():
        if kid not in (i["a"], i["b"]):
            continue
        diger = i["b"] if i["a"] == kid else i["a"]
        baglar.append({"diger": diger, "tip": i["tip"], "kaynak": i.get("kaynak", ""), "not": i.get("not", "")})
        if diger == ben:
            ben_baglari.append(i["tip"])
    cikarimlar = [r for r in c.cikarimlari_oku() if r["kisi"] == kid or (r["alan"] == "iliski" and _bag_cifti(r["deger"])[1] == kid)]
    metin_beyan = c.sade(" ".join(beyanlar + [str(k.get("kullanici_gorusu") or "")]))
    siklik = k.get("temas_sikligi") if k.get("temas_sikligi") in c.SIKLIK else ""
    rol = c.sade(f"{k.get('rol') or ''} {k.get('kurum') or ''}")
    yakin = bool(set(ben_baglari) & set(YAKIN_BAG)) or bool(_KIZ_ARK.search(rol))
    return {"kid": kid, "ad": k.get("ad") or kid, "var": bool(k), "tur": k.get("tur") or "", "yakinlik": k.get("yakinlik") or "",
            "yakinlik_sen": "sen" in c.sade(k.get("yakinlik_kaynak") or "").split(), "siklik": siklik, "gorus": k.get("kullanici_gorusu") or "",
            "beyanlar": beyanlar, "baglar": baglar, "ben_baglari": ben_baglari, "ben": ben, "yakin_bag": yakin,
            "yakin_ozel": yakin or k.get("tur") == "yakin",  # özel hayat kuralları (özet/etiket) için: partner/akraba ya da tür yakın
            "birlikte_yasiyor": bool(_BIRLIKTE_YASIYOR.search(metin_beyan)), "cikarimlar": cikarimlar}


def bilinen_baglam(kid):
    """İstemlere eklenecek kısa metin: kişi için kesin bilinenler ve bunlardan çıkan 'sorma' kuralları."""
    g = baglam_yapisi(kid)
    if not g["var"]:
        return ""
    def ad(x):
        k2 = c.kisi_oku(os.path.join(c.KISILER, x + ".md")) if c.gecerli_id(x) and os.path.exists(os.path.join(c.KISILER, x + ".md")) else None
        return (k2 or {}).get("ad", x)
    s = [f"{g['ad']} ({kid}): tür {g['tur']}, yakınlık {g['yakinlik']}" + (" (KULLANICI belirledi)" if g["yakinlik_sen"] else "")]
    if g["ben_baglari"]:
        s.append("Kullanıcıyla bağ: " + ", ".join(dict.fromkeys(g["ben_baglari"])))
    if g["siklik"]:
        s.append(f"Görüşme sıklığı (KULLANICI BEYANI): {c.SIKLIK[g['siklik']][1]}")
    if g["gorus"]:
        s.append(f"Kullanıcının görüşü: {g['gorus']}")
    for b in g["beyanlar"][:6]:
        s.append(f"Beyan: {b}")
    diger = [f"{b['tip']} {ad(b['diger'])}" for b in g["baglar"] if b["diger"] != g["ben"]]
    if diger:
        s.append("Kayıtlı bağları: " + "; ".join(diger[:8]))
    onayli = [f"{c.CIKARIM_TURLERI.get(r['alan'], r['alan'])}: {r['deger']}" + (f" → {r['yanit']}" if r["yanit"] else "")
              for r in g["cikarimlar"] if r["durum"] in ("onaylandi", "duzeltildi") and r["kisi"] == kid][:6]
    if onayli:
        s.append("Kullanıcının onayladığı/yanıtladığı: " + " | ".join(onayli))
    yasak = []
    if g["yakin_bag"] or g["siklik"] in ("gunluk", "haftalik") or g["birlikte_yasiyor"]:
        yasak.append("temas sıklığı, kanalı, birebir/grup yazışması, 'ne sıklıkla/en son ne zaman' soruları")
    if g["yakin_bag"]:
        yasak.append("yakınlık puanı önerisi, 'tanışıyorlar mı' soruları, ev içi/ilişki dinamiği/alışkanlık etiketleri ve özetleri")
    if yasak:
        s.append("BU KİŞİ İÇİN ÜRETME: " + "; ".join(yasak) + ".")
    return "\n".join(s)


def kesin_bilinenler_blogu(kimlikler):
    """Birden çok kişi için istem bloğu (boşsa 'yok')."""
    parcalar = [t for t in (bilinen_baglam(k) for k in dict.fromkeys(kimlikler)) if t]
    if not parcalar:
        return "KESİN BİLİNENLER: ağda henüz kayıt yok."
    return ("KESİN BİLİNENLER — bunlarla cevaplanmış ya da çelişen soru/öneri ÜRETME (kullanıcı söyledi ya da ağda kayıtlı; "
            "soruyu bu bilgiyle zaten yanıtlayabiliyorsan sorma):\n" + "\n---\n".join(parcalar))


def onceki_kararlar(kid):
    """c.onceki_kararlar gibi; ek olarak bağlamla çelişip kapatılan önerileri 'tekrar önerme' diye verir."""
    out = []
    for r in c.cikarimlari_oku():
        if r["kisi"] != kid or r["durum"] == "bekliyor":
            continue
        ad = c.CIKARIM_TURLERI.get(r["alan"], r["alan"])
        if r["durum"] == KAPANDI:
            out.append(f"KAPATILDI, bilinen bağlamla çelişiyordu, TEKRAR ÖNERME ({ad}): {r['deger']}")
        elif r["durum"] == "reddedildi":
            out.append(f"REDDETTİ ({ad}): {r['deger']}")
        elif r["durum"] == "duzeltildi":
            out.append(f"DÜZELTTİ ({ad}): '{r['deger']}' değil, '{r['yanit']}'")
        elif r["alan"] == "soru":
            out.append(f"CEVAPLADI: {r['deger']} → {r['yanit']}")
    return out


# ---------- kural tabanlı kapı ----------
def _karar_satirlari(g, oneri):
    """Aynı kişinin (ve bağ ise karşı kişinin) bekleyen olmayan kararları; öneri kendisi sayılmaz."""
    no = str(oneri.get("no") or "")
    return [r for r in g["cikarimlar"] if r["durum"] != "bekliyor" and r["no"] != no]


def etiket_suz(deger):
    """'a, b, c' etiket listesini -> (kalan meşru etiketler, elenen hobi/günlük yaşam etiketleri)."""
    kalan, elenen = [], []
    for e in (x.strip() for x in re.split(r"[,;]", str(deger or ""))):
        if not e:
            continue
        sd = c.sade(e)
        hobi = any(_HOBI.match(w) for w in sd.split()) and not _MESLEKI.search(sd)
        (elenen if hobi else kalan).append(e)
    return kalan, elenen


def _bilinen_ozet(g):
    """Gerekçelerde kullanılacak genel ifade: özel hayat ayrıntısını çoğaltmaz (örn. 'partner, günlük görüşme')."""
    parca = list(dict.fromkeys(g["ben_baglari"] if g["yakin_bag"] else []))
    if g["yakin_bag"] and not parca:
        parca.append("yakın")
    if g["siklik"] or g["birlikte_yasiyor"]:
        parca.append({"gunluk": "günlük", "haftalik": "haftalık", "aylik": "aylık"}.get(g["siklik"], "günlük") + " görüşme")
    return ", ".join(parca) or "bilinen bağlam"


def celisiyor_mu(oneri, baglam):
    """oneri: {kisi, alan, deger, gerekce?, no?}; baglam: baglam_yapisi() sözlüğü (ya da kişi id'si). -> (bool, gerekçe)"""
    g = baglam if isinstance(baglam, dict) else baglam_yapisi(baglam)
    alan, deger = oneri.get("alan"), str(oneri.get("deger") or "")
    sd = c.sade(deger)
    yakin = g["yakin_bag"]
    yakin_ozel = g.get("yakin_ozel", yakin)
    gunluk = g["siklik"] in ("gunluk", "haftalik") or g["birlikte_yasiyor"]

    # (a) temas sıklığı / kanalı soruları
    if alan == "soru":
        if (yakin or gunluk) and _TEMAS.search(sd):
            return True, f"kullanıcı beyanıyla cevaplanmış ({_bilinen_ozet(g)}): sıklık/kanal sorusu gereksiz"
        if yakin and _TANISMA.search(sd):
            return True, f"tanışıklık sorusu gereksiz: kullanıcıyla bağı {'/'.join(dict.fromkeys(g['ben_baglari'])) or 'yakın'}"

    # (b) yakınlık önerisi
    if alan == "yakinlik":
        if g["yakinlik_sen"]:
            return True, "yakınlığı kullanıcı kendisi belirledi"
        if yakin:
            return True, f"kullanıcıyla bağı {'/'.join(dict.fromkeys(g['ben_baglari'])) or 'yakın'}: yakınlık puanı önerisi anlamsız"

    # (e) hobi / günlük yaşam etiketi (herkes için, AGENTS.md): hepsi elenirse öneri kapanır; bir kısmı kalırsa
    # filtrele() kalanlarla geçirir, kuyrugu_temizle() eskisini kapatıp kalanlarla yenisini ekler.
    if alan == "etiketler":
        kalan, elenen = etiket_suz(deger)
        if elenen and not kalan:
            return True, "günlük yaşam/hobi etiketi: etiket sayılmaz"
        sd_ozel = c.sade(" ".join(kalan))  # özel hayat taraması yalnız kalan (meşru) etiketlere bakar
    else:
        sd_ozel = sd

    # (e2) özel hayat ayrıntısı (partner / yakın aile / yakın tür)
    if yakin_ozel and alan in ("ozet", "etiketler", "hakkinda"):
        if _OZEL.search(sd_ozel) or (alan != "etiketler" and _OZEL.search(c.sade(oneri.get("gerekce") or ""))):
            return True, "özel hayat ayrıntısı: yakın kişiler için yazılmaz"
    if alan == "ozet":
        if yakin_ozel and _HOBI_METIN.search(sd):
            return True, "özet gereksiz: özel hayat/hobi ayrıntısı içeriyor"
        if (yakin or gunluk) and _OZET_TEKRAR.search(sd):
            return True, f"özet gereksiz: kullanıcı beyanını tekrar ediyor ({_bilinen_ozet(g)})"

    # (c) aynı çift için daha güçlü bağ varken daha zayıf bağ; (d) bağ tekrarı
    if alan == "iliski":
        tip, hedef = _bag_cifti(deger)
        if tip in GUC and hedef:
            mevcut = [(b["tip"], "kayıtlı bağ") for b in g["baglar"] if b["diger"] == hedef]
            bekleyen = []  # aynı çift için bekleyen öneriler: yalnız 'daha güçlü bağ' sayılır (iki eşit bekleyen birbirini kapatmasın)
            for kd in c.cikarimlari_oku():
                if kd["alan"] == "iliski" and str(kd["no"]) != str(oneri.get("no") or ""):
                    if kd["durum"] in ("onaylandi", "duzeltildi"):
                        t2, h2 = _bag_cifti(kd["deger"] if kd["durum"] == "onaylandi" else (kd["yanit"] or kd["deger"]))
                        if {kd["kisi"], h2} == {oneri.get("kisi"), hedef}:
                            mevcut.append((t2, f"onaylı öneri #{kd['no']}"))
                    elif kd["durum"] == "bekliyor":
                        t2, h2 = _bag_cifti(kd["deger"])
                        if {kd["kisi"], h2} == {oneri.get("kisi"), hedef}:
                            bekleyen.append((t2, f"bekleyen öneri #{kd['no']}"))
            guclu = [(t, k) for t, k in mevcut + bekleyen if GUC.get(t, 0) > GUC[tip]]
            if guclu:
                return True, f"bu çift için daha güçlü {guclu[0][0]} bağı var ({guclu[0][1]}); {tip} daha zayıf"
            esit = [(t, k) for t, k in mevcut if t == tip]
            if esit:
                return True, f"{tip} bağı zaten biliniyor ({esit[0][1]})"
        for r in _karar_satirlari(g, oneri):
            if r["alan"] != "iliski":
                continue
            t2, h2 = _bag_cifti(r["deger"])
            if t2 == tip and {r["kisi"], h2} == {oneri.get("kisi"), hedef}:
                return True, f"aynı bağ daha önce {r['durum']} (#{r['no']})"
        return False, ""

    # (d) aynı/çok benzer öneri daha önce onaylandı, reddedildi ya da kapatıldı
    esik = 0.6 if alan == "soru" else 0.85
    for r in _karar_satirlari(g, oneri):
        if r["kisi"] != oneri.get("kisi") or r["alan"] != alan:
            continue
        if sd == c.sade(r["deger"]) or _benzerlik(deger, r["deger"]) >= esik:
            if r["durum"] == "onaylandi" or (r["durum"] == "duzeltildi" and alan == "soru"):
                return True, f"aynı öneri/soru zaten yanıtlandı (#{r['no']})" + (f": {r['yanit']}" if r["yanit"] else "")
            return True, f"çok benzer öneri daha önce {r['durum']} (#{r['no']})"
    return False, ""


def filtrele(oneriler):
    """Önerileri kural kapısından geçirir. -> (geçenler, elenenler[{oneri, gerekce}]).
    Etiket önerisinde hobi/günlük yaşam etiketleri süzülür; meşru etiket kalırsa öneri yalnız kalanlarla geçer."""
    onbellek, gecen, elenen = {}, [], []
    for o in oneriler:
        kid = o.get("kisi")
        if kid not in onbellek:
            onbellek[kid] = baglam_yapisi(kid) if kid else {"kid": "", "var": False, "siklik": "", "ben_baglari": [], "baglar": [], "cikarimlar": [],
                                                              "yakin_bag": False, "yakin_ozel": False, "birlikte_yasiyor": False, "yakinlik_sen": False}
        sonuc, gerekce = celisiyor_mu(o, onbellek[kid])
        if sonuc:
            elenen.append({"oneri": o, "gerekce": gerekce})
            continue
        if o.get("alan") == "etiketler":
            kalan, atilan = etiket_suz(o.get("deger"))
            if atilan and kalan:
                o = dict(o, deger=", ".join(kalan))
        gecen.append(o)
    return gecen, elenen


# ---------- kuyruk temizliği ----------
def kuyrugu_temizle(kid=None):
    """Bekleyen çıkarımları tarar; çelişen/cevaplanmış olanları SİLMEZ, durumunu 'kapandi' yapıp yanıta gerekçeyi yazar.
    Etiket önerisinde yalnız bir kısmı hobi/günlük yaşam ise öneri kapatılır, kalan meşru etiketlerle yeni öneri eklenir.
    -> {"incelenen": n, "kapanan": [{no, kisi, alan, deger, gerekce, kaynak}], "yeni": n}"""
    satirlar = c.cikarimlari_oku()
    adaylar = [r for r in satirlar if r["durum"] == "bekliyor" and (kid is None or r["kisi"] == kid)
               and os.path.exists(os.path.join(c.KISILER, r["kisi"] + ".md"))]
    baglamlar = {k: baglam_yapisi(k) for k in {r["kisi"] for r in adaylar}}  # tek anlık görüntü: bu turda kapananlar birbirini etkilemez
    kapanan, yeniler = {}, []
    for r in adaylar:
        sonuc, gerekce = celisiyor_mu(r, baglamlar[r["kisi"]])
        if sonuc:
            kapanan[r["no"]] = gerekce
        elif r["alan"] == "etiketler":
            kalan, atilan = etiket_suz(r["deger"])
            if atilan and kalan:
                kapanan[r["no"]] = "günlük yaşam/hobi etiketi etiket sayılmaz; meşru etiketlerle yeni öneri eklendi"
                yeniler.append({"kisi": r["kisi"], "alan": "etiketler", "deger": ", ".join(kalan), "gerekce": r.get("gerekce", ""), "kaynak": r["kaynak"]})
    sonuc = []
    for r in satirlar:
        if r["no"] in kapanan and r["durum"] == "bekliyor":
            r["durum"] = KAPANDI
            r["yanit"] = KAPANIS_ONEKI + kapanan[r["no"]]
            sonuc.append({"no": r["no"], "kisi": r["kisi"], "alan": r["alan"], "deger": r["deger"], "gerekce": kapanan[r["no"]], "kaynak": r["kaynak"]})
    if sonuc:
        c.cikarimlari_yaz(satirlar)
    eklenen = c.cikarim_ekle(yeniler) if yeniler else 0
    return {"incelenen": len(adaylar), "kapanan": sonuc, "yeni": eklenen}
