"""kisiler/*.md + iliskiler.md dosyalarından salt okunur ağ görünümü (ag.html) üretir.

Kullanım: python kut/ag_uret.py [--veri KLASÖR] (PIN kilidi kuruluysa üretmez). Düzenlenebilir görünüm için kut.pyw (Kut kısayolu).
Çıktı tek dosyadır (fotoğraflar gömülü), yalnız bu klasörde kalır; dış kaynak yüklemez, internete bir şey göndermez.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ag_cekirdek as c  # noqa: E402
import ag_kilit as kl  # noqa: E402


def main():
    if "--veri" in sys.argv:
        c.veri_klasoru(sys.argv[sys.argv.index("--veri") + 1])
    if kl.kurulu():   # kilit kuruluyken kilitsiz tam ağ dosyası yazılmaz; eskisi de silinir
        eski = os.path.join(c.VERI, "ag.html")
        if os.path.exists(eski):
            os.remove(eski)
        sys.stdout.reconfigure(encoding="utf-8")
        print("PIN kilidi kurulu: kilitsiz ag.html üretilmez. Kut'u kut.pyw ile aç.", file=sys.stderr)
        return 1
    uyarilar = []
    veri = c.veri_hazirla(uyarilar)
    with open(os.path.join(c.VERI, "ag.html"), "w", encoding="utf-8") as f:
        f.write(c.sayfa(veri))
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"ag.html üretildi: {len(veri['kisiler']) - 1} kişi, {len(veri['iliskiler'])} ilişki, {len(veri['dikkatler'])} dikkat")
    for u in uyarilar:
        print("uyarı:", u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
