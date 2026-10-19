"""Kut sürümü ve sürüm karşılaştırma (anlamsal sürüm: X.Y.Z). Yayın etiketi `vX.Y.Z`; burası ile etiket aynı olmalı."""
import re

SURUM = "1.3.0"
_DESEN = re.compile(r"^v?(\d{1,6})\.(\d{1,6})\.(\d{1,6})$")


def ayristir(s):
    """'v1.2.3' / '1.2.3' → (1, 2, 3); başka biçim (ön sürüm eki dahil) ValueError."""
    m = _DESEN.match(str(s or "").strip())
    if not m:
        raise ValueError("geçersiz sürüm: " + str(s)[:40])
    return tuple(int(x) for x in m.groups())


def karsilastir(a, b):
    """a<b → -1, a==b → 0, a>b → 1."""
    x, y = ayristir(a), ayristir(b)
    return (x > y) - (x < y)


def yeni_mi(aday, simdiki=SURUM):
    return karsilastir(aday, simdiki) > 0
