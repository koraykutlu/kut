"""Okuldan bağımsız akademik zenginleştirme: OpenAlex (açık API) ve ORCID public API.

Hocanın kurumu, yayın sayısı ve çalışma alanları buradan gelir. İlkeler:
- Varsayılan KAPALI: ayarlar.json → kesif.akademik true olmadan hiçbir istek atılmaz (Ayarlar → Kaynaklar'daki "Akademik profiller" anahtarı).
- Dışarı yalnız hocanın AD SOYADI gider (herkese açık bir akademisyen adı); ağdaki başka hiçbir veri gönderilmez, API anahtarı ya da e-posta kullanılmaz.
- Kişi bazında kapalı olanlar atlanır: haric.md ile eşleşen ya da kişi notunda `remote_allowed: false` ("yapay zekâya gönderilmesin") olan
  kişinin adı hiçbir dış servise gitmez (uzak model kapısıyla aynı kural, ag_kapi).
- Hiçbir şey kişi dosyasına doğrudan yazılmaz: sonuç Doğrula kuyruğuna (ag_cekirdek.cikarim_ekle) öneri olarak düşer. Ad + kurum birlikte
  tek bir adayla eşleşirse "Hakkında" önerisi; ad uyuyor ama kurum uyuşmuyor ya da birden çok aday varsa "emin değilim" sorusu olur.
- Ağ yalnız ag_kaynak._istek üzerinden (SSRF koruması, zaman aşımı, boyut sınırı, istek hızı); yanıtlar 7 gün önbellekte; en çok 20 kişi/çalıştırma.
Model kullanılmaz.
"""
import hashlib
import json
import time
import urllib.parse

import ag_cekirdek as c
import ag_ice_aktar as ia

OPENALEX = "https://api.openalex.org"
ORCID = "https://pub.orcid.org"
AZAMI_KISI = 20
TEKRAR_GUN = 30


def acik():
    """Ayar yoksa KAPALI (yeni kurulum internete çıkmaz)."""
    return (ia.ayarlar().get("kesif") or {}).get("akademik") is True


def _kn():
    import ag_kaynak
    return ag_kaynak


def _json(url, basliklar=None):
    """Önbellekli (7 gün) JSON GET; ana makine yalnız bu modülün iki sabit adresinden biri olabilir."""
    host = urllib.parse.urlparse(url).hostname
    if host not in ("api.openalex.org", "pub.orcid.org"):
        raise OSError("izin verilmeyen adres")
    import ag_okullar as ok
    kn = _kn()

    def getir():
        ham, _ = kn._istek(url, basliklar={"Accept": "application/json", **(basliklar or {})}, zaman=20, azami=2_000_000)
        return json.loads(ham.decode("utf-8", "replace"))
    return ok.onbellekli("akademik-" + hashlib.sha1(url.encode()).hexdigest()[:20], getir, 24 * 7)


def openalex_ara(ad):
    u = OPENALEX + "/authors?" + urllib.parse.urlencode({"search": ad, "per-page": 5,
                                                        "select": "id,display_name,orcid,works_count,cited_by_count,last_known_institutions,topics"})
    return _json(u).get("results") or []


def orcid_ara(ad):
    p = ad.split()
    if len(p) < 2:
        return []
    kac = lambda x: x.replace("\\", "\\\\").replace('"', '\\"')   # Lucene tırnak içi: \ ve " kaçışı (sorgu enjeksiyonu)
    q = f'family-names:"{kac(p[-1])}" AND given-names:"{kac(" ".join(p[:-1]))}"'
    u = ORCID + "/v3.0/expanded-search/?" + urllib.parse.urlencode({"q": q, "rows": 5})
    return [{"orcid": x.get("orcid-id", ""), "ad": f"{x.get('given-names') or ''} {x.get('family-names') or ''}".strip(),
             "kurumlar": x.get("institution-name") or []} for x in (_json(u).get("expanded-result") or [])]


def _ad_ayni(a, b):
    return sorted(c.sade(a).split()) == sorted(c.sade(b).split())


def _kurum_uyar(adlar, kurum_en):
    kurum_en = [k.lower() for k in kurum_en if k]
    return any(k in (a or "").lower() for a in adlar for k in kurum_en)


def alanlar(aday, azami=4):
    """OpenAlex konularından en sık geçen alan/alt alan adları."""
    sayim = {}
    for t in aday.get("topics") or []:
        for ad in ((t.get("subfield") or {}).get("display_name"), (t.get("field") or {}).get("display_name")):
            if ad:
                sayim[ad] = sayim.get(ad, 0) + int(t.get("count") or 1)
    return [a for a, _ in sorted(sayim.items(), key=lambda x: -x[1])[:azami]]


def _ozet(a, kurumlar):
    parca = [f"{a.get('works_count', 0)} yayın"] + ([f"alanlar: {', '.join(alanlar(a))}"] if alanlar(a) else [])
    if a.get("orcid"):
        parca.append("ORCID " + a["orcid"].rsplit("/", 1)[-1])
    if kurumlar:
        parca.append("son kurum: " + ", ".join(kurumlar[:2]))
    return "; ".join(parca)


def degerlendir(ad, kurum_en, oa, orc):
    """Adaylardan karar: {durum: kesin|belirsiz|yok, metin}. oa: OpenAlex yazar listesi, orc: ORCID listesi (ikisi de boş olabilir)."""
    tam = [a for a in oa if _ad_ayni(a.get("display_name") or "", ad)]
    kurumlu = [a for a in tam if _kurum_uyar([(k.get("display_name") or "") for k in a.get("last_known_institutions") or []], kurum_en)]
    orc_tam = [o for o in orc if _ad_ayni(o["ad"], ad)]
    orc_kurumlu = [o for o in orc_tam if _kurum_uyar(o["kurumlar"], kurum_en)]
    if len(kurumlu) == 1:
        a = kurumlu[0]
        kurumlar = [k.get("display_name") for k in a.get("last_known_institutions") or [] if k.get("display_name")]
        not_ = ""
        if a.get("orcid") and any(o["orcid"] == a["orcid"].rsplit("/", 1)[-1] for o in orc_kurumlu):
            not_ = " ORCID kaydındaki kurum da uyuşuyor."
        return {"durum": "kesin", "metin": _ozet(a, kurumlar) + "." + not_}
    if not kurumlu and not tam and len(orc_kurumlu) == 1:
        o = orc_kurumlu[0]
        return {"durum": "kesin", "metin": f"ORCID {o['orcid']}; kurum kaydı: {', '.join(o['kurumlar'][:2])}."}
    adaylar = kurumlu or tam
    if adaylar:
        a = max(adaylar, key=lambda x: x.get("works_count") or 0)
        kurumlar = [k.get("display_name") for k in a.get("last_known_institutions") or [] if k.get("display_name")]
        return {"durum": "belirsiz", "aday_sayisi": len(adaylar),
                "metin": f"{len(adaylar)} aday; en kalabalığı: {_ozet(a, kurumlar)}"}
    return {"durum": "yok", "metin": ""}


def oneriler(kisiler, ay, durum, simdi=None):
    """kisiler: [(kisi_id, ad)]. Doğrula'ya düşecek çıkarım listesi döndürür (kişi dosyasına yazmaz; ağ isteği yapar, kilit dışında çağır).
    durum: ag_kaynak.durum() sözlüğü; 'akademik:<id>' anahtarına son sorgu zamanı yazılır (çağıran kaydeder)."""
    if not acik():
        return []
    simdi = simdi or time.time()
    kurum_en = (ay or {}).get("kurum_en") or []
    cikti, sayac = [], 0
    import ag_kapi
    red = ag_kapi.Kapi().red   # haric / remote_allowed:false / okunamayan kişi dosyası: adı dışarı gitmez
    for kid, ad in kisiler:
        if sayac >= AZAMI_KISI:
            break
        if kid in red:
            continue
        son = durum.get("akademik:" + kid, 0)
        if simdi - (son if isinstance(son, (int, float)) else 0) < TEKRAR_GUN * 86400:
            continue
        sayac += 1
        try:
            oa, orc = openalex_ara(ad), []
            try:
                orc = orcid_ara(ad)
            except (OSError, ValueError):
                pass
        except (OSError, ValueError):
            continue   # API erişilemedi: sonra yeniden denenir (zaman yazılmaz)
        durum["akademik:" + kid] = simdi
        k = degerlendir(ad, kurum_en, oa, orc)
        if k["durum"] == "kesin":
            cikti.append({"kisi": kid, "alan": "hakkinda", "deger": k["metin"], "kaynak": "OpenAlex / ORCID (açık akademik veri)",
                          "gerekce": "Ad ve kurum tek bir akademik kayıtla eşleşti."})
        elif k["durum"] == "belirsiz":
            cikti.append({"kisi": kid, "alan": "soru", "kaynak": "OpenAlex / ORCID (açık akademik veri)",
                          "deger": f"Açık akademik kayıtlarda '{ad}' adıyla {k['metin']}. Emin değilim: bu kayıt senin hocana mı ait?",
                          "gerekce": "Ad uyuyor ama kurum eşleşmedi ya da birden çok aday var."})
    return cikti
