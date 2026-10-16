"""Kut icin KALABALIK ama tamamen KURGUSAL sentetik ag uretir (harita okunurlugu denemesi).

Kullanim:
    py -3 demo/kalabalik_veri.py --kisi 400 --hedef KLASOR   # 400 sahte kisi, yogun iliskili
    py -3 kut.pyw --veri KLASOR --tarayicisiz --port 47391

Adlar rastgele birlestirilmis sahte ad+soyaddir (gercek kisiyle ilgisi yok); tohum sabit oldugu icin her kosuda ayni ag cikar.
Gercek veri klasorune yazilmaz: hedef verilmezse gecici klasor kullanilir.
"""
import argparse
import os
import random
import sys
import tempfile
from datetime import date, timedelta

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
sys.path.insert(0, KOK)
import ag_cekirdek as c  # noqa: E402

ADLAR = ["Alp", "Bora", "Cem", "Defne", "Ece", "Fırat", "Gül", "Hakan", "Irmak", "Jale", "Kaan", "Lale", "Mina", "Naz", "Oya", "Pınar",
         "Rüya", "Sinan", "Tuna", "Umay", "Vedat", "Yaren", "Zeki", "Aras", "Beren", "Ceren", "Deniz", "Elif", "Güney", "Hira"]
SOYADLAR = ["Kurgunoğlu", "Örnekçi", "Sahteli", "Denemeci", "Yapaycan", "Hayalbay", "Maketoğlu", "Uydurmaz", "Taslakçı", "Demolu",
            "Kurmaca", "Sanalcı", "Hayali", "Örneksel", "Gölgeli", "Bulutlu", "Rüzgârlı", "Dumanlı"]
DAGILIM = [("yakin", .10, (2, 3)), ("cevre", .16, (0, 2)), ("akademi", .24, (0, 2)), ("is", .24, (0, 3)), ("finans", .08, (0, 1)),
           ("siyaset", .08, (0, 1)), ("etkinlik", .10, (0, 1))]
BEN = {"ad": "Deniz Demo", "kurum": "Kurgu Teknoloji", "rol": "Deneme", "asistan": "Kut"}


def uret(hedef, n, tohum=7):
    rnd = random.Random(tohum)
    hedef = os.path.abspath(hedef)
    os.makedirs(hedef, exist_ok=True)
    c.veri_klasoru(hedef)
    c.ben_yaz(dict(BEN, foto=""))
    ids, turde, kullanilan = [], {}, set()
    bugun = date.today()
    for i in range(n):
        r, acc = rnd.random(), 0
        for tur, oran, (y0, y1) in DAGILIM:
            acc += oran
            if r <= acc:
                break
        for _ in range(50):
            ad = f"{rnd.choice(ADLAR)} {rnd.choice(SOYADLAR)}"
            if ad not in kullanilan:
                break
        else:
            ad = f"{ad} {i}"
        kullanilan.add(ad)
        kid = c.slug(ad)
        yak = rnd.randint(y0, y1)
        alanlar = {"ad": ad, "tur": tur, "kurum": f"Kurgu {tur.title()} {rnd.randint(1, 9)}", "rol": "Sahte", "yakinlik": str(yak), "foto": ""}
        if yak >= 1 or rnd.random() < .5:
            alanlar["son_temas"] = (bugun - timedelta(days=rnd.randint(2, 200))).isoformat()
        c.kisi_yaz(kid, alanlar, c.yeni_govde(ad, "kurgusal sentetik veri", []))
        ids.append(kid)
        turde.setdefault(tur, []).append(kid)
    tipler = ["tanisiyor", "arkadas", "birlikte-calisiyor", "is-ortagi", "mentor"]
    il, goruldu = [], set()

    def ekle(a, b, t):
        if a == b or (a, b) in goruldu or (b, a) in goruldu:
            return
        goruldu.add((a, b))
        il.append({"a": a, "b": b, "tip": t, "not": "", "kaynak": "sentetik", "tarih": bugun.isoformat()})

    for grup in turde.values():                # küme içi yoğun bağlar
        for kid in grup:
            for _ in range(3):
                ekle(kid, rnd.choice(grup), rnd.choice(tipler))
    for _ in range(n // 2):                    # kümeler arası bağlar
        ekle(rnd.choice(ids), rnd.choice(ids), "tanisiyor")
    c.iliskileri_yaz(il)
    return hedef, len(il)


def main():
    p = argparse.ArgumentParser(description="Kut icin kalabalik sentetik ag uretir.")
    p.add_argument("--kisi", type=int, default=150)
    p.add_argument("--hedef")
    a = p.parse_args()
    h, m = uret(a.hedef or tempfile.mkdtemp(prefix="kut-kalabalik-"), a.kisi)
    print(h, a.kisi, "kisi,", m, "bag")


if __name__ == "__main__":
    main()
