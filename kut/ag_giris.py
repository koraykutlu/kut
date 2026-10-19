"""Kut giriş noktası: `kut.pyw` ve PyInstaller `Kut.exe` buradan başlar.

İki iş yapar:
  * Sunucu: `ag_sunucu.main()` (tarayıcı penceresi, kısayol, `--veri`, `--port`, `--tarayicisiz`).
  * Zamanlanmış özet: `--ozet [--veri X] [--sessiz]` → `ag_bildirim.calistir` (özeti üretir, gerekiyorsa bildirir). Sunucu, tarayıcı ve gereksiz
    modüller hiç yüklenmez. Görev Zamanlayıcı/launchd/systemd bu komutu çalıştırır (yalnız kullanıcı Ayarlar'dan açınca kurulur).
  * MCP sunucusu: `--mcp --veri X` → `ag_mcp.main` (stdio, salt okur). Yapay zekâ istemcisi bu komutu kendisi başlatır; sunucu ve tarayıcı açılmaz,
    taşınmış `--veri` klasörü yeniden yaratılmaz.

Veri klasörü: `ag_cekirdek` içe aktarılınca kendiliğinden bir veri iskeleti kurar. `--veri` verilmişse bu, içe aktarmadan ÖNCE `AGIM_VERI`'ye
çevrilir ki varsayılan klasörde (`<depo>/veri`) istenmeyen bir iskelet oluşmasın. Zamanlanmış görevde klasör artık yoksa (taşınmış/silinmiş)
hiçbir iskelet kurulmaz (`KUT_ISKELETSIZ`): görev kodu 2 ile çıkar, eski yol sessizce yeniden yaratılmaz.
"""
import os
import sys


def veri_yolu(argv):
    """`--veri X` ya da `--veri=X`; yoksa ''."""
    for i, a in enumerate(argv):
        if a == "--veri" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--veri="):
            return a[len("--veri="):]
    return ""


def ortam_hazirla(argv, ozet):
    """ag_cekirdek içe aktarılmadan önce çağrılır (ortam değişkenleri içe aktarma anında okunur)."""
    veri = veri_yolu(argv)
    if not veri:
        return
    if ozet and not os.path.isdir(veri):
        os.environ["KUT_ISKELETSIZ"] = "1"
    else:
        os.environ["AGIM_VERI"] = os.path.abspath(veri)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    ozet = "--ozet" in argv[1:]
    mcp = "--mcp" in argv[1:]
    ortam_hazirla(argv[1:], ozet or mcp)
    if mcp:
        if os.environ.get("KUT_ISKELETSIZ"):
            print("Kut MCP: veri klasörü bulunamadı.", file=sys.stderr)
            return 2
        import ag_mcp
        return ag_mcp.main()
    if ozet:
        import ag_bildirim
        return ag_bildirim.calistir(argv)
    import ag_sunucu
    ag_sunucu.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
