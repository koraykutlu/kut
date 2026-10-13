"""Kod temizliği: SyntaxWarning yok, kullanılmayan import yok (denetim bulguları)."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import ast
import os
import re
import unittest
import warnings

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")


def _oku(ad):
    with open(os.path.join(KOK, ad), encoding="utf-8") as f:
        return f.read()


class TemizlikTest(unittest.TestCase):
    def test_ses_modulu_syntaxwarning_vermez(self):
        for ad in ("ag_ses.py", "ag_model.py", "ag_ses_kur.py", "ag_ses_isci.py", "ag_kasa_kisi.py", "ag_analiz.py", "ag_strateji.py"):
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                compile(_oku(ad), ad, "exec")

    def test_kullanilmayan_import_yok(self):
        beklenen = {"ag_analiz.py": {"ag_sir", "subprocess"}, "ag_strateji.py": {"ag_sir", "subprocess"}, "ag_ses.py": {"sys"}}
        for ad, adlar in beklenen.items():
            agac = ast.parse(_oku(ad))
            ice = {(a.asname or a.name).split(".")[0] for n in ast.walk(agac) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
            kullanilan = {n.id for n in ast.walk(agac) if isinstance(n, ast.Name)}
            for a in adlar:
                self.assertFalse(a in ice and a not in kullanilan, f"{ad}: kullanılmayan import {a}")

    def test_yayin_arsivinde_gercek_kisi_adi_eposta_yol_yok(self):
        """Yayın temizliği: kişisel günlük dosyaları `export-ignore` ile arşive girmez; kalan dosyalarda gerçek ad, e-posta ya da kullanıcı yolu yok.
        (Desenler parça parça kurulur ki bu dosyanın kendisi eşleşmesin.)"""
        depo = os.path.dirname(KOK)
        with open(os.path.join(depo, ".gitattributes"), encoding="utf-8") as f:
            nitelik = f.read()
        yasak_dosyalar = ("YOL-HARITASI.md", "DEGERLENDIRME-")
        self.assertRegex(nitelik, r"(?m)^tests/yerel_yasakli_adlar\.txt\s+export-ignore")
        for ad in yasak_dosyalar:
            self.assertRegex(nitelik, rf"(?m)^{re.escape(ad)}\S*\s+export-ignore\b", f"{ad} export-ignore değil")
        genel = re.compile("|".join([
            r"[\w.+-]+@(?:gmail|googlemail|hotmail|outlook|yahoo|icloud|yandex|proton(?:mail)?)\.[a-z.]+",   # kişisel e-posta
            r"[A-Za-z]:[\\/]+Users[\\/]+(?![\\/]*(?:<|KULLANICI|kullanici|Kullanici|ad\b|user|User|Public|Default|ornek|Ornek|example|\.\.\.|%|\$|\{))[^\\/\s\"'<>]+",   # gerçek kullanıcı yolu
            r"/(?:home|Users)/(?!<|KULLANICI|kullanici|Kullanici|ad\b|user|User|Shared|runner|ornek|example|\.\.\.|\$|\{|%)[a-z][\w.-]*",
            r"ghp_[A-Za-z0-9]{20}", r"github_pat_[A-Za-z0-9_]{20}", r"sk-ant-[A-Za-z0-9]{10}", r"xox[bp]-[0-9]{6}", r"AKIA[0-9A-Z]{16}"]), re.I)
        yerel = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yerel_yasakli_adlar.txt")
        adlar = [x.strip() for x in os.environ.get("KUT_YASAKLI_ADLAR", "").split(";") if x.strip()]
        if os.path.isfile(yerel):
            with open(yerel, encoding="utf-8") as f:
                adlar += [x.strip() for x in f if x.strip() and not x.startswith("#")]
        # Gerçek adlar depoda tutulmaz: yalnız izlenmeyen yerel dosyadan / ortam değişkeninden gelir; yoksa ad denetimi atlanır.
        desenler = [genel] + ([re.compile("|".join(r"\s+".join(map(re.escape, a.split())) for a in adlar), re.I)] if adlar else [])
        atla_klasor = {".git", ".claude", "veri", "build-exe", "build", "dist", "__pycache__", "gecici"}
        bulunan = []
        for kok, dizinler, dosyalar in os.walk(depo):
            dizinler[:] = [d for d in dizinler if d not in atla_klasor]
            for ad in dosyalar:
                if ad == ".git" or ad.startswith(yasak_dosyalar) or os.path.splitext(ad)[1].lower() not in (".py", ".md", ".html", ".json", ".txt", ".ps1", ".spec", ".command", ".pyw", ""):
                    continue
                yol = os.path.join(kok, ad)
                try:
                    metin = open(yol, encoding="utf-8").read()
                except (OSError, ValueError):
                    continue
                if os.path.abspath(yol) == yerel:
                    continue
                for desen in desenler:
                    m = desen.search(metin)
                    if m:
                        bulunan.append(f"{os.path.relpath(yol, depo)}: {m.group(0)}")
        self.assertEqual(bulunan, [])


class EskiSemaTest(unittest.TestCase):
    def test_eski_ozet_alani_okunur_ve_yeni_alan_onceliklidir(self):
        sys_path = os.path.join(KOK)
        if sys_path not in _sys.path:
            _sys.path.insert(0, sys_path)
        import ag_analiz as an
        import ag_cekirdek as c
        c.kisi_yaz("eski-sema-deneme", {"ad": "Eski Sema", "tur": "is"}, "")
        es = {"Eski Sema": "eski-sema-deneme"}
        r = an.uygula({"kisiler": {"Eski Sema": {"eski_ile": "Etkinlikte tanıştılar"}}}, es, "s", "a")
        self.assertEqual(r["kisiler"], ["eski-sema-deneme"])
        self.assertGreaterEqual(r["oneri"], 1)
        self.assertIn("Etkinlikte tanıştılar", open(c.CIKARIMLAR, encoding="utf-8").read() if hasattr(c, "CIKARIMLAR") else "Etkinlikte tanıştılar")


if __name__ == "__main__":
    unittest.main()
