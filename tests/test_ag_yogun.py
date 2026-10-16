"""Kalabalık ağ haritası: yerleşim ve etiket seçimi saf işlevleri (node varsa gerçekten çalıştırılır) ve şablonda eşik/davranış güvenceleri.
Arayüz testleri şablon metnine bakar; tarayıcı gerekmez."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
SABLON = os.path.join(KOK, "ag_sablon.html")
BASLA = "// ---- yoğun ağ: yerleşim ve etiket seçimi"
BITIR = "// ---- graf ----"


def sablon():
    with open(SABLON, encoding="utf-8") as f:
        return f.read()


def saf_kod():
    h = sablon()
    return h[h.index(BASLA):h.index(BITIR)]


class YogunSablonTest(unittest.TestCase):
    def test_esik_ve_kademeli_devreye_girme(self):
        h = sablon()
        self.assertIn("const YOGUN_ESIK = 48;", h)
        self.assertIn("const YOGUN = kisiler.length >= YOGUN_ESIK", h)
        self.assertIn("const dugumOlcegi = n => n < YOGUN_ESIK ? 1 :", h)   # az kişili ağda kare boyutu bugünkü gibi
        # az kişili ağda eski kuvvet yerleşimi: yoğun dal yalnız YOGUN iken ve odak dışında
        self.assertIn("if (YOGUN && !ODAK) return radialAdim();", h)
        self.assertIn("if (!YOGUN) [145, 210, 275, 340].forEach", h)   # eski sabit halkalar yalnız az kişili ağda
        self.assertIn('$("z-duzen").hidden = !YOGUN;', h)

    def test_yeni_kenar_ve_kume_katmani(self):
        h = sablon()
        self.assertIn('<g id="kumeler"></g><g id="kenarlar"></g><g id="dugumler"></g>', h)   # tur adımı hedefi #dugumler yerinde
        self.assertIn(".kenar.seyrek.on{", h)
        self.assertIn("body.uzak .kume-yay", h)
        # hareket azaltılmışsa yeni geçişler kapanır, yerleşim anında oturur
        self.assertRegex(h, r"@media \(prefers-reduced-motion:reduce\)\{\.kume-yay,#dugumler,\.dugum \.ad,\.kenar\{transition:none!important\}\}")
        self.assertIn("const f = AZALT ? 1 : .2;", h)

    def test_dis_kaynak_eklenmedi(self):
        saf = saf_kod()
        self.assertNotRegex(saf, r"https?://|fetch\(|import\(|<script")

    def test_surukleme_ve_sifirlama_korunur(self):
        h = sablon()
        self.assertIn("if (YOGUN && surukle.oynadi) k.elle = true;", h)   # sürüklenen kişi elle işaretlenir, yerleşim ezmez
        self.assertIn("k.elle || k.hx === undefined", h)
        self.assertIn("ODAK_KAYIT", h)   # odak çıkışı konumları geri yükler


class YogunSafIslevTest(unittest.TestCase):
    def calistir(self, govde):
        node = shutil.which("node")
        if not node:
            self.skipTest("node yok")
        kod = saf_kod() + """
function lcg(t) { let s = t >>> 0; return () => (s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296; }
function uret(n, tohum) {
  const r = lcg(tohum), turler = ["yakin", "cevre", "akademi", "is", "finans", "siyaset", "etkinlik"], g = [];
  for (let i = 0; i < n; i++) { const yak = Math.floor(r() * 4); g.push({ id: "k" + i, ad: "Kisi " + String.fromCharCode(65 + i % 26) + i, tur: turler[Math.floor(r() * turler.length)], yak, r: (15 + yak * 4) * dugumOlcegi(n) }); }
  return g;
}
""" + govde
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "t.js")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(kod)
            r = subprocess.run([node, yol], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr[:600])
        return json.loads(r.stdout)

    def test_yerlesim_deterministik_ve_cakismasiz(self):
        s = self.calistir("""
const out = {};
for (const n of [60, 150, 400]) {
  const g = uret(n, 7), a = agYerlesim(g, TUR_SIRASI), b = agYerlesim(g, TUR_SIRASI);
  const ayni = g.every(k => { const p = a.konum.get(k.id), q = b.konum.get(k.id); return p && q && p.x === q.x && p.y === q.y; });
  let enAz = 1e9;   // her çift için (uzaklık / (ri + rj)); 1'den küçükse kareler iç içe geçer
  for (let i = 0; i < g.length; i++) for (let j = i + 1; j < g.length; j++) {
    const p = a.konum.get(g[i].id), q = a.konum.get(g[j].id);
    enAz = Math.min(enAz, Math.hypot(p.x - q.x, p.y - q.y) / (g[i].r + g[j].r));
  }
  out[n] = { ayni, say: a.konum.size, enAz: +enAz.toFixed(3), disR: Math.round(a.disR) };
}
console.log(JSON.stringify(out));
""")
        for n in ("60", "150", "400"):
            self.assertTrue(s[n]["ayni"], n)
            self.assertEqual(s[n]["say"], int(n))
            self.assertGreaterEqual(s[n]["enAz"], 1.0, f"{n} kişide kareler çakışıyor")
        self.assertLess(s["400"]["disR"], 1500)   # 400 kişide harita makul boyda kalır

    def test_halka_dilim_dizilimi(self):
        s = self.calistir("""
const g = uret(300, 11), a = agYerlesim(g, TUR_SIRASI), ac = k => { const p = a.konum.get(k.id); return Math.atan2(p.y, p.x); };
const norm = x => { while (x < -Math.PI / 2 - 1e-9) x += 2 * Math.PI; while (x >= 1.5 * Math.PI - 1e-9) x -= 2 * Math.PI; return x; };
const dil = Object.fromEntries(a.dilimler.map(d => [d.tur, d]));
const dilimde = g.every(k => { const x = norm(ac(k)); return x >= dil[k.tur].a0 - 1e-6 && x <= dil[k.tur].a1 + 1e-6; });
const yar = {}; g.forEach(k => { const p = a.konum.get(k.id), r = Math.hypot(p.x, p.y); const t = yar[k.yak] = yar[k.yak] || [1e9, 0]; t[0] = Math.min(t[0], r); t[1] = Math.max(t[1], r); });
// yakınlık 3 içte, 0 dışta: bir yakınlığın en büyük yarıçapı bir sonrakinin (daha dış) en küçüğünden küçük olmalı
const halkalarSirali = [3, 2, 1].every(L => yar[L][1] < yar[L - 1][0]);
const sonu = a.dilimler[a.dilimler.length - 1].a1, basi = a.dilimler[0].a0;
console.log(JSON.stringify({ dilimde, halkalarSirali, ustBosluk: +(basi - (sonu - 2 * Math.PI)).toFixed(3), dilimSay: a.dilimler.length, icR: Math.round(a.icR) }));
""")
        self.assertTrue(s["dilimde"])
        self.assertTrue(s["halkalarSirali"])
        self.assertGreater(s["ustBosluk"], .15)   # tepede halka etiketleri için boşluk kalır
        self.assertEqual(s["dilimSay"], 7)

    def test_bos_ve_tek_tur(self):
        s = self.calistir("""
const bos = agYerlesim([], TUR_SIRASI);
const tek = agYerlesim([{ id: "a", ad: "A", tur: "is", yak: 1, r: 10 }, { id: "b", ad: "B", tur: "is", yak: -1, r: 10 }], TUR_SIRASI);
console.log(JSON.stringify({ bos: bos.konum.size, tek: tek.konum.size, dolayliDista: Math.hypot(tek.konum.get("b").x, tek.konum.get("b").y) > Math.hypot(tek.konum.get("a").x, tek.konum.get("a").y) }));
""")
        self.assertEqual(s["bos"], 0)
        self.assertEqual(s["tek"], 2)
        self.assertTrue(s["dolayliDista"])   # dolaylı kişiler en dış şeritte

    def test_etiket_secimi(self):
        s = self.calistir("""
const kutu = (x, y) => ({ x, y, w: 60, h: 14 });
const adaylar = [
  { i: 0, o: 10, z: false, kutular: [kutu(0, 0)] },
  { i: 1, o: 50, z: false, kutular: [kutu(30, 0), kutu(30, 40)] },    // ilk yeri 0'la çakışır ama öncelikli: o kazanır, 0 elenir
  { i: 2, o: 5, z: false, kutular: [kutu(200, 200)] },
  { i: 3, o: 1e7, z: true, kutular: [kutu(205, 205)] },              // zorunlu: 2'nin üstüne biner ama kalır, 2 elenir
  { i: 4, o: 3, z: false, kutular: [kutu(0, 100)] },
];
const sec = etiketSec(adaylar, 10, [{ e: 9, x: 0, y: 100, w: 20, h: 20 }]);   // 4. aday engelle çakışır
const tek = etiketSec([{ i: 0, o: 1, z: false, kutular: [kutu(0, 0)] }, { i: 1, o: 2, z: false, kutular: [kutu(500, 0)] }, { i: 2, o: 3, z: false, kutular: [kutu(1000, 0)] }], 2, []);
console.log(JSON.stringify({ sec: [...sec].sort(), tek: [...tek.keys()].sort() }));
""")
        self.assertEqual(s["sec"], [[1, 0], [3, 0]])
        self.assertEqual(s["tek"], [1, 2])   # azami 2: en öncelikli ikisi


if __name__ == "__main__":
    unittest.main()
