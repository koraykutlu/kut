"""Ağın ortak çekirdeği: kişi dosyaları, ilişkiler, hariç listesi, dikkat (çıkar çatışması) kuralları.

Kaynak her zaman Markdown, veri klasöründe: ben.md (merkezdeki kişi), kisiler/*.md, iliskiler.md (tablo), haric.md, yorumlar/*.md.
Kod (bu klasör) ile veri ayrıdır: varsayılan veri klasörü <kod>/veri, başka yer için veri_klasoru(yol).
ag_uret.py (statik görünüm) ve ag_sunucu.py (kut.pyw ile açılan, düzenlenebilir yerel sunucu) bunu kullanır.
"""
import base64
import contextlib
import json
import math
import os
import re
import shutil
import sys
import unicodedata
from datetime import date, datetime

import ag_sir

KOK = os.path.dirname(os.path.abspath(__file__))
DONDURULDU = bool(getattr(sys, "frozen", False))   # PyInstaller .exe: salt okunur varlıklar geçici açılım klasöründe (_MEIPASS)
VARLIK = getattr(sys, "_MEIPASS", KOK)
DEPO = os.path.dirname(KOK)   # depo kökü (kaynaktan çalışırken): kut/ bir üstü


def varsayilan_veri():
    """Kaynaktan çalışınca <depo>/veri; .exe'de geçici klasör değil, Belgelerim/Kut (--veri verilmişse onu, boşuna kurmaz)."""
    if not DONDURULDU:
        return os.path.join(DEPO, "veri")
    if "--veri" in sys.argv[:-1]:
        return sys.argv[sys.argv.index("--veri") + 1]
    return os.path.join(os.path.expanduser("~"), "Documents", "Kut")


def veri_klasoru(yol):
    """Tüm veri yollarını verilen klasöre çevirir; yoksa iskeletini kurar."""
    global VERI, KISILER, FOTO, YORUMLAR, ARSIV, ILISKILER, HARIC, BEN_DOSYA, CIKARIMLAR, BELGELER
    VERI = os.path.abspath(yol)
    KISILER = os.path.join(VERI, "kisiler")
    FOTO = os.path.join(VERI, "foto")
    YORUMLAR = os.path.join(VERI, "yorumlar")
    ARSIV = os.path.join(VERI, "arsiv")
    ILISKILER = os.path.join(VERI, "iliskiler.md")
    HARIC = os.path.join(VERI, "haric.md")
    BEN_DOSYA = os.path.join(VERI, "ben.md")
    CIKARIMLAR = os.path.join(VERI, "cikarimlar.md")
    BELGELER = os.path.join(VERI, "belgeler")
    for d in (KISILER, FOTO, YORUMLAR):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(HARIC):
        with open(HARIC, "w", encoding="utf-8", newline="\n") as f:
            f.write(HARIC_SABLON)
    if not os.path.exists(ILISKILER):
        iliskileri_yaz([])


HARIC_SABLON = """# Hariç tutulanlar

İletişim kurmak istemediğin kurum/parti adlarını aşağıya "- " ile yaz. Kişinin `kurum`, `parti` veya `rol` alanında
geçen kişiler hiçbir öneriye ("Bu hafta", içe aktarma) girmez ve kırmızı halkayla işaretlenir.

## Liste
"""

TURLER = {
    "ben": ("Ben", "#D4A72C"),
    "yakin": ("Yakın", "#D6537F"),
    "cevre": ("Çevre", "#7A8599"),
    "akademi": ("Akademi", "#8A5CD6"),
    "etkinlik": ("Etkinlik", "#E08A2E"),
    "finans": ("Finans", "#2E9E6A"),
    "is": ("İş", "#1BA3A3"),
    "siyaset": ("Siyaset", "#3B6FD9"),
}
# ilişki tipi: (etiket, renk, yönlü mü, kategori)  kategori: notr | pozitif | bagimli | negatif
TIPLER = {
    "tanisiyor": ("Tanışıyor", "#8b93a5", False, "notr"),
    "arkadas": ("Arkadaş", "#4CAF7A", False, "pozitif"),
    "birlikte-calisiyor": ("Birlikte çalışıyor", "#1BA3A3", False, "pozitif"),
    "mentor": ("Mentoru (A → B)", "#8A5CD6", True, "pozitif"),
    "yonetici": ("Yöneticisi (A → B)", "#3B6FD9", True, "bagimli"),
    "is-ortagi": ("İş ortağı", "#2E9E6A", False, "bagimli"),
    "asistan": ("Asistanı (A → B)", "#5B8DEF", True, "bagimli"),
    "hocasi": ("Hocası (A → B)", "#B07A3C", True, "bagimli"),
    "akraba": ("Akraba", "#C27BD6", False, "bagimli"),
    "partner": ("Partner", "#D6537F", False, "bagimli"),
    "rakip": ("Rakip", "#E0832E", False, "negatif"),
    "gerginlik": ("Gerginlik / anlaşmazlık", "#D64545", False, "negatif"),
}
WA_ALANLARI = ["wa_sohbetler", "wa_mesaj", "wa_oturum", "wa_baslatma", "wa_cevap_dk", "wa_cevap_ben_dk", "wa_son90", "wa_onceki90", "wa_ilk", "wa_son"]
ALAN_SIRASI = ["ad", "aliases", "foto", "tur", "kurum", "rol", "alan", "etiketler", "nereden", "yakinlik", "telefon", "eposta", "x",
               "linkedin", "instagram", "dogum_gunu", "son_temas", "temas_sikligi", "kullanici_gorusu", "yakinlik_kaynak", "sonraki_adim", "sonraki_tarih", "neden_onemli", "ne_verebilirim",
               "ozellikler", "ozellik_kaynak"] + WA_ALANLARI
LISTE_ALANLARI = {"aliases", "dersler", "alan", "nereden", "telefon", "etiketler", "ozellikler", "wa_sohbetler"}
# Kişi özellikleri: 0–10, asistan kanıtla doldurur, kullanıcı düzenler. Hassas kategori (siyasi görüş, din, sağlık, etnik köken,
# cinsel yönelim) ve "zaaf" bilerek yok.
OZELLIKLER = [
    ("uzmanlik", "Uzmanlık", "Alanında bilgi ve beceri derinliği"),
    ("etki", "Etki", "Çevresi, konumu, kapı açabilme gücü"),
    ("ulasilabilirlik", "Ulaşılabilirlik", "Ne kadar kolay ulaşılır, ne hızlı döner"),
    ("destek", "Destek", "Yardım etme, fikir ve fırsat paylaşma eğilimi"),
    ("guvenilirlik", "Güvenilirlik", "Sözünü tutma, tutarlılık"),
    ("uyum", "Uyum", "Senin hedef ve ilgi alanlarınla örtüşme"),
]
# Özellik ölçütleri: her puan bandı gözlenebilir bir davranış ya da konuma bağlı. Asistan istemi, puan denetimi ve sayfadaki
# kaydırıcı aynı tabloyu kullanır. Puan kişinin değerini değil, gözlenen davranışını ve konumunu (senin bağlamında) ölçer.
OLCUTLER = {
    "uzmanlik": {
        "kanit": "unvan/rol, eğitim düzeyi, yayın/proje, resmi özgeçmiş, işini kendi gözünle görmen",
        "sayilmaz": "hobi, ev becerisi, genel kültür, kendini tanıtması tek başına",
        "bantlar": [(0, 2, "Alan dışı ya da alanında hiç deneyimi yok"), (3, 4, "Öğrenci / yeni başlayan; temel bilgi, ilk projeler"),
                    (5, 6, "Alanında çalışan ya da ileri öğrenci; bağımsız iş çıkarır"),
                    (7, 8, "Deneyimli uzman; başkalarına öğretir ya da yönetir, somut çıktıları var"),
                    (9, 10, "Alanında tanınan otorite (kıdemli akademisyen, yayınları, sektörde bilinen isim)")]},
    "etki": {
        "kanit": "konum/unvan, yönettiği ekip ya da kurum, tanıştırma yapması, karar vericilere erişimi, kitlesi",
        "sayilmaz": "sosyal ortamda aktif olmak, etkinlik ya da oyun daveti başlatmak (bu ulaşılabilirlik/destek), popüler görünmek",
        "bantlar": [(0, 2, "Kendi yakın çevresi dışında erişimi yok"), (3, 4, "Kendi okul/arkadaş çevresinde tanıştırabilir"),
                    (5, 6, "Bir kurum ya da topluluk içinde tanınır, oradaki kişilere erişimi var (kulüp yöneticisi, asistan)"),
                    (7, 8, "Karar verici ya da karar vericilere doğrudan erişimi var (hoca, yönetici, kurucu)"),
                    (9, 10, "Sektör ya da kamu düzeyinde kapı açar (üst yönetici, vekil, tanınmış yatırımcı)")]},
    "ulasilabilirlik": {
        "kanit": "cevap süresi (WhatsApp ölçümü), görüşme sıklığı, yüz yüze erişim, senin beyanın",
        "sayilmaz": "başkalarına ne kadar ulaşılabilir olduğu",
        "bantlar": [(0, 2, "Ulaşılamıyor ya da aracı gerekiyor"), (3, 4, "Resmi kanaldan, birkaç günde döner"),
                    (5, 6, "Mesajla ulaşılır, 1–2 günde döner"), (7, 8, "Aynı gün döner, kolayca görüşülür"),
                    (9, 10, "Her gün görüşüyorsunuz ya da hemen döner")]},
    "destek": {
        "kanit": "sana yaptığı somut yardım, tanıştırma, fırsat paylaşma, isteğine olumlu yanıt",
        "sayilmaz": "nezaket; başkalarına yaptığı yardım tek başına (en çok 5–6'yı destekler)",
        "bantlar": [(0, 2, "İsteklere olumsuz ya da karşılıksız"), (3, 4, "Sorulunca kısa yanıt, kendiliğinden yardım yok"),
                    (5, 6, "İstenince yardım eder (en az 1 örnek)"), (7, 8, "Kendiliğinden yardım ya da fırsat paylaşır (2+ örnek)"),
                    (9, 10, "Emek ve zaman isteyen konularda tekrar tekrar yanında (farklı türde birden çok örnek)")]},
    "guvenilirlik": {
        "kanit": "verdiği sözü tutması ya da tutmaması, zamanında dönmesi, sırrı saklaması",
        "sayilmaz": "izlenim, sempati",
        "bantlar": [(0, 2, "Birden çok tutulmamış söz"), (3, 4, "Tutarsız; bazen tutar"),
                    (5, 6, "Bilinen sözünü tuttu (1 örnek) ya da birlikte iş yaptınız ve sorun olmadı"),
                    (7, 8, "Birden çok sözünü zamanında tuttu"), (9, 10, "Uzun süredir (6 ay+) ve önemli işlerde istisnasız tutarlı")]},
    "uyum": {
        "kanit": "ortak alan/etiket, ortak proje, aynı hedef (profilindeki ilgi alanlarına göre)",
        "sayilmaz": "kişisel yakınlık, sevgi; yalnız aynı okulda olmak",
        "bantlar": [(0, 2, "Ortak alan yok"), (3, 4, "Bir ortak ilgi, yüzeysel"),
                    (5, 6, "Bir ortak alanda ikiniz de aktifsiniz (aynı bölüm, topluluk, konu)"),
                    (7, 8, "Birden çok ortak alan ya da birlikte yapılan bir proje"),
                    (9, 10, "Aynı hedef üzerinde düzenli birlikte çalışıyorsunuz")]},
}
OLCUT_KURALLARI = [
    "Kanıt yoksa puan yok: '—' bilinmiyor demektir, düşük demek değildir.",
    "Puan, bandın koşulu tam karşılanınca verilir; iki bant arasında kalırsa alttaki.",
    "7 ve üstü en az 2 ayrı kanıt ister; 9–10 en az 2 farklı kaynak ister (ör. senin beyanın + resmi kaynak ya da ölçüm). "
    "Asistan tek bir kaynaktan (bir sohbet, bir belge) en çok 8 verebilir.",
    "Kanıt, ölçtüğü özelliğe uymalı (ör. davet başlatmak 'etki' değil, 'ulaşılabilirlik' kanıtıdır).",
    "Yakınlık puanı şişirmez: partner ya da yakın arkadaş olmak uzmanlık ya da etki puanını artırmaz.",
    "Aynı ölçüt herkese: puan kişinin değerini değil, senin bağlamındaki davranışını ve konumunu ölçer.",
]
YAKINLIK_OLCUT = ["0 · Tanımıyor (hedef): hiç birebir temas yok",
                  "1 · Yazıştık: en az bir birebir mesaj ya da e-posta; yüz yüze görüşme yok ya da tek seferlik",
                  "2 · Görüştük: yüz yüze ya da sesli birebir görüşme oldu; ara sıra temas",
                  "3 · Güçlü: düzenli (ayda bir ya da daha sık) birebir temas ve karşılıklı güven/yardım geçmişi"]
# nereden alanında çevre değil kanal olan değerler: köprü puanında sayılmaz
KANAL_NEREDEN = {"whatsapp", "rehber", "telefon", "linkedin", "instagram", "x", "eposta", "e posta", "mail"}


def olcut_bandi(anahtar, puan):
    for alt, ust, metin in OLCUTLER.get(anahtar, {}).get("bantlar", []):
        if alt <= puan <= ust:
            return metin
    return ""


def olcut_metni():
    """Asistan istemlerine giren ölçüt tablosu (yakınlık + özellikler + kurallar)."""
    s = ["Yakınlık (0–3):"] + ["  " + y for y in YAKINLIK_OLCUT] + ["Özellikler (0–10), bantlar:"]
    for a, ad, ac in OZELLIKLER:
        o = OLCUTLER[a]
        s.append(f"  {a} ({ad}: {ac}). Kanıt: {o['kanit']}. Sayılmaz: {o['sayilmaz']}.")
        s += [f"    {alt}–{ust}: {m}" for alt, ust, m in o["bantlar"]]
    s.append("Kurallar:")
    s += [f"  - {k}" for k in OLCUT_KURALLARI]
    return "\n".join(s)


# İlişki puanları: 0–100, verilerden otomatik hesaplanır (açıklama = hesaplama yöntemi).
ILISKI_PUANLARI = [
    ("sicaklik", "Sıcaklık", "Son temastan bu yana geçen gün, yakınlığa göre üstel azalır (yakınlık 3: ~30 günde %37'ye iner). Beyan ettiğin görüşme sıklığı son temas sayılır."),
    ("derinlik", "Derinlik", "Yakınlık × 25 + kayıtlı temas başına 5 (temastan en çok 25)."),
    ("karsiliklilik", "Karşılıklılık", "WhatsApp'ta konuşmaları başlatma dengesi: %50–%50 = 100, hep bir taraf = 0. Ölçüm yoksa boş."),
    ("sureklilik", "Süreklilik", "İlk ve son temas arası ay × 6 + 20; son 90 günde temas yoksa ×0,6."),
    ("kopru", "Köprü", "Kişinin bulunduğu farklı çevre sayısı (kanal adları sayılmaz) ve ağdaki bağlarının çevreleri."),
    ("ortak_zemin", "Ortak zemin", "Alan/etiketlerinden ilgi alanlarınla örtüşen her biri 34 puan."),
]
IHMAL_GUN = {3: 14, 2: 30, 1: 60}
# Kullanıcı beyanı: kayıt tutulmasa da ne sıklıkla görüşüldüğü. Puanlarda son temas en az bu kadar yeni sayılır.
SIKLIK = {"gunluk": (1, "Her gün (birlikte yaşıyor / aynı ortam)"), "haftalik": (7, "Haftada bir ya da daha sık"),
          "aylik": (30, "Ayda bir civarı")}
BEN_VARSAYILAN = {"id": "ben", "ad": "Ben", "kurum": "", "rol": "Merkez", "foto": "", "asistan": "Claude",
                  "temas_basligi": "Temas", "yorum_yolu": "veri/yorumlar", "ilgiler": [], "karakter": "", "okul": "", "dersler": [], "dogum_gunu": ""}
BEN_ALANLARI = list(BEN_VARSAYILAN)


def ben():
    """Merkezdeki kişi (ben.md). id bir kez belirlenir; ilişkilerde bu id kullanılır."""
    b = dict(BEN_VARSAYILAN)
    if os.path.exists(BEN_DOSYA):
        b.update({k: v for k, v in (kisi_oku(BEN_DOSYA) or {}).items() if v not in ("", None)})
    b.update({"tur": "ben", "alan": [], "nereden": [], "yakinlik": 3})
    return b


def ben_yaz(alanlar):
    b = ben()
    b.update({k: alanlar[k] for k in BEN_ALANLARI if k in alanlar and k != "id"})
    yaz = lambda v: "[" + ", ".join(_temiz(x).replace(",", " ") for x in v if _temiz(x)) + "]" if isinstance(v, list) else _temiz(v)
    satirlar = [f"{k}: {yaz(b.get(k))}".rstrip() for k in BEN_ALANLARI]
    with open(BEN_DOSYA, "w", encoding="utf-8", newline="\n") as f:
        f.write("---\n" + "\n".join(satirlar) + "\n---\n# Ben\n\nAğın merkezi. `id` ilişkilerde kullanılır, değiştirme. "
                "`asistan`: yorum yapan yapay zekâ ajanının adı. `temas_basligi`: kişi dosyalarındaki temas bölümünün adı.\n")


def ben_id():
    return ben()["id"]

_TR = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")


def sade(s):
    """Karşılaştırma için: küçük harf, Türkçe karakter ve aksansız, yalnız harf/rakam/boşluk."""
    s = (s or "").replace("İ", "i").replace("I", "ı").lower().translate(_TR)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def slug(ad):
    return re.sub(r"\s+", "-", sade(ad)) or "kisi"


def bos_slug(ad):
    t, i = slug(ad), 2
    while os.path.exists(os.path.join(KISILER, t + ".md")) or t == ben_id():
        t = f"{slug(ad)}-{i}"; i += 1
    return t


# ---------- kişi dosyaları ----------
def _deger(v):
    v = v.split("  #")[0].strip()
    if v.startswith("[") and v.endswith("]"):
        return [x.strip() for x in v[1:-1].split(",") if x.strip()]
    return v


def kisi_oku(yol):
    metin = open(yol, encoding="utf-8").read().replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", metin, re.S)
    if not m:
        return None
    alanlar = {}
    for satir in m.group(1).splitlines():
        if ":" in satir and not satir.startswith(" "):
            k, v = satir.split(":", 1)
            alanlar[k.strip()] = _deger(v)
    for k in TURETILEN:  # her yazışta Kut alanlarından yeniden üretilir; ikinci kopya tutulmaz
        alanlar.pop(k, None)
    alanlar["govde"] = m.group(2).strip()
    return alanlar


TURETILEN = ("kind", "title", "facts")
FACTS_ALANLARI = ("kurum", "rol", "son_temas")
HAYIR = ("false", "hayir", "no", "0", "off")


def uzak_kapali_mi(alanlar):
    """Kişi kartındaki '🔒 Bu kişi yapay zekâya gönderilmez' (remote_allowed: false)."""
    return str(alanlar.get("remote_allowed", "")).strip().lower() in HAYIR


def _temiz(v):
    return re.sub(r"\s+", " ", str(v or "")).replace("  #", " #").strip()


def kisi_yaz(kid, alanlar, govde):
    # Beyin kişi notu biçimi (beyin entegrasyonu): kind/title/facts ikinci beynin araması içindir, Kut alanlarından türetilir.
    satirlar = ["kind: person", f"title: {_temiz(alanlar.get('ad'))}".rstrip()]
    # Yapay zekâya kapalı kişi ikinci beynin otomatik bağlamına da girmez: beyin yalnız `visibility: private`'ı tanır, remote_allowed'ı değil.
    gorunurluk = "private" if uzak_kapali_mi(alanlar) else _temiz(alanlar.get("visibility"))
    if gorunurluk:
        satirlar.append(f"visibility: {gorunurluk}")
    anahtarlar = ALAN_SIRASI + [k for k in alanlar if k not in ALAN_SIRASI and k not in ("govde", "id", "visibility") + TURETILEN]
    for k in anahtarlar:
        if k not in alanlar and k not in ("ad", "tur", "yakinlik"):
            continue
        v = alanlar.get(k, "")
        if k in LISTE_ALANLARI or isinstance(v, list):
            if not isinstance(v, list):
                v = [x for x in re.split(r"[,;]", str(v)) if x.strip()]
            v = "[" + ", ".join(_temiz(x).replace(",", " ").replace("[", "(").replace("]", ")") for x in v if _temiz(x)) + "]"
        else:
            v = _temiz(v)
            if v.startswith("["):
                v = "(" + v[1:]
        satirlar.append(f"{k}: {ag_sir.temizle(v, 'kişi alanı', entropi=False)}".rstrip())   # sır kapısı: içe aktarılan/model metni sır taşıyamaz
    facts = [(k, _temiz(alanlar.get(k))) for k in FACTS_ALANLARI if not isinstance(alanlar.get(k), list) and _temiz(alanlar.get(k))]
    if facts:
        satirlar += ["facts:"] + [f"  {k}: {v.lstrip('[')}" for k, v in facts]
    os.makedirs(KISILER, exist_ok=True)
    with open(os.path.join(KISILER, kid + ".md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("---\n" + "\n".join(satirlar) + "\n---\n" + ag_sir.temizle(govde, "kişi notu", entropi=False).strip() + "\n")


def yeni_govde(ad, kaynak, temas_satirlari=()):
    temas = "\n".join(f"- {t}" for t in temas_satirlari) or "- (henüz yok)"
    return f"# {ad}\n\nKaynak: {kaynak}\n\n## {ben()['temas_basligi']}\n{temas}\n"


def temas_ekle(govde, satir):
    """Temas bölümünün ('## ... temas') sonuna satır ekler (yoksa bölümü açar)."""
    satirlar = govde.split("\n")
    bas = next((i for i, l in enumerate(satirlar) if re.match(r"^## .*temas\s*$", l.strip(), re.I)), None)
    if bas is None:
        return govde.rstrip() + f"\n\n## {ben()['temas_basligi']}\n- {satir}\n"
    son = next((i for i in range(bas + 1, len(satirlar)) if satirlar[i].startswith("## ")), len(satirlar))
    bolum = [l for l in satirlar[bas + 1:son] if "(henüz yok)" not in l]
    while bolum and not bolum[-1].strip():
        bolum.pop()
    return "\n".join(satirlar[:bas + 1] + bolum + [f"- {satir}", ""] + satirlar[son:]).rstrip() + "\n"


def bolume_ekle(govde, baslik, satir):
    """'## <baslik>' bölümünün sonuna satır ekler (yoksa bölümü açar)."""
    satirlar = govde.split("\n")
    bas = next((i for i, l in enumerate(satirlar) if l.strip().lower() == f"## {baslik}".lower()), None)
    if bas is None:
        return govde.rstrip() + f"\n\n## {baslik}\n- {satir}\n"
    son = next((i for i in range(bas + 1, len(satirlar)) if satirlar[i].startswith("## ")), len(satirlar))
    bolum = satirlar[bas + 1:son]
    while bolum and not bolum[-1].strip():
        bolum.pop()
    return "\n".join(satirlar[:bas + 1] + bolum + [f"- {satir}", ""] + satirlar[son:]).rstrip() + "\n"


def bolum_oku(govde, baslik):
    m = re.search(rf"(?ms)^## {re.escape(baslik)}[^\n]*\n(.*?)(?=^## |\Z)", govde or "")
    return m.group(1).strip() if m else ""


def kisileri_oku(uyarilar=None):
    uyarilar = [] if uyarilar is None else uyarilar
    kisiler = []
    if not os.path.isdir(KISILER):
        return kisiler
    for ad in sorted(os.listdir(KISILER)):
        if not ad.endswith(".md") or ad.startswith("_"):
            continue
        k = kisi_oku(os.path.join(KISILER, ad))
        if not k:
            uyarilar.append(f"{ad}: frontmatter yok, atlandı")
            continue
        k["id"] = ad[:-3]
        if k.get("tur") not in TURLER or k.get("tur") == "ben":
            uyarilar.append(f"{ad}: bilinmeyen tur '{k.get('tur')}', 'cevre' sayıldı")
            k["tur"] = "cevre"
        try:
            k["yakinlik"] = max(0, min(3, int(k.get("yakinlik") or 0)))
        except ValueError:
            k["yakinlik"] = 0
        for liste in ("alan", "nereden", "telefon", "baglantilar"):
            if not isinstance(k.get(liste), list):
                k[liste] = [k[liste]] if k.get(liste) else []
        kisiler.append(k)
    return kisiler


def foto_kaydet(kid, ham):
    tip = "png" if ham[1:4] == b"PNG" else "jpg"
    os.makedirs(FOTO, exist_ok=True)
    for eski in ("png", "jpg"):
        p = os.path.join(FOTO, f"{kid}.{eski}")
        if eski != tip and os.path.exists(p):
            os.replace(p, os.path.join(FOTO, f"{kid}.{eski}.eski"))
    with open(os.path.join(FOTO, f"{kid}.{tip}"), "wb") as f:
        f.write(ham)
    return f"foto/{kid}.{tip}"


FOTO_AZAMI = 8_000_000
FOTO_UZANTI = (".png", ".jpg", ".jpeg")


def foto_yolu(yol):
    """frontmatter 'foto:' değerini FOTO klasörünün içindeki gerçek dosyaya çözer; `../`, mutlak yol, sembolik bağ ya da
    resim dışı uzantıyla dışarı kaçan değer için None."""
    if not yol or not isinstance(yol, str) or "\x00" in yol:
        return None
    try:
        kok = os.path.realpath(FOTO)
        tam = os.path.realpath(os.path.join(VERI, yol))
        if os.path.commonpath([kok, tam]) != kok or tam == kok:
            return None
    except ValueError:   # farklı sürücü / geçersiz yol
        return None
    if os.path.splitext(tam)[1].lower() not in FOTO_UZANTI or not os.path.isfile(tam) or os.path.getsize(tam) > FOTO_AZAMI:
        return None
    return tam


def foto_veri(yol):
    tam = foto_yolu(yol)
    if not tam:
        return ""
    with open(tam, "rb") as f:
        ham = f.read()
    if not (ham[:3] == b"\xff\xd8\xff" or ham[1:4] == b"PNG"):
        return ""
    tip = "png" if ham[1:4] == b"PNG" else "jpeg"
    return f"data:image/{tip};base64," + base64.b64encode(ham).decode()


# ---------- ilişkiler ----------
ILISKI_BASLIK = """# Kişiler arası ilişkiler

Kim kimi nasıl tanıyor. `a` ve `b` kişi dosya adları (ben.md'deki `id` = sen). Yönlü tiplerde (mentor, yonetici, asistan, hocasi) A → B okunur:
A, B'nin mentoru / yöneticisi / asistanı / hocasıdır.
Tipler: tanisiyor · arkadas · birlikte-calisiyor · mentor · yonetici · is-ortagi · asistan · hocasi · akraba · partner · rakip · gerginlik.
Not kısa ve olgusal: dedikodu, sağlık, zaaf yazılmaz. Ağ sayfasından (Ağım → kişi → İlişki ekle) veya elle düzenlenir.

| a | b | tip | not | kaynak | tarih |
|---|---|---|---|---|---|
"""


def iliskileri_oku():
    if not os.path.exists(ILISKILER):
        return []
    sonuc = []
    for satir in open(ILISKILER, encoding="utf-8"):
        if not satir.startswith("|"):
            continue
        h = [x.strip() for x in satir.strip().strip("|").split("|")]
        if len(h) < 3 or h[0] in ("a", "") or set(h[0]) <= set("-: "):
            continue
        h += [""] * (6 - len(h))
        sonuc.append({"a": h[0], "b": h[1], "tip": h[2] if h[2] in TIPLER else "tanisiyor",
                      "not": h[3], "kaynak": h[4], "tarih": h[5]})
    return sonuc


def iliskileri_yaz(iliskiler):
    temiz = lambda s: _temiz(s).replace("|", "/")
    govde = ILISKI_BASLIK + "".join(
        f"| {temiz(i['a'])} | {temiz(i['b'])} | {temiz(i['tip'])} | {temiz(i.get('not'))} | {temiz(i.get('kaynak'))} | {temiz(i.get('tarih'))} |\n"
        for i in iliskiler)
    with open(ILISKILER, "w", encoding="utf-8", newline="\n") as f:
        f.write(govde)


# ---------- puanlama ----------
def ozellik_oku(k):
    """'ozellikler: [uzmanlik=7, etki=5]' → {'uzmanlik': 7, ...}"""
    sonuc = {}
    for x in k.get("ozellikler") or []:
        if "=" in x:
            a, v = x.split("=", 1)
            try:
                sonuc[a.strip()] = max(0, min(10, int(float(v))))
            except ValueError:
                pass
    return sonuc


def _sayi(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _tarih_oku(s):
    try:
        return date.fromisoformat(str(s))
    except ValueError:
        return None


def temas_tarihleri(govde):
    tarihler = []
    for m in re.finditer(r"(?m)^- (\d{2})\.(\d{2})\.(\d{4})", govde or ""):
        try:
            tarihler.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    return tarihler


def etkin_son_temas(k, bugun=None):
    """Kayıtlı son temas ile kullanıcının beyan ettiği görüşme sıklığından yeni olanı. Beyan çıkarımı ve eski veriyi ezer."""
    bugun = bugun or date.today()
    son = _tarih_oku(k.get("son_temas")) if k.get("son_temas") else None
    sik = SIKLIK.get(k.get("temas_sikligi") or "")
    if sik:
        beyan = date.fromordinal(bugun.toordinal() - sik[0])
        son = max(son, beyan) if son else beyan
    return son


def iliski_puanlari(k, komsu_cevreleri, ilgiler, bugun=None):
    """0–100 ilişki puanları; veri yoksa None. '_trend' WhatsApp mesaj eğilimi."""
    bugun = bugun or date.today()
    y = k.get("yakinlik", 0)
    temaslar = temas_tarihleri(k.get("govde"))
    son_temas = etkin_son_temas(k, bugun)
    p = {}
    tau = {3: 30, 2: 45, 1: 75, 0: 60}[y]
    p["sicaklik"] = round(100 * math.exp(-max((bugun - son_temas).days, 0) / tau)) if son_temas else None
    p["derinlik"] = min(100, y * 25 + min(25, len(temaslar) * 5))
    b = _sayi(k.get("wa_baslatma"))
    p["karsiliklilik"] = round(100 - 2 * abs(50 - b)) if b is not None else None
    wa_ilk = _tarih_oku(k.get("wa_ilk")) if k.get("wa_ilk") else None
    tarihler = temaslar + [d for d in (wa_ilk, son_temas) if d]
    if len(tarihler) >= 2 or (tarihler and son_temas):
        ay = (max(tarihler) - min(tarihler)).days / 30
        canli = (bugun - max(tarihler)).days <= 90 or (_sayi(k.get("wa_son90")) or 0) > 0
        p["sureklilik"] = round(min(100, 20 + ay * 6) * (1 if canli else 0.6))
    else:
        p["sureklilik"] = None
    cevre = {x for x in (k.get("nereden") or []) if sade(x) not in KANAL_NEREDEN} | komsu_cevreleri
    p["kopru"] = min(100, max(0, len(cevre) - 1) * 20 + len(komsu_cevreleri) * 10) if cevre else None
    if ilgiler:
        ortak = {sade(x) for x in (k.get("alan") or []) + (k.get("etiketler") or [])} & {sade(x) for x in ilgiler}
        p["ortak_zemin"] = min(100, len(ortak) * 34)
    else:
        p["ortak_zemin"] = None
    s90, o90 = _sayi(k.get("wa_son90")), _sayi(k.get("wa_onceki90"))
    if s90 is not None and o90 is not None and (s90 or o90):
        p["_trend"] = "ısınıyor" if s90 > o90 * 1.3 + 5 else "soğuyor" if s90 < o90 * 0.7 else "sabit"
    return p


def surum_al(kid, sakla=20):
    """Kişi dosyasının yazılmadan önceki halini arsiv/surum/'e kopyalar (son `sakla` kopya kalır); elle geri almak için."""
    yol = os.path.join(KISILER, kid + ".md")
    if not os.path.exists(yol):
        return ""
    hedef = os.path.join(ARSIV, "surum")
    os.makedirs(hedef, exist_ok=True)
    kopya = os.path.join(hedef, f"{kid}-{datetime.now():%Y%m%d-%H%M%S-%f}.md")
    shutil.copyfile(yol, kopya)
    _ozel_yap(kopya)
    eskiler = sorted(f for f in os.listdir(hedef) if re.fullmatch(rf"{re.escape(kid)}-\d{{8}}-\d{{6}}-\d+\.md", f))
    for f in eskiler[:-sakla]:
        os.remove(os.path.join(hedef, f))
    return kopya


# ---- Arşiv bakımı: Kut'un kendi tuttuğu kopyalar süreyle silinir ve ikinci beynin aramasına girmez ----
ARSIV_GUN = 90   # eski kişi sürümleri, çıkarılan kişiler, doğrulama öncesi yedekler, arşivlenmiş ham sohbetler
HAM_GUN = 30     # gelen/whatsapp: analiz bitince hemen silinir; analiz edilmemiş olanlar bu kadar gün sonra
ARSIV_SURELI = ("surum", "cikarilan", "gelen")   # + "yedek-dogrulama-oncesi-*" klasörleri. haric/, hedefler/ kullanıcının kararıdır, dokunulmaz


def _ozel_yap(yol):
    """Arşivdeki .md kopyasına `visibility: private` ekler: eski sürümler ikinci beynin otomatik bağlamına girmez.
    Atomik yazar (geçici dosya + os.replace) ve dosyanın değişme zamanını korur (süre sayacı sıfırlanmaz)."""
    try:
        with open(yol, encoding="utf-8-sig") as f:   # BOM'lu dosya da tanınır; BOM yazılmaz
            metin = f.read()
        st = os.stat(yol)
    except (OSError, UnicodeDecodeError):
        return False
    m = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", metin, re.S)
    if m and re.search(r"(?m)^visibility:\s*private\s*$", m.group(1)):
        return False
    if m:
        ust = re.sub(r"(?m)^visibility:.*\n?", "", m.group(1)).rstrip("\n")
        metin = "---\n" + (ust + "\n" if ust else "") + "visibility: private\n---\n" + metin[m.end():]
    elif metin.startswith("---\n"):   # kapanışı olmayan bozuk frontmatter: alanları gövdeye itmemek için dokunma
        return False
    else:
        metin = "---\nvisibility: private\n---\n" + metin
    gecici = yol + ".ozel-yaz"
    try:
        with open(gecici, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)
        os.utime(gecici, ns=(st.st_atime_ns, st.st_mtime_ns))
        os.replace(gecici, yol)
    except OSError:
        with contextlib.suppress(OSError):
            os.remove(gecici)
        return False
    return True


def _ad_tarihi(ad):
    """Arşiv dosya adındaki tarih (surum: <id>-YYYYMMDD-HHMMSS-..., cikarilan: <id>-YYYYMMDD.md); yoksa None."""
    m = re.search(r"-(\d{8})(?:-\d{6}(?:-\d+)?)?\.[a-z0-9]+$", ad, re.I)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").timestamp()
    except ValueError:
        return None


def _eski_mi(yol, gun, simdi):
    """Yaş, dosya adındaki tarih ile değişme zamanından YENİ olanına göre: taşıma mtime'ı korusa da arşive giriş anı sayılır."""
    try:
        t = os.path.getmtime(yol)
    except OSError:
        return False
    ad_t = _ad_tarihi(os.path.basename(yol))
    return simdi - max(t, ad_t or 0) > gun * 86400


def _arsiv_ici(yol, kok_gercek):
    """Bağlantı (sembolik bağ/junction) değil ve gerçekten arşivin içinde mi? Dışarıdaki dosyalar asla silinmez."""
    if _bag_mi(yol):
        return False
    return os.path.normcase(os.path.realpath(yol)).startswith(kok_gercek + os.sep)


def ham_sil(yol):
    """Analizi biten ham sohbet metnini siler (türetilen kişi, bağ ve temas bilgisi kişi dosyalarında kalır)."""
    try:
        os.remove(yol)
        return True
    except OSError:
        return False


def arsiv_bakimi(simdi=None):
    """Açılışta çalışır: süresi dolan arşiv kopyalarını ve ham sohbetleri siler, kalan arşiv .md'lerini private yapar. Sayıları döndürür."""
    import time
    simdi = simdi or time.time()
    say = {"silinen": 0, "ham": 0, "ozel": 0}
    wa = os.path.join(VERI, "gelen", "whatsapp")
    if os.path.isdir(wa):
        for f in os.listdir(wa):
            yol = os.path.join(wa, f)
            if os.path.isfile(yol) and _eski_mi(yol, HAM_GUN, simdi) and ham_sil(yol):
                say["ham"] += 1
    if not os.path.isdir(ARSIV) or os.path.islink(ARSIV):
        return say
    kok_g = os.path.normcase(os.path.realpath(ARSIV))

    def gez(kok):   # bağlantıları izlemeden, yalnız arşivin içindeki gerçek dosyalar
        for dizin, alt, dosyalar in os.walk(kok, followlinks=False):
            alt[:] = [d for d in alt if _guvenli(lambda: _arsiv_ici(os.path.join(dizin, d), kok_g))]
            for f in dosyalar:
                yol = os.path.join(dizin, f)
                if _guvenli(lambda: _arsiv_ici(yol, kok_g)):
                    yield yol

    for ad in os.listdir(ARSIV):
        kok = os.path.join(ARSIV, ad)
        if not os.path.isdir(kok) or not _guvenli(lambda: _arsiv_ici(kok, kok_g)):
            continue
        m = re.fullmatch(r"yedek-dogrulama-oncesi-(\d{8})-\d{6}", ad)
        if m:
            try:
                yas = (datetime.fromtimestamp(simdi) - datetime.strptime(m.group(1), "%Y%m%d")).days
            except ValueError:   # bozuk tarihli klasör bakımı yarıda kesmez; dokunulmaz
                continue
            if yas > ARSIV_GUN:
                for yol in list(gez(kok)):
                    with contextlib.suppress(OSError):
                        _sil(yol)
                _bos_dizinleri_sil(kok)
                say["silinen"] += 1
        elif ad in ARSIV_SURELI:
            for yol in list(gez(kok)):
                if _eski_mi(yol, ARSIV_GUN, simdi):
                    with contextlib.suppress(OSError):
                        _sil(yol)
                        say["silinen"] += 1
    for yol in list(gez(ARSIV)):
        if yol.endswith(".md") and _ozel_yap(yol):
            say["ozel"] += 1
    return say


def _bag_mi(yol):
    return os.path.islink(yol) or bool(getattr(os.stat(yol, follow_symlinks=False), "st_file_attributes", 0) & 0x400)   # 0x400 = junction/reparse point


def _bos_dizinleri_sil(kok):
    """Boş dizinleri alttan üste ve bağlantı girişlerini (hedeflerine HİÇ inmeden) kaldırır; rmtree/os.walk junction'ı izleyebilir, kullanılmaz."""
    with contextlib.suppress(OSError):
        for e in list(os.scandir(kok)):
            with contextlib.suppress(OSError):
                if _bag_mi(e.path):
                    try:
                        os.unlink(e.path)
                    except OSError:
                        os.rmdir(e.path)   # Windows junction: rmdir bağı kaldırır, hedefe dokunmaz
                elif e.is_dir(follow_symlinks=False):
                    _bos_dizinleri_sil(e.path)
        os.rmdir(kok)   # yalnız boşsa


def _sil(yol):
    """Arşiv dosyasını siler; salt-okunur öznitelikliyse yazılabilir yapıp yeniden dener."""
    try:
        os.remove(yol)
    except PermissionError:
        import stat
        os.chmod(yol, stat.S_IWRITE)
        os.remove(yol)


def _guvenli(f):
    try:
        return f()
    except OSError:
        return False


def kisi_guncelle(kid, alanlar=None, degerlendirme=None, kaynak_adi=None):
    """Asistanın kullandığı güvenli güncelleme: alanları birleştirir, istenirse '## Değerlendirme' bölümünü yeniler."""
    yol = os.path.join(KISILER, kid + ".md")
    k = kisi_oku(yol)
    govde = k.pop("govde")
    for a, v in (alanlar or {}).items():
        if isinstance(v, dict) and a == "ozellikler":
            v = [f"{x}={int(y)}" for x, y in v.items()]
        k[a] = v
    if degerlendirme:
        baslik = f"## Değerlendirme ({kaynak_adi or ben()['asistan']}, {date.today().isoformat()})"
        govde = re.sub(r"\n## Değerlendirme.*?(?=\n## |\Z)", "", govde, flags=re.S).rstrip()
        govde += f"\n\n{baslik}\n{degerlendirme.strip()}\n"
    kisi_yaz(kid, k, govde)


# ---------- hariç listesi ----------
def haric_listesi():
    if not os.path.exists(HARIC):
        return []
    return [sade(l[2:]) for l in open(HARIC, encoding="utf-8") if l.startswith("- ") and l[2:].strip()]


def haric_mi(k, liste=None):
    liste = haric_listesi() if liste is None else liste
    metin = " " + sade(" ".join(str(k.get(a) or "") for a in ("kurum", "parti", "rol"))) + " "
    return any(f" {h} " in metin for h in liste)


# ---------- dikkat: çıkar çatışması ve hassas ilişkiler ----------
def dikkatler(kisiler, iliskiler):
    """Kural tabanlı uyarılar. Yorum değil, işaret: asistanın yorumu yorumlar/<id>.md'de durur."""
    BI = ben_id()
    ad = {k["id"]: k["ad"] for k in kisiler}
    ad[BI] = "Sen"
    yak = {k["id"]: k.get("yakinlik", 0) for k in kisiler}
    yak[BI] = 3
    kat = lambda i: TIPLER[i["tip"]][3]
    etiket = lambda i: TIPLER[i["tip"]][0].split(" (")[0].replace("İ", "i").replace("I", "ı").lower()
    sonuc, gorulen = [], set()

    def ekle(ids, seviye, metin):
        anahtar = (tuple(sorted(ids)), metin)
        if anahtar not in gorulen and all(x in ad for x in ids):
            gorulen.add(anahtar)
            sonuc.append({"kisiler": [x for x in ids if x != BI], "seviye": seviye, "metin": metin})

    komsu = {}
    for i in iliskiler:
        komsu.setdefault(i["a"], []).append((i["b"], i))
        komsu.setdefault(i["b"], []).append((i["a"], i))

    for i in iliskiler:
        a, b = i["a"], i["b"]
        if kat(i) == "negatif":
            if BI in (a, b):
                o = b if a == BI else a
                ekle([o], "yuksek", f"{ad.get(o)} ile aranda: {etiket(i)}. Ondan referans/destek isterken ve ortak çevrede bunu hesaba kat.")
            elif yak.get(a, 0) >= 1 and yak.get(b, 0) >= 1:
                ekle([a, b], "orta", f"{ad.get(a)} – {ad.get(b)} arasında: {etiket(i)}. Birini diğerine referans gösterme, ikisini aynı işe birlikte çağırmadan önce düşün.")
        if kat(i) == "bagimli" and BI not in (a, b):
            ekle([a, b], "dusuk", f"{ad.get(a)} – {ad.get(b)}: {etiket(i)}. Birinin diğeri hakkındaki referansı, oyu veya değerlendirmesi bağımsız sayılmaz.")

    # üçgen: X, A'ya bağlı (pozitif/bağımlı); A, C ile negatif → X'in C hakkındaki görüşü tarafsız olmayabilir
    for i in iliskiler:
        if kat(i) not in ("pozitif", "bagimli"):
            continue
        for x, a in ((i["a"], i["b"]), (i["b"], i["a"])):
            for c, j in komsu.get(a, []):
                if j is i or kat(j) != "negatif" or c == x:
                    continue
                if c == BI:
                    ekle([x, a], "orta", f"{ad.get(x)} – {ad.get(a)}: {etiket(i)}; {ad.get(a)} ile aranda: {etiket(j)}. {ad.get(x)} ile paylaştığın bilgi ve ondan alacağın destek bu bağdan etkilenebilir.")
                elif x == BI:
                    ekle([a, c], "orta", f"Senin {ad.get(a)} ile bağın: {etiket(i)}; {ad.get(a)} – {ad.get(c)}: {etiket(j)}. {ad.get(c)} ile yakınlaşman, {ad.get(a)} tarafından taraf tutma gibi okunabilir.")
                elif yak.get(x, 0) >= 1 and yak.get(c, 0) >= 1:
                    ekle([x, c], "dusuk", f"{ad.get(x)} – {ad.get(a)}: {etiket(i)}; {ad.get(a)} – {ad.get(c)}: {etiket(j)}. {ad.get(x)}, {ad.get(c)} hakkında tarafsız olmayabilir.")

    sira = {"yuksek": 0, "orta": 1, "dusuk": 2}
    return sorted(sonuc, key=lambda d: sira[d["seviye"]])


def bu_hafta(kisiler, bugun=None):
    """Tarihi gelen sonraki adımlar + yakınlığına göre ihmal edilenler + gecikmiş/yaklaşan sözler (`tur: "soz"`, `ag_soz.hatirlatmalar`).
    Hariç kişiler asla girmez. Pusula hamleleri buraya girmez (ayrı bölüm)."""
    import ag_soz   # geç içe aktarma: ag_soz bu modülü kullanır
    bugun = bugun or date.today()
    liste = ag_soz.hatirlatmalar(kisiler, bugun)
    for k in kisiler:
        if k.get("haric"):
            continue
        st = k.get("sonraki_tarih")
        if st:
            try:
                g = (date.fromisoformat(st) - bugun).days
                if g <= 7:
                    liste.append({"id": k["id"], "neden": f"{k.get('sonraki_adim') or 'Sonraki adım'} ({'bugün' if g == 0 else f'{-g} gün gecikti' if g < 0 else f'{g} gün kaldı'})", "oncelik": g})
                    continue
            except ValueError:
                pass
        esik = IHMAL_GUN.get(k.get("yakinlik", 0))
        son = etkin_son_temas(k, bugun)
        if esik and son:
            g = (bugun - son).days
            if g >= esik:
                liste.append({"id": k["id"], "neden": f"{g} gündür temas yok", "oncelik": 30 - g + esik, "ihmal": True})
    return sorted(liste, key=lambda x: x["oncelik"])[:12]


# ---------- çıkarımlar: asistanın önerileri kullanıcı onaylayana kadar kişi dosyasına işlenmez ----------
CIKARIM_BASLIK = """# Asistan çıkarımları

Asistanın (yapay zekâ) kişiler hakkındaki çıkarımları ve soruları. Kullanıcı onaylamadan kişi dosyasına işlenmez.
`durum`: bekliyor · onaylandi · duzeltildi · reddedildi · kapandi (Kut: bilinen bağlamla çelişti). `yanit`: kullanıcının düzelttiği değer ya da cevabı.
Reddedilen ve düzeltilen çıkarımlar sonraki analizde asistana "tekrar önerme" diye verilir. Kullanıcı beyanı her zaman önce gelir.

| no | kisi | alan | deger | gerekce | durum | yanit | kaynak | tarih |
|---|---|---|---|---|---|---|---|---|
"""
CIKARIM_SUTUN = ["no", "kisi", "alan", "deger", "gerekce", "durum", "yanit", "kaynak", "tarih"]
CIKARIM_TURLERI = {"ozet": "Aranızdaki ilişki", "tur": "Tür", "yakinlik": "Yakınlık", "etiketler": "Etiketler", "alan": "Alan",
                   "ozellikler": "Özellik puanları", "iliski": "Kişiler arası bağ", "soru": "Sana sorusu",
                   "hakkinda": "Hakkında", "ozgecmis": "Özgeçmiş", "kurum": "Kurum", "rol": "Rol", "eposta": "E-posta",
                   "linkedin": "LinkedIn", "x": "X hesabı"}
TEK_ALANLAR = ("kurum", "rol", "eposta", "linkedin", "x")  # onaylanınca kişi alanına doğrudan yazılan çıkarımlar
OZGECMIS_BASLIK, HAKKINDA_BASLIK = "Özgeçmiş", "Hakkında"
BEYAN_BASLIK = "Senin beyanların"
ID_KALIP = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")


def gecerli_id(kid):
    return bool(kid) and bool(ID_KALIP.fullmatch(str(kid)))


def cikarimlari_oku():
    if not os.path.exists(CIKARIMLAR):
        return []
    sonuc = []
    for satir in open(CIKARIMLAR, encoding="utf-8"):
        if not satir.startswith("|"):
            continue
        h = [x.strip() for x in satir.strip().strip("|").split("|")]
        if not h or not h[0].isdigit():
            continue
        h += [""] * (len(CIKARIM_SUTUN) - len(h))
        sonuc.append(dict(zip(CIKARIM_SUTUN, h)))
    return sonuc


def cikarimlari_yaz(satirlar):
    temiz = lambda s: _temiz(s).replace("|", "/")
    with open(CIKARIMLAR, "w", encoding="utf-8", newline="\n") as f:
        f.write(CIKARIM_BASLIK + "".join("| " + " | ".join(temiz(r.get(a)) for a in CIKARIM_SUTUN) + " |\n" for r in satirlar))


def cikarim_ekle(yeniler):
    """yeniler: [{kisi, alan, deger, gerekce, kaynak}]. Aynı kişi/alan/değer zaten bekliyorsa ya da reddedildiyse eklenmez."""
    satirlar = cikarimlari_oku()
    var = {(r["kisi"], r["alan"], sade(r["deger"])) for r in satirlar if r["durum"] in ("bekliyor", "reddedildi", "duzeltildi", "kapandi")}
    no = max([int(r["no"]) for r in satirlar] or [0])
    eklenen = 0
    for y in yeniler:
        y = {**y, **{a: ag_sir.temizle(y[a], "çıkarım", entropi=False) for a in ("deger", "gerekce") if isinstance(y.get(a), str)}}   # sır kapısı
        anahtar = (y["kisi"], y["alan"], sade(y.get("deger")))
        if not gecerli_id(y["kisi"]) or y["alan"] not in CIKARIM_TURLERI or not str(y.get("deger") or "").strip() or anahtar in var:
            continue
        # aynı kişi ve alan için eski bekleyen öneri yenisiyle değişir (soru ve bağlar hariç: bunlar çoğul)
        if y["alan"] not in ("soru", "iliski", "ozgecmis", "hakkinda"):
            satirlar = [r for r in satirlar if not (r["kisi"] == y["kisi"] and r["alan"] == y["alan"] and r["durum"] == "bekliyor")]
        no += 1
        satirlar.append({"no": str(no), "kisi": y["kisi"], "alan": y["alan"], "deger": y["deger"], "gerekce": y.get("gerekce", ""),
                         "durum": "bekliyor", "yanit": "", "kaynak": y.get("kaynak", ""), "tarih": date.today().isoformat()})
        var.add(anahtar)
        eklenen += 1
    cikarimlari_yaz(satirlar)
    return eklenen


def cikarim_yanitla(no, karar, yanit=""):
    """karar: onay | duzelt | ret. Onay ve düzeltme kişi dosyasına işlenir; düzeltmede kullanıcının değeri geçerlidir."""
    satirlar = cikarimlari_oku()
    r = next((x for x in satirlar if x["no"] == str(no)), None)
    if not r or r["durum"] != "bekliyor":
        raise ValueError("çıkarım bulunamadı ya da zaten yanıtlandı")
    if karar not in ("onay", "duzelt", "ret"):
        raise ValueError("bilinmeyen karar")
    yanit = _temiz(yanit)
    if karar == "duzelt" and not yanit:
        raise ValueError("düzeltme boş")
    if r["alan"] == "soru" and karar != "ret":
        karar, yanit = "duzelt", yanit or r.get("yanit", "")
        if not yanit:
            raise ValueError("cevap boş")
    if karar != "ret":
        _cikarim_uygula(r, yanit if karar == "duzelt" else r["deger"], karar == "duzelt")
    r["durum"] = {"onay": "onaylandi", "duzelt": "duzeltildi", "ret": "reddedildi"}[karar]
    if r["alan"] == "soru" and karar != "ret":
        r["durum"] = "onaylandi"
    r["yanit"] = yanit
    cikarimlari_yaz(satirlar)
    return r


def _cikarim_uygula(r, deger, kullanici):
    kid = r["kisi"]
    yol = os.path.join(KISILER, kid + ".md")
    if not gecerli_id(kid) or not os.path.exists(yol):
        raise ValueError("kişi bulunamadı")
    k = kisi_oku(yol)
    govde = k.pop("govde")
    bugun = date.today().strftime("%d.%m.%Y")
    alan = r["alan"]
    bol = lambda v: [x.strip() for x in re.split(r"[,;]", v) if x.strip()]
    if alan == "ozet":
        if kullanici:
            k["kullanici_gorusu"] = deger
            govde = bolume_ekle(govde, BEYAN_BASLIK, f"{bugun} · İlişkimiz: {deger} (asistanın çıkarımını düzelttin)")
        else:
            govde = bolume_ekle(govde, "Asistan değerlendirmesi (onayladın)", f"{bugun} · {deger}")
    elif alan == "tur":
        if deger not in TURLER or deger == "ben":
            raise ValueError("bilinmeyen tür")
        k["tur"] = deger
    elif alan == "yakinlik":
        k["yakinlik"] = str(max(0, min(3, int(float(deger)))))
        k["yakinlik_kaynak"] = "sen" if kullanici else f"{r['kaynak'] or 'asistan'} (onayladın)"
    elif alan in ("etiketler", "alan"):
        k[alan] = sorted(set(liste_yap(k.get(alan)) + [re.sub(r"[^a-z0-9-]", "", sade(x).replace(" ", "-")) for x in bol(deger)]) - {""})
    elif alan == "ozellikler":
        oz = {}
        for x in bol(deger):
            if "=" in x and x.split("=")[0].strip() in {o[0] for o in OZELLIKLER}:
                oz[x.split("=")[0].strip()] = max(0, min(10, int(float(x.split("=")[1]))))
        k["ozellikler"] = [f"{a}={v}" for a, v in oz.items()]
        k["ozellik_kaynak"] = "sen" if kullanici else f"{r['kaynak'] or 'asistan'} (onayladın)"
        if r.get("gerekce") and not kullanici:
            govde = re.sub(r"\n## Özellik gerekçeleri.*?(?=\n## |\Z)", "", govde, flags=re.S).rstrip()
            govde += "\n\n## Özellik gerekçeleri (onayladın)\n" + "\n".join(f"- {g.strip()}" for g in r["gerekce"].split(" ; ") if g.strip()) + "\n"
    elif alan == "iliski":
        tip, _, b = deger.partition(" ")
        if tip not in TIPLER or not (gecerli_id(b) and (b == ben_id() or os.path.exists(os.path.join(KISILER, b + ".md")))):
            raise ValueError("bağ geçersiz (tip ya da kişi)")
        iliskiler = [i for i in iliskileri_oku() if not ({i["a"], i["b"]} == {kid, b} and i["tip"] in (tip, "tanisiyor"))]
        iliskiler.append({"a": kid, "b": b, "tip": tip, "not": r.get("gerekce", "")[:80],
                          "kaynak": "sen" if kullanici else f"{r['kaynak'] or 'asistan'} (onayladın)", "tarih": date.today().isoformat()})
        iliskileri_yaz(iliskiler)
    elif alan in TEK_ALANLAR:
        k[alan] = deger
    elif alan == "ozgecmis":
        govde = bolume_ekle(govde, OZGECMIS_BASLIK, f"{deger} · kaynak: {'sen' if kullanici else (r['kaynak'] or 'asistan')}")
    elif alan == "hakkinda":
        govde = bolume_ekle(govde, HAKKINDA_BASLIK, f"{deger} ({'sen' if kullanici else (r['kaynak'] or 'asistan')}, {bugun})")
    elif alan == "soru":
        govde = bolume_ekle(govde, BEYAN_BASLIK, f"{bugun} · Soru: {r['deger']} → {deger}")
    kisi_yaz(kid, k, govde)


def tumunu_onayla(kid):
    """Kişinin bekleyen tüm çıkarımlarını (sorular hariç) onaylar."""
    n = 0
    for r in [x for x in cikarimlari_oku() if x["kisi"] == kid and x["durum"] == "bekliyor" and x["alan"] != "soru"]:
        try:
            cikarim_yanitla(r["no"], "onay")
            n += 1
        except ValueError:
            pass
    return n


# ---------- özgeçmiş: '## Özgeçmiş' bölümünde '- dönem · başlık · ayrıntı · kaynak: X' satırları ----------
def ozgecmis_ekle(kid, donem, baslik, ayrinti=""):
    yol = os.path.join(KISILER, kid + ".md")
    if not gecerli_id(kid) or not os.path.exists(yol):
        raise ValueError("kişi bulunamadı")
    baslik = _temiz(baslik)
    if not baslik:
        raise ValueError("başlık gerekli")
    k = kisi_oku(yol)
    govde = k.pop("govde")
    parca = [_temiz(donem) or "?", baslik] + ([_temiz(ayrinti)] if _temiz(ayrinti) else []) + ["kaynak: sen"]
    kisi_yaz(kid, k, bolume_ekle(govde, OZGECMIS_BASLIK, " · ".join(p.replace("·", "-") for p in parca[:-1]) + " · " + parca[-1]))


def bolum_satir_sil(kid, baslik, sira):
    """'## <baslik>' bölümündeki sira'ncı (0'dan) madde satırını siler (arsiv yerine: satır kısa ve kullanıcı isteğiyle)."""
    yol = os.path.join(KISILER, kid + ".md")
    if not gecerli_id(kid) or not os.path.exists(yol):
        raise ValueError("kişi bulunamadı")
    k = kisi_oku(yol)
    satirlar = k.pop("govde").split("\n")
    bas = next((i for i, l in enumerate(satirlar) if l.strip().lower() == f"## {baslik}".lower()), None)
    if bas is None:
        raise ValueError("bölüm yok")
    maddeler = [i for i in range(bas + 1, len(satirlar)) if satirlar[i].startswith("- ")
                and all(not satirlar[j].startswith("## ") for j in range(bas + 1, i + 1))]
    if not 0 <= int(sira) < len(maddeler):
        raise ValueError("satır yok")
    del satirlar[maddeler[int(sira)]]
    kisi_yaz(kid, k, "\n".join(satirlar))


def belgeler(kid):
    d = os.path.join(BELGELER, kid)
    return sorted(os.listdir(d)) if gecerli_id(kid) and os.path.isdir(d) else []


def liste_yap(v):
    return v if isinstance(v, list) else ([v] if v else [])


def yorum_oku(kid):
    p = os.path.join(YORUMLAR, kid + ".md")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def veri_hazirla(uyarilar=None, foto_gom=True):
    uyarilar = [] if uyarilar is None else uyarilar
    kisiler = kisileri_oku(uyarilar)
    hl = haric_listesi()
    idler = {k["id"] for k in kisiler} | {ben_id()}
    iliskiler = [i for i in iliskileri_oku() if i["a"] in idler and i["b"] in idler]
    # eski 'baglantilar' alanı: iliskiler.md'de yoksa 'tanisiyor' say
    var = {tuple(sorted((i["a"], i["b"]))) for i in iliskiler}
    for k in kisiler:
        for b in k.pop("baglantilar", []):
            if b in idler and tuple(sorted((k["id"], b))) not in var:
                var.add(tuple(sorted((k["id"], b))))
                iliskiler.append({"a": k["id"], "b": b, "tip": "tanisiyor", "not": "", "kaynak": "baglantilar alanı", "tarih": ""})
    for k in kisiler:
        k["haric"] = haric_mi(k, hl)
        if k["haric"]:
            uyarilar.append(f"{k['id']}: hariç listesindeki bir partiyle eşleşiyor (haric.md); önerilere girmez")
        k["x_hesap"] = k.pop("x", "")
        if k.get("foto") and not os.path.exists(os.path.join(VERI, k["foto"])):
            uyarilar.append(f"{k['id']}: foto bulunamadı ({k['foto']})")
            k["foto"] = ""
        k["yorum"] = yorum_oku(k["id"])
    # puanlar: komşuların çevreleri (kanal olmayan ilk 'nereden' etiketi) köprü puanına girer
    ilgiler = ben().get("ilgiler") or []
    ilgiler = ilgiler if isinstance(ilgiler, list) else [ilgiler]
    kmap = {k["id"]: k for k in kisiler}
    for k in kisiler:
        komsu = {i["b"] if i["a"] == k["id"] else i["a"] for i in iliskiler if k["id"] in (i["a"], i["b"])}
        cevreler = {next((x for x in (kmap[o].get("nereden") or []) if sade(x) not in KANAL_NEREDEN), o) for o in komsu if o in kmap}
        k["puan"] = iliski_puanlari(k, cevreler, ilgiler)
        k["ozellik"] = ozellik_oku(k)
    bekleyen = [r for r in cikarimlari_oku() if r["durum"] == "bekliyor" and r["kisi"] in kmap]
    import ag_soz   # geç içe aktarma (ag_soz bu modülü kullanır)
    ag_soz.ozet_ekle(kisiler)
    for k in kisiler:
        k["uzak_kapali"] = "haric" if k["haric"] else "kapali" if uzak_kapali_mi(k) else ""
        k["bekleyen"] = sum(1 for r in bekleyen if r["kisi"] == k["id"])
        k["belgeler"] = belgeler(k["id"])
        e = etkin_son_temas(k)
        k["etkin_son_temas"] = e.isoformat() if e else ""
    merkez = ben()
    merkez["govde"] = ""
    if not os.path.exists(os.path.join(VERI, merkez["foto"] or "-")):
        merkez["foto"] = ""
    if foto_gom:
        for k in [merkez] + kisiler:
            k["foto"] = foto_veri(k.get("foto"))
    return {
        "turler": TURLER, "tipler": TIPLER, "kisiler": [merkez] + kisiler, "iliskiler": iliskiler,
        "ozellik_tanim": OZELLIKLER, "puan_tanim": ILISKI_PUANLARI, "ozellik_olcut": OLCUTLER, "olcut_kurallari": OLCUT_KURALLARI,
        "yakinlik_olcut": YAKINLIK_OLCUT,
        "ben": {k: merkez.get(k, "") for k in BEN_ALANLARI},
        "dikkatler": dikkatler(kisiler, iliskiler), "bu_hafta": _dinlenenleri_cikar(bu_hafta(kisiler)),
        "cikarimlar": bekleyen, "cikarim_turleri": CIKARIM_TURLERI, "siklik": {a: v[1] for a, v in SIKLIK.items()},
        "uretildi": date.today().isoformat(), "uyarilar": uyarilar,
    }


def _dinlenenleri_cikar(liste):
    """"Bu hafta"daki ihmal satırlarından, kullanıcının "Uymuyor/Atla/Ertele" kararıyla dinlendirdiği kişileri çıkarır (ag_sonuc.ayar).
    Kullanıcının kendi koyduğu sonraki adım ve sözler kalır: onlar Kut'un önerisi değil, kullanıcının kaydıdır."""
    if not any(x.get("ihmal") for x in liste):
        return liste
    try:
        import ag_sonuc   # geç içe aktarma: ag_sonuc bu modülü kullanır
        kayitlar = ag_sonuc.oku()
        if not kayitlar:
            return liste
        dinlenen = {x["id"] for x in liste if x.get("ihmal") and ag_sonuc.ayar(x["id"], kayitlar=kayitlar)["bekle_gun"] > 0}
    except Exception:   # sonuç defteri okunamazsa liste olduğu gibi kalır
        return liste
    return [x for x in liste if not (x.get("ihmal") and x["id"] in dinlenen)]


def _js_json(x):
    """Veriyi <script> içine güvenle gömer: '</' ve '<!--' ile betik etiketi kapatılamaz/kaçırılamaz."""
    return json.dumps(x, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")


def sayfa(veri, mod=None, kilit=None):
    """Şablondaki /*VERI*/null, /*MOD*/null, /*KILIT*/null yer tutucularını TEK geçişte doldurur; kullanıcı verisinin
    içindeki yer tutucu benzeri metin yeniden işlenmez."""
    deger = {"VERI": _js_json(veri), "MOD": _js_json(mod), "KILIT": _js_json(kilit)}
    html = open(os.path.join(VARLIK, "ag_sablon.html"), encoding="utf-8").read()
    return re.sub(r"/\*(VERI|MOD|KILIT)\*/null", lambda m: deger[m.group(1)], html)


if not globals().get("DEMO_KAPSULU") and not os.environ.get("KUT_ISKELETSIZ"):   # demo kapsülü (ag_demo.py) gerçek veri klasörünü iskeletlemez; yolunu kendisi verir
    veri_klasoru(os.environ.get("AGIM_VERI") or varsayilan_veri())   # KUT_ISKELETSIZ: zamanlanmış özet, taşınmış --veri klasörünü yeniden yaratmasın (ag_giris.py)
