"""Kut MCP sunucusu: yapay zekâ asistanına (Claude Desktop, Claude Code, MCP destekleyen her istemci) ağını SALT OKUR araçlarla açar.

Çalıştırma: `kut.pyw --mcp --veri KLASÖR` (istemci bunu stdio üzerinden kendisi başlatır). Bağımlılık yok: MCP'nin stdio taşıması
(satır başına bir JSON-RPC 2.0 iletisi) burada stdlib ile yazılı. Ağa çıkmaz, port açmaz, diske yazmaz.

Gizlilik: istemciye giden her şey uzak modele gider sayılır. Bu yüzden her araç `ag_kapi.Kapi` kurallarını uygular:
`remote_allowed: false` ve `haric.md` ile eşleşen kişi hiç listelenmez, adı geçen satırlar atılır; her metin sır süzgecinden geçer
(`Kapi.temizle`). Telefon ve e-posta hiç verilmez. Kişi kimliği `c.gecerli_id` ile doğrulanır.
"""
import json
import re
import sys
from datetime import date, timedelta

import ag_cekirdek as c
import ag_kapi
import ag_soz
import surum

PROTOKOL = "2025-06-18"
DESTEKLENEN = {"2024-11-05", "2025-03-26", "2025-06-18"}
SONUC_AZAMI = 25
TEMAS_AZAMI = 10
GUN_AZAMI = 365

ARACLAR = [
    {"name": "kisi_ara",
     "description": "Kut ağında ada, kuruma, role, alana ya da etikete göre kişi arar. Kimlik (id), ad, kurum, rol, yakınlık (0-3) ve son temas tarihini döner. "
                    "Kişinin ayrıntısı için sonra kisi_karti ya da brifing çağır.",
     "inputSchema": {"type": "object", "properties": {"sorgu": {"type": "string", "description": "Ad, kurum, rol ya da etiket parçası"}},
                     "required": ["sorgu"]}},
    {"name": "kisi_karti",
     "description": "Bir kişinin kartı: kurum, rol, nereden tanışıldığı, yakınlık, kullanıcının görüşü, sonraki adım, açık sözler ve son temas notları.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string", "description": "kisi_ara'dan gelen kimlik"}}, "required": ["id"]}},
    {"name": "bu_hafta",
     "description": "Bu hafta ilgilenilmesi gereken kişiler: tarihi gelen sonraki adımlar, yakınlığına göre ihmal edilenler, gecikmiş ya da yaklaşan sözler.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "son_gorusmeler",
     "description": "Son N günde kayıtlı temaslar (tarih, kişi, kanal, tek cümle not), yeniden eskiye.",
     "inputSchema": {"type": "object", "properties": {"gun": {"type": "integer", "minimum": 1, "maximum": GUN_AZAMI, "default": 30}}}},
    {"name": "brifing",
     "description": "Bir kişiyle görüşme öncesi tek sayfalık brifing (Markdown): konuşulabilecekler, açık sözler, ortak bağlar, son temaslar.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
]


class AracHatasi(ValueError):
    """Kullanıcıya gösterilecek araç hatası (isError: true)."""


def _kisiler(kapi):
    """Kapıdan geçen kişiler (hariç ve uzağa kapalı olanlar yok)."""
    hl = c.haric_listesi()
    return [k for k in c.kisileri_oku() if kapi.acik_mi(k["id"]) and not c.haric_mi(k, hl)]


def _liste(v):
    return v if isinstance(v, list) else [v] if v else []


def _kisi(kapi, kid):
    if not isinstance(kid, str) or not c.gecerli_id(kid) or not kapi.acik_mi(kid):
        raise AracHatasi("Kişi bulunamadı ya da yapay zekâya kapalı.")
    k = next((x for x in _kisiler(kapi) if x["id"] == kid), None)
    if k is None:
        raise AracHatasi("Kişi bulunamadı ya da yapay zekâya kapalı.")
    return k


def _ozet_satiri(k):
    parca = [f"{k.get('ad') or k['id']} (id: {k['id']})"]
    for alan in ("kurum", "rol"):
        if k.get(alan):
            parca.append(str(k[alan]))
    parca.append(f"yakınlık {k.get('yakinlik', 0)}")
    if k.get("son_temas"):
        parca.append(f"son temas {k['son_temas']}")
    return " · ".join(parca)


def kisi_ara(kapi, sorgu=""):
    s = c.sade(str(sorgu or "")).strip()
    if not s:
        raise AracHatasi("Arama metni boş.")
    bulunan = []
    for k in _kisiler(kapi):
        alanlar = [k.get("ad"), k.get("kurum"), k.get("rol")] + _liste(k.get("aliases")) + _liste(k.get("alan")) + _liste(k.get("etiketler"))
        if any(s in c.sade(str(a)) for a in alanlar if a):
            bulunan.append(k)
    bulunan.sort(key=lambda k: (-int(k.get("yakinlik") or 0), c.sade(k.get("ad") or "")))
    if not bulunan:
        return "Eşleşen kişi yok."
    satirlar = [f"- {_ozet_satiri(k)}" for k in bulunan[:SONUC_AZAMI]]
    if len(bulunan) > SONUC_AZAMI:
        satirlar.append(f"(+{len(bulunan) - SONUC_AZAMI} kişi daha; aramayı daralt)")
    return "\n".join(satirlar)


def _temas_satirlari(govde, azami=TEMAS_AZAMI):
    satirlar = [l.strip() for l in c.bolum_oku(govde, "Temas").splitlines() if re.match(r"^- \d{2}\.\d{2}\.\d{4}", l.strip())]

    def anahtar(l):
        g, a, y = l[2:12].split(".")
        return (y, a, g)
    return sorted(satirlar, key=anahtar, reverse=True)[:azami]


def kisi_karti(kapi, id=""):
    k = _kisi(kapi, id)
    s = [f"# {k.get('ad') or k['id']}", ""]
    tur = c.TURLER.get(k.get("tur"))
    bilgi = [("Tür", tur[0] if isinstance(tur, (list, tuple)) else tur or k.get("tur")), ("Kurum", k.get("kurum")), ("Rol", k.get("rol")),
             ("Alan", ", ".join(_liste(k.get("alan")))), ("Nereden", ", ".join(_liste(k.get("nereden")))),
             ("Yakınlık", f"{k.get('yakinlik', 0)} / 3"), ("Son temas", k.get("son_temas")), ("Görüşme sıklığı", k.get("temas_sikligi")),
             ("Kullanıcının görüşü", k.get("kullanici_gorusu")), ("Neden önemli", k.get("neden_onemli")),
             ("Ne verebilirim", k.get("ne_verebilirim")), ("Sonraki adım", k.get("sonraki_adim")), ("Sonraki tarih", k.get("sonraki_tarih"))]
    s += [f"- {ad}: {v}" for ad, v in bilgi if v]
    sozler = ag_soz.acik_sozler(k.get("govde") or "")
    if sozler:
        s += ["", "## Açık sözler"] + [f"- {ag_soz.ETIKET[x['yon']]}: {x['metin']} ({ag_soz.durum_yazisi(x)})" for x in sozler]
    temas = _temas_satirlari(k.get("govde") or "")
    if temas:
        s += ["", f"## Son temaslar (en çok {TEMAS_AZAMI})"] + temas
    beyan = c.bolum_oku(k.get("govde") or "", "Senin beyanların")
    if beyan:
        s += ["", "## Kullanıcının beyanları", beyan]
    return "\n".join(s)


def bu_hafta(kapi):
    kisiler = _kisiler(kapi)
    ad = {k["id"]: k.get("ad") or k["id"] for k in kisiler}
    liste = [x for x in c.bu_hafta(kisiler) if x["id"] in ad]
    if not liste:
        return "Bu hafta bekleyen bir şey yok."
    return "\n".join(f"- {ad[x['id']]} (id: {x['id']}): {x['neden']}" for x in liste)


def son_gorusmeler(kapi, gun=30):
    try:
        gun = max(1, min(GUN_AZAMI, int(gun)))
    except (TypeError, ValueError):
        raise AracHatasi("gun bir tam sayı olmalı.")
    sinir = date.today() - timedelta(days=gun)
    olaylar = []
    for k in _kisiler(kapi):
        for l in _temas_satirlari(k.get("govde") or "", azami=10_000):
            g, a, y = l[2:12].split(".")
            try:
                t = date(int(y), int(a), int(g))
            except ValueError:
                continue
            if t >= sinir:
                olaylar.append((t, f"- {l[2:12]} · {k.get('ad') or k['id']} (id: {k['id']}){l[12:]}"))
    if not olaylar:
        return f"Son {gun} günde kayıtlı temas yok."
    olaylar.sort(key=lambda x: x[0], reverse=True)
    return "\n".join(x[1] for x in olaylar[:100])


def brifing(kapi, id=""):
    import ag_brifing
    k = _kisi(kapi, id)
    veri = c.veri_hazirla(foto_gom=False)
    veri["kisiler"] = [x for x in veri.get("kisiler") or [] if kapi.acik_mi(x.get("id")) or x.get("id") == k["id"]]
    try:
        return ag_brifing.markdown(ag_brifing.brifing(veri, k["id"]))
    except ValueError as e:
        raise AracHatasi(str(e))


ISLEV = {"kisi_ara": kisi_ara, "kisi_karti": kisi_karti, "bu_hafta": bu_hafta, "son_gorusmeler": son_gorusmeler, "brifing": brifing}


def arac_cagir(ad, argumanlar):
    """Aracı çalıştırır; dönen metin her zaman kapıdan (kapalı kişiyi anan satırlar atılır) ve sır süzgecinden geçer."""
    if ad not in ISLEV:
        raise AracHatasi(f"Bilinmeyen araç: {ad}")
    if not isinstance(argumanlar, dict):
        raise AracHatasi("Argümanlar bir nesne olmalı.")
    izinli = set(next(a for a in ARACLAR if a["name"] == ad)["inputSchema"]["properties"])
    kapi = ag_kapi.Kapi()
    metin = ISLEV[ad](kapi, **{k: v for k, v in argumanlar.items() if k in izinli})
    return kapi.temizle(metin)


def isle(ileti):
    """Tek bir JSON-RPC iletisini işler; bildirimlere (id yok) cevap None'dır."""
    if not isinstance(ileti, dict) or ileti.get("jsonrpc") != "2.0" or not isinstance(ileti.get("method"), str):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Geçersiz istek"}}
    yontem, kimlik, p = ileti["method"], ileti.get("id"), ileti.get("params") or {}
    if "id" not in ileti:
        return None

    def cevap(sonuc):
        return {"jsonrpc": "2.0", "id": kimlik, "result": sonuc}

    if yontem == "initialize":
        istenen = p.get("protocolVersion") if isinstance(p, dict) else None
        return cevap({"protocolVersion": istenen if istenen in DESTEKLENEN else PROTOKOL,
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "kut", "title": "Kut", "version": surum.SURUM},
                      "instructions": "Kut, kullanıcının kişisel ilişki ağıdır (yerel, salt okur). Kişi verisi özeldir: yalnız görev için gerekeni iste, "
                                      "mesaj içeriği uydurma, kayıtta olmayanı 'kayıtta yok' de. Mesaj taslağı yazabilirsin ama gönderen kullanıcıdır."})
    if yontem == "ping":
        return cevap({})
    if yontem == "tools/list":
        return cevap({"tools": [dict(a, annotations={"readOnlyHint": True, "openWorldHint": False}) for a in ARACLAR]})
    if yontem == "tools/call":
        try:
            metin = arac_cagir(p.get("name"), p.get("arguments") or {})
            return cevap({"content": [{"type": "text", "text": metin}], "isError": False})
        except (AracHatasi, TypeError) as e:
            return cevap({"content": [{"type": "text", "text": str(e) if isinstance(e, AracHatasi) else "Geçersiz argüman."}], "isError": True})
    return {"jsonrpc": "2.0", "id": kimlik, "error": {"code": -32601, "message": f"Yöntem yok: {yontem}"}}


def main(girdi=None, cikti=None):
    """stdio döngüsü. stdout yalnız protokol içindir: başka her çıktı stderr'e yönlenir."""
    girdi = girdi or sys.stdin.buffer
    cikti = cikti or sys.stdout.buffer
    sys.stdout = sys.stderr   # modüllerin print'i protokolü bozmasın
    for ham in girdi:
        ham = ham.strip()
        if not ham:
            continue
        try:
            ileti = json.loads(ham.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            yanit = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Ayrıştırma hatası"}}
        else:
            try:
                yanit = isle(ileti)
            except Exception as e:   # sunucu çökmesin; ayrıntı yalnız stderr'de
                print(f"Kut MCP: {type(e).__name__}: {e}", file=sys.stderr)
                yanit = {"jsonrpc": "2.0", "id": ileti.get("id") if isinstance(ileti, dict) else None,
                         "error": {"code": -32603, "message": "İç hata"}}
        if yanit is not None:
            cikti.write(json.dumps(yanit, ensure_ascii=False).encode("utf-8") + b"\n")
            cikti.flush()
    return 0
