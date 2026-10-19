"""MCP sunucusu (ag_mcp): protokol, salt okur araçlar ve kişi kapısı. Kurgusal adlar; veri geçici klasörde (_yalitim)."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut"))
import ag_cekirdek as c  # noqa: E402
import ag_mcp as m  # noqa: E402

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUN = (date.today() - timedelta(days=1)).strftime("%d.%m.%Y")
ESKI = (date.today() - timedelta(days=200))


def _kisi(kid, on, govde=""):
    with open(os.path.join(c.KISILER, f"{kid}.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("---\n" + "\n".join(f"{k}: {v}" for k, v in on.items()) + "\n---\n" + govde)


class MCPTest(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(c.KISILER, ignore_errors=True)
        os.makedirs(c.KISILER)
        with open(c.HARIC, "w", encoding="utf-8") as f:
            f.write(c.HARIC_SABLON + "\n- Kurgu Partisi\n")
        _kisi("deniz-demo", {"ad": "Deniz Demo", "tur": "is", "kurum": "Kuzeyova Üniversitesi", "rol": "Araştırmacı", "yakinlik": 3,
                             "telefon": "[05550000000]", "eposta": "deniz@ornek.test", "son_temas": ESKI.isoformat()},
              f"# Deniz Demo\n\n## Temas\n- {DUN} · yüz yüze · Kahve içtik; Mert Kurgusal da oradaydı\n- {DUN} · e-posta · Taslak gönderdi\n\n"
              "## Sözler\n- [ ] 2026-01-01 · ben → o · Makaleyi okuyup döneceğim\n")
        _kisi("selin-hoca", {"ad": "Selin Hoca", "tur": "akademi", "kurum": "Kuzeyova Üniversitesi", "yakinlik": 1, "son_temas": "2020-01-01"},
              "# Selin Hoca\n\n## Temas\n- 01.01.2020 · e-posta · Eski yazışma\n")
        _kisi("mert-kurgusal", {"ad": "Mert Kurgusal", "tur": "yakin", "kurum": "Kuzeyova Üniversitesi", "yakinlik": 3, "remote_allowed": "false"},
              f"# Mert Kurgusal\n\n## Temas\n- {DUN} · telefon · Gizli kalmalı\n")
        _kisi("ayla-kurgu", {"ad": "Ayla Kurgu", "tur": "siyaset", "kurum": "Kurgu Partisi", "yakinlik": 2},
              f"# Ayla Kurgu\n\n## Temas\n- {DUN} · yüz yüze · Miting\n")

    def cagir(self, ad, **arg):
        return m.isle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": ad, "arguments": arg}})["result"]

    def metin(self, ad, **arg):
        r = self.cagir(ad, **arg)
        self.assertFalse(r["isError"], r)
        return r["content"][0]["text"]

    def test_baslatma_ve_liste(self):
        r = m.isle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})["result"]
        self.assertEqual(r["protocolVersion"], "2025-03-26")
        self.assertEqual(r["serverInfo"]["name"], "kut")
        self.assertIsNone(m.isle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        araclar = m.isle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertEqual({a["name"] for a in araclar}, set(m.ISLEV))
        self.assertTrue(all(a["annotations"]["readOnlyHint"] for a in araclar))
        self.assertEqual(m.isle({"jsonrpc": "2.0", "id": 3, "method": "yok"})["error"]["code"], -32601)

    def test_kapali_ve_haric_kisi_hic_gorunmez(self):
        for ad, arg in (("kisi_ara", {"sorgu": "kuzeyova"}), ("son_gorusmeler", {"gun": 30}), ("bu_hafta", {}),
                        ("kisi_karti", {"id": "deniz-demo"}), ("brifing", {"id": "deniz-demo"})):
            t = self.metin(ad, **arg)
            self.assertNotIn("Mert", t, ad)
            self.assertNotIn("Ayla", t, ad)
        for kid in ("mert-kurgusal", "ayla-kurgu", "../ben", "yok-boyle"):
            self.assertTrue(self.cagir("kisi_karti", id=kid)["isError"], kid)
            self.assertTrue(self.cagir("brifing", id=kid)["isError"], kid)

    def test_iletisim_bilgisi_verilmez(self):
        t = self.metin("kisi_karti", id="deniz-demo") + self.metin("brifing", id="deniz-demo")
        self.assertNotIn("0555", t)
        self.assertNotIn("deniz@ornek.test", t)

    def test_kart_ara_son_gorusmeler(self):
        self.assertIn("deniz-demo", self.metin("kisi_ara", sorgu="deniz"))
        self.assertEqual(self.metin("kisi_ara", sorgu="zzz"), "Eşleşen kişi yok.")
        kart = self.metin("kisi_karti", id="deniz-demo")
        self.assertIn("Taslak gönderdi", kart)
        self.assertIn("Makaleyi okuyup döneceğim", kart)
        son = self.metin("son_gorusmeler", gun=7)
        self.assertIn("Taslak gönderdi", son)
        self.assertNotIn("Eski yazışma", son)
        self.assertTrue(self.cagir("son_gorusmeler", gun="x")["isError"])

    def test_bu_hafta_ihmal_ve_soz(self):
        t = self.metin("bu_hafta")
        self.assertIn("Selin Hoca", t)   # yakınlık 1, yıllardır temas yok
        self.assertIn("Makaleyi", t)     # gecikmiş söz

    def test_stdio_dongusu(self):
        girdi = io.BytesIO(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n\nbozuk\n'
                           b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        cikti = io.BytesIO()
        eski = sys.stdout
        try:
            m.main(girdi, cikti)
        finally:
            sys.stdout = eski
        satirlar = [json.loads(x) for x in cikti.getvalue().decode("utf-8").splitlines()]
        self.assertEqual(satirlar[0], {"jsonrpc": "2.0", "id": 1, "result": {}})
        self.assertEqual(satirlar[1]["error"]["code"], -32700)
        self.assertEqual(len(satirlar), 2)

    def test_giris_noktasi_alt_surec(self):
        istek = "\n".join(json.dumps(x) for x in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "kisi_ara", "arguments": {"sorgu": "selin"}}})) + "\n"
        p = subprocess.run([sys.executable, os.path.join(DEPO, "kut.pyw"), "--mcp", "--veri", c.VERI], input=istek.encode("utf-8"),
                           capture_output=True, timeout=60)
        satirlar = [json.loads(x) for x in p.stdout.decode("utf-8").splitlines()]
        self.assertEqual(len(satirlar), 2, p.stderr.decode("utf-8", "replace"))
        self.assertIn("selin-hoca", satirlar[1]["result"]["content"][0]["text"])
        yok = subprocess.run([sys.executable, os.path.join(DEPO, "kut.pyw"), "--mcp", "--veri", os.path.join(c.VERI, "yok")],
                             input=b"", capture_output=True, timeout=60)
        self.assertEqual(yok.returncode, 2)
        self.assertFalse(os.path.exists(os.path.join(c.VERI, "yok")))


if __name__ == "__main__":
    unittest.main()
