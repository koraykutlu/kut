"""Kut başlatıcı: kut/ klasörünü yola ekleyip sunucuyu açar. Çift tıkla (pythonw) ya da `py -3 kut.pyw [--veri KLASÖR]`."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "kut"))
import ag_sunucu  # noqa: E402

if __name__ == "__main__":
    ag_sunucu.main()
