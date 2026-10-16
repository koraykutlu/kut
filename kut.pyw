"""Kut başlatıcı: kut/ klasörünü yola ekleyip sunucuyu açar. Çift tıkla (pythonw) ya da `py -3 kut.pyw [--veri KLASÖR]`.
`kut.pyw --ozet --veri KLASÖR` zamanlanmış görevin komutudur: haftalık özeti hazırlar ve bildirir, sunucu ya da pencere açmaz."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "kut"))
import ag_giris  # noqa: E402  (ag_sunucu'yu --ozet dışında yükler)

if __name__ == "__main__":
    sys.exit(ag_giris.main())
