"""Model sağlayıcı katmanı: Kut'un uzağa giden TÜM model çağrıları buradan geçer.
Sağlayıcılar, kullanıcının makinesinde kurulu komut satırı araçlarıdır; her biri kendi oturumunu (abonelik/giriş) yönetir.
Kut API anahtarı saklamaz, istemez, ortama koymaz.
  claude  Claude Code (`claude -p`)  varsayılan ve ÖNERİLEN; oturum devamı, salt-okur dosya araçları, belge (PDF/görsel) okuma.
  codex   OpenAI Codex CLI (`codex exec`)
  gemini  Google Gemini CLI (`gemini -p`)
  ollama  Yerel Ollama (yalnız 127.0.0.1:11434); veri bilgisayardan çıkmaz.
Yetenek farkı burada düşürülür: Claude dışındaki sağlayıcılara Kut dosya aracı VERMEZ, ama Codex ve Gemini kendi yerleşik araçlarıyla
diski okuyabilir (Codex `--sandbox read-only` yazmayı engeller, okumayı değil; Gemini'de plan kipi salt-okur araçları açık bırakır).
Bu yüzden ikisi boş, geçici bir çalışma klasöründe çalışır; Gemini'ye ek olarak "tüm araçlar yasak" politikası verilir (_gemini).
Kişi kapısı yalnız Kut'un GÖNDERDİĞİ veriyi süzer; aracın kendi okuyuşunu süzemez: bu yüzden bu iki sağlayıcı seçilirken açık onay gerekir.
Kapıdan (ag_kapi.kopya) geçmiş veri klasörünün metni istemin içine konur. Hiçbir sağlayıcıya yazma izni verilmez.
Her istem, sağlayıcı ne olursa olsun, sır süzgecinden (ag_sir.temizle) geçer. Ollama dışındakiler "uzak" sayılır.
Kişi bazlı kapı (haric.md / remote_allowed) çağıranlarda uygulanır (ag_kapi.Kapi); bu katman onu atlatmaz, yalnız ek bir yol açmaz."""
import collections
import contextlib
import http.client
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid

import ag_ice_aktar as ia
import ag_kilit
import ag_sir

VARSAYILAN_SAGLAYICI = "claude"
VARSAYILAN_MODEL = {"analiz": "claude-haiku-5-5", "sohbet": "claude-haiku-5-5", "strateji": "claude-opus-5-5"}  # yalnız Claude için
AYAR_ANAHTARI = {"analiz": "analiz_modeli", "sohbet": "sohbet_modeli", "strateji": "strateji_modeli"}
OLLAMA_ADRES = ("127.0.0.1", 11434)
MODEL_AD = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]{0,99}")   # bayrak enjeksiyonunu önler ("-" ile başlayamaz)
CLAUDE_OTURUM = re.compile(r"[0-9a-f-]{20,60}")
KAPALI_ARACLAR = ["Bash", "Edit", "Write", "Glob", "Grep", "WebFetch", "WebSearch", "NotebookEdit", "Task"]
DOSYA_BUTCE = {"ollama": 40_000}   # modele inline verilecek veri klasörü metni (karakter); diğerleri VARSAYILAN_BUTCE
VARSAYILAN_BUTCE = 300_000
INLINE_ATLANAN = {"gelen", "belgeler", "foto", "arsiv"}
# Kendi yerleşik araçlarıyla diski okuyabilen sağlayıcılar: seçerken açık onay gerekir (ayarla: onay=True).
ARAC_UYARISI = ("Bu araç bilgisayarındaki dosyaları kendi başına açabilir. Kut, \"kimseye gitmesin\" dediğin kişileri yalnız kendi "
                "gönderdiği metinden ayıklar; araç dosyaları kendisi açarsa bu koruma işlemez ve okunan bilgi aracın şirketine gidebilir "
                "({not}). Ağında hassas kişiler varsa Claude Code ya da Ollama kullan.")
ARAC_NOTU = {"codex": "Kut Codex'te bu araçları kapatamaz",
             "gemini": "Kut Gemini'de araçları kapatmaya çalışır, ama bunun her sürümde işlediğini doğrulayamaz"}


def arac_uyarisi(sid):
    """Diski kendi okuyabilen sağlayıcı için gizlilik uyarısı; diğerleri için boş metin."""
    if not SAGLAYICILAR.get(sid, {}).get("arac_riski"):
        return ""
    return ARAC_UYARISI.replace("{not}", ARAC_NOTU.get(sid, "Kut bu aracın araçlarını kapatamayabilir"))
# Gemini CLI 0.62 yerleşik araç adları (docs/reference/tools.md). Politika "*" hepsini reddeder; bu liste yedek katmandır.
GEMINI_ARACLAR = ["run_shell_command", "glob", "grep_search", "search_file_content", "list_directory", "read_file", "read_many_files",
                  "write_file", "replace", "ask_user", "write_todos", "activate_skill", "get_internal_docs", "enter_plan_mode",
                  "exit_plan_mode", "google_web_search", "web_fetch", "list_mcp_resources", "read_mcp_resource", "save_memory"]
GEMINI_POLITIKA = '[[rule]]\ntoolName = "*"\ndecision = "deny"\npriority = 999\ndenyMessage = "Kut: araçlar kapalı"\n'

SAGLAYICILAR = {
    "claude": {"ad": "Claude Code", "komut": "claude", "onerilen": True, "uzak": True, "oturum": True, "arac": True, "belge": True,
               "kurulum": "Claude Code kurulu değil (claude komutu bulunamadı).",
               "gizlilik": "Kut, Claude'un hangi dosyaları okuyabileceğini kendisi sınırlar: yalnız ayıklanmış kopyayı görür. Veri Anthropic'e gider.",
               "aciklama": "Kut'un asıl hedeflediği ve test ettiği yol. Oturum devamı, salt-okur dosya araçları ve PDF/görsel belge okuma burada tam çalışır."},
    "codex": {"arac_riski": True, "ad":"OpenAI Codex CLI", "komut": "codex", "onerilen": False, "uzak": True, "oturum": False, "arac": False, "belge": False,
              "kurulum": "Codex CLI kurulu değil (codex komutu bulunamadı).",
              "aciklama": "ChatGPT hesabınla giriş yapmış `codex` komutu. Kut'a sor her turda bağlamı yeniden gönderir; PDF/görsel belgeler okunmaz."},
    "gemini": {"arac_riski": True, "ad":"Google Gemini CLI", "komut": "gemini", "onerilen": False, "uzak": True, "oturum": False, "arac": False, "belge": False,
               "kurulum": "Gemini CLI kurulu değil (gemini komutu bulunamadı).",
               "aciklama": "Google hesabınla giriş yapmış `gemini` komutu. Kut'a sor her turda bağlamı yeniden gönderir; PDF/görsel belgeler okunmaz."},
    "ollama": {"ad": "Ollama (yerel)", "komut": "ollama", "onerilen": False, "uzak": False, "oturum": False, "arac": False, "belge": False,
               "kurulum": "Ollama çalışmıyor (127.0.0.1:11434 yanıt vermedi; Ollama kurulu ve açık mı?).",
               "gizlilik": "En güçlü gizlilik: model bu bilgisayarda çalışır, hiçbir veri dışarı çıkmaz.",
               "aciklama": "Yalnız bu bilgisayarda çalışan model; veri bilgisayardan çıkmaz. Küçük modellerde sonuç zayıf olabilir (JSON ve uzun bağlam)."},
}

_kilit = threading.Lock()
_gecmis_imza = None   # geçmişin biriktiği kapı/sağlayıcı durumu; değişirse geçmiş silinir
_gecmis = collections.OrderedDict()   # oturumsuz sağlayıcılar için bellek içi konuşma geçmişi: id → [(soru, cevap)]
GECMIS_OTURUM, GECMIS_TUR = 20, 12


_claude_oturumlar = collections.OrderedDict()   # bu süreçte üretilen/devam ettirilen Claude oturum kimlikleri
_claude_iptal = collections.OrderedDict()       # kilitlenince iptal edilenler: bir daha --resume edilmez (yeni konuşma başlar)
CLAUDE_OTURUM_AZAMI = 500


def _kilit_bagla():
    """Kilitlenince (oturum kapanınca/süresi dolunca) konuşma geçmişi ve Claude oturum kimlikleri bellekten silinir. Tekrar çağrılabilir."""
    for f in (gecmis_temizle, claude_oturumlari_iptal_et):
        if f not in ag_kilit.kapaninca:
            ag_kilit.kapaninca.append(f)


def claude_oturumlari_iptal_et():
    """Kilitlenince: bilinen tüm Claude oturum kimlikleri iptal listesine geçer; sonraki sohbet bu kimlikleri `--resume` etmez ve tam bağlamla
    yeni oturum açar (kilit açıldıktan sonra eski konuşmanın modelde sürmesi engellenir). Claude CLI'nin kendi disk kaydına dokunulmaz."""
    with _kilit:
        for o in _claude_oturumlar:
            _claude_iptal[o] = True
        _claude_oturumlar.clear()
        while len(_claude_iptal) > CLAUDE_OTURUM_AZAMI:
            _claude_iptal.popitem(last=False)


def claude_oturum_gecerli(oturum):
    """Bu kimlik ile Claude konuşması sürdürülebilir mi (biçim uygun ve kilitle iptal edilmemiş)?"""
    return isinstance(oturum, str) and bool(CLAUDE_OTURUM.fullmatch(oturum)) and oturum not in _claude_iptal


class Cevap:
    def __init__(self, metin, oturum=""):
        self.metin, self.oturum = metin, oturum


# ---------- seçim ve durum ----------
def secili():
    s = ia.ayarlar().get("saglayici")
    return s if s in SAGLAYICILAR else VARSAYILAN_SAGLAYICI


def uzak_mi(sag=None):
    return SAGLAYICILAR[sag or secili()]["uzak"]


def oturum_destekli(sag=None):
    return SAGLAYICILAR[sag or secili()]["oturum"]


def yol_bul(sag):
    """Komutun tam yolu ya da None. Ollama için komut değil çalışan yerel sunucu aranır (ollama_calisiyor)."""
    if sag == "ollama":
        return shutil.which("ollama") or ("127.0.0.1:11434" if ollama_calisiyor() else None)
    yol = shutil.which(SAGLAYICILAR[sag]["komut"])
    if yol or sag != "claude":
        return yol
    aday = os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe" if os.name == "nt" else "claude")
    return aday if os.path.exists(aday) else None


def hazir(sag=None):
    """Seçili (ya da verilen) sağlayıcı kullanılabilir mi?"""
    sag = sag or secili()
    if sag == "ollama":
        return ollama_calisiyor()
    return bool(yol_bul(sag))


def hazir_degil_mesaji(sag=None):
    return SAGLAYICILAR[sag or secili()]["kurulum"]


def model_adi(gorev, sag=None):
    """Claude: ayarlar.json'daki analiz/sohbet/strateji modeli (eski anahtarlar, aynı varsayılanlar). Diğerleri: ayarlar → modeller[sağlayıcı]
    (boşsa CLI'nin kendi varsayılanı; Kut model kimliği uydurmaz)."""
    sag = sag or secili()
    a = ia.ayarlar()
    if sag == "claude":
        m = a.get(AYAR_ANAHTARI[gorev])
        if gorev == "sohbet":
            m = m or a.get("analiz_modeli")
        return m or VARSAYILAN_MODEL[gorev]
    return str((a.get("modeller") or {}).get(sag) or "").strip()


def model_etiketi(gorev):
    """Kayıtta/arayüzde görünen ad: Claude'da düz model kimliği (eskisi gibi), diğerlerinde 'codex:model'."""
    sag = secili()
    return model_adi(gorev, sag) if sag == "claude" else f"{sag}:{model_adi(gorev, sag) or 'varsayılan'}"


def durum():
    """Arayüz için: seçili sağlayıcı ve her birinin kurulu olup olmadığı."""
    a = ia.ayarlar()
    liste = []
    for sid, s in SAGLAYICILAR.items():
        d = {"id": sid, "ad": s["ad"], "onerilen": s["onerilen"], "uzak": uzak_mi(sid), "kurulu": hazir(sid), "aciklama": s["aciklama"], "gizlilik": s.get("gizlilik", ""),
             "model": str((a.get("modeller") or {}).get(sid) or ""), "uyari": arac_uyarisi(sid)}
        if sid == "claude":
            d["model"] = ""   # Claude modelleri ayarlar.json'daki eski anahtarlardadır
        liste.append(d)
    return {"secili": secili(), "saglayicilar": liste}


def ayarla(g):
    """{saglayici, modeller: {codex: "...", ...}} → ayarlar.json. Kurulu olmayan sağlayıcı seçilemez."""
    a = ia.ayarlar()
    if "saglayici" in g:
        if g["saglayici"] not in SAGLAYICILAR:
            raise ValueError("bilinmeyen sağlayıcı")
        if not hazir(g["saglayici"]):
            raise ValueError(SAGLAYICILAR[g["saglayici"]]["kurulum"])
        degisti = g["saglayici"] != secili()
        if degisti and SAGLAYICILAR[g["saglayici"]].get("arac_riski") and g.get("onay") is not True:
            raise ValueError("Onay gerekli. " + arac_uyarisi(g["saglayici"]))
        a["saglayici"] = g["saglayici"]
        if degisti:
            gecmis_temizle()
    if isinstance(g.get("modeller"), dict):
        m = dict(a.get("modeller") or {})
        for sid, ad in g["modeller"].items():
            ad = str(ad or "").strip()
            if sid not in SAGLAYICILAR or sid == "claude":
                continue
            if ad and not MODEL_AD.fullmatch(ad):
                raise ValueError("model adı geçersiz")
            m[sid] = ad
        a["modeller"] = m
    ia.ayar_yaz(a)
    return durum()


# ---------- oturumsuz sağlayıcılar için konuşma geçmişi ----------
def yeni_oturum_id():
    return str(uuid.uuid4())


def gecmis_al(oid):
    if not isinstance(oid, str):
        return []
    with _kilit:
        return list(_gecmis.get(oid) or [])


def gecmis_temizle():
    """Bellekteki tüm konuşma geçmişini siler (kilitlenince, sağlayıcı ya da kapı listesi değişince)."""
    global _gecmis_imza
    with _kilit:
        _gecmis.clear()
        _gecmis_imza = None


def gecmis_imza_denetle(imza):
    """Kapı/sağlayıcı durumu önceki turdan farklıysa geçmişi siler; sonra yeni durumu kaydeder."""
    global _gecmis_imza
    degisti = False
    with _kilit:
        if imza != _gecmis_imza:
            _gecmis.clear()
            degisti = True
        _gecmis_imza = imza
    if degisti:   # kapı (🔒/hariç) ya da sağlayıcı değişti: Claude'daki eski konuşma o kişinin verisini bağlamında taşıyor olabilir, --resume edilmez
        claude_oturumlari_iptal_et()


def gecmis_ekle(oid, soru, cevap):
    if not (isinstance(oid, str) and isinstance(soru, str) and isinstance(cevap, str)):
        return
    with _kilit:
        _gecmis.setdefault(oid, []).append((soru, cevap))
        _gecmis[oid] = _gecmis[oid][-GECMIS_TUR:]
        _gecmis.move_to_end(oid)
        while len(_gecmis) > GECMIS_OTURUM:
            _gecmis.popitem(last=False)


def gecmis_blogu(gecmis):
    return "\n".join(f"Kullanıcı: {s}\nSen: {c}" for s, c in gecmis)


# ---------- veri klasörünü inline vermek ----------
def klasor_ozeti(veri, azami):
    """Kapıdan geçmiş kopyanın metin dosyaları (kisiler önce), azami karakterle kırpılmış. Dosya aracı olmayan sağlayıcılar için."""
    parcalar, toplam = [], 0
    dosyalar = []
    for yol, dizinler, adlar in os.walk(veri):
        goreli = os.path.relpath(yol, veri)
        ust = "" if goreli == "." else goreli.replace("\\", "/").split("/")[0]
        dizinler[:] = sorted(d for d in dizinler if not (ust == "" and d in INLINE_ATLANAN))
        for ad in sorted(adlar):
            if os.path.splitext(ad)[1].lower() in (".md", ".txt", ".json", ".csv", ".tsv", ".yaml", ".yml"):
                dosyalar.append(os.path.join(yol, ad))
    dosyalar.sort(key=lambda y: (0 if os.path.relpath(y, veri).replace("\\", "/").startswith("kisiler/") else 1, y))
    for y in dosyalar:
        try:
            metin = open(y, encoding="utf-8").read().strip()
        except (OSError, ValueError):
            continue
        blok = f"### {os.path.relpath(y, veri).replace(chr(92), '/')}\n{metin}\n"
        if toplam + len(blok) > azami:
            kalan = azami - toplam
            if kalan > 400:
                parcalar.append(blok[:kalan] + "\n[kırpıldı]")
            parcalar.append("[Veri bütçesi doldu; kalan dosyalar gönderilmedi.]")
            break
        parcalar.append(blok)
        toplam += len(blok)
    return "\n".join(parcalar)


# ---------- ortak çağrı ----------
def _calistir(arg, istem, cwd, zaman_asimi, env=None):
    ek = {"env": env} if env is not None else {}
    return subprocess.run(arg, input=istem.encode("utf-8"), capture_output=True, cwd=cwd, timeout=zaman_asimi,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **ek)


@contextlib.contextmanager
def _bos_klasor():
    """Kendi araçlarıyla dosya okuyabilen uzak sağlayıcılar için boş, geçici çalışma klasörü (Kut klasörlerini görmesin); çıkışta silinir."""
    d = tempfile.mkdtemp(prefix="kut-bos-")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _hata(ad, p):
    return RuntimeError(f"{ad} hata verdi: " + p.stderr.decode("utf-8", "replace")[-300:])


def _json_nesne(metin):
    """stdout'ta uyarı satırları olsa da son JSON nesnesini ayıklar; olmazsa None."""
    metin = metin.strip()
    try:
        return json.loads(metin)
    except ValueError:
        pass
    for m in re.finditer(r"^\{", metin, re.M):
        try:
            return json.loads(metin[m.start():])
        except ValueError:
            continue
    return None


def cagir(gorev, istem, *, sistem="", zaman_asimi=240, json_cikti=False, oturum="", oturum_kalici=False,
          okuma_klasoru=None, veri_klasoru=None, cwd=None, yer="istem"):
    """Seçili sağlayıcıyla tek model çağrısı → Cevap(metin, oturum).
    gorev: analiz|sohbet|strateji (model seçimi). sistem: sistem istemi. json_cikti: yanıt JSON olmalı (istem bunu söyler; Ollama'da format=json).
    oturum_kalici + oturum: Claude'da konuşma devamı (--resume); diğerlerinde yok sayılır (çağıran bağlamı yeniden verir).
    okuma_klasoru: yalnız o klasörde salt-okur dosya okuma (PDF/görsel belge); yalnız Claude. veri_klasoru: kapıdan geçmiş kopya;
    Claude salt-okur araçlarla gezer, diğerlerine metni istemin içinde verilir. yer: sır süzgeci günlüğü için istem adı."""
    if ag_kilit.kilitli_mi():   # Kut kilitliyken (PIN kuruluysa ve açık oturum yoksa) hiçbir model çağrısı yapılmaz
        raise RuntimeError("Kut kilitli: model çağrısı için önce PIN ile aç.")
    sag = secili()
    s = SAGLAYICILAR[sag]
    if not hazir(sag):
        raise RuntimeError(s["kurulum"])
    if okuma_klasoru and not s["belge"]:
        raise RuntimeError(f"{s['ad']} PDF/görsel belge okuyamaz; bu belge için sağlayıcıyı Claude Code yap.")
    model = model_adi(gorev, sag)
    if model and not MODEL_AD.fullmatch(model):
        raise RuntimeError("model adı geçersiz: ayarlardaki model adını düzelt")
    if not isinstance(oturum, str):
        oturum = ""
    cwd = cwd or os.getcwd()
    os.makedirs(cwd, exist_ok=True)
    if sag == "claude":
        return _claude(istem, sistem, model, zaman_asimi, oturum, oturum_kalici, okuma_klasoru, veri_klasoru, cwd, yer)
    parca = []
    if sistem:
        parca.append(sistem)
    if veri_klasoru:
        parca.append("NOT: Bu çalıştırmada dosya araçların yok. Yukarıda adı geçen veri klasörünün ilgili metinleri aşağıdadır; "
                     "başka dosya okumaya çalışma.\n--- VERİ ---\n" + klasor_ozeti(veri_klasoru, DOSYA_BUTCE.get(sag, VARSAYILAN_BUTCE)) + "\n--- VERİ SONU ---")
    parca.append(istem)
    duz = ag_sir.temizle("\n\n".join(parca), yer)
    if sag == "codex":
        with _bos_klasor() as bos:
            return _codex(duz, model, zaman_asimi, bos, s["ad"])
    if sag == "gemini":
        with _bos_klasor() as bos:
            return _gemini(duz, model, zaman_asimi, bos, s["ad"])
    return _ollama(duz, model, zaman_asimi, json_cikti, s["ad"])


def _komut(sag):
    """yol_bul sonucu None ise argv'ye None girmesin (TypeError): anlaşılır kurulum hatası."""
    yol = yol_bul(sag)
    if not yol:
        raise RuntimeError(SAGLAYICILAR[sag]["kurulum"])
    return yol


def _claude(istem, sistem, model, zaman_asimi, oturum, oturum_kalici, okuma_klasoru, veri_klasoru, cwd, yer):
    ad = SAGLAYICILAR["claude"]["ad"]
    arg = [_komut("claude"), "-p", "--output-format", "json"]
    if not oturum_kalici:
        arg.append("--no-session-persistence")
    arg += ["--model", model]
    if veri_klasoru:
        arg += ["--add-dir", veri_klasoru, "--allowedTools", "Read", "Grep", "Glob",
                "--disallowedTools", "Bash", "Edit", "Write", "WebFetch", "WebSearch", "NotebookEdit", "Task"]
    else:
        arg += ["--disallowedTools", *KAPALI_ARACLAR, *([] if okuma_klasoru else ["Read"])]
        if okuma_klasoru:
            arg += ["--allowedTools", "Read"]
    if sistem:
        arg += ["--append-system-prompt", ag_sir.temizle(sistem, yer)]
    if oturum and oturum_kalici and claude_oturum_gecerli(oturum):
        arg += ["--resume", oturum]
    p = _calistir(arg, ag_sir.temizle(istem, yer), okuma_klasoru or cwd, zaman_asimi)
    if p.returncode != 0:
        raise _hata(ad, p)
    cikti = json.loads(p.stdout.decode("utf-8", "replace"))
    if cikti.get("is_error"):
        raise RuntimeError(f"{ad}: " + str(cikti.get("result"))[:300])
    yeni = cikti.get("session_id", "")
    if oturum_kalici and isinstance(yeni, str) and CLAUDE_OTURUM.fullmatch(yeni):
        with _kilit:
            _claude_oturumlar[yeni] = True
            while len(_claude_oturumlar) > CLAUDE_OTURUM_AZAMI:
                _claude_oturumlar.popitem(last=False)
    return Cevap(cikti.get("result", ""), yeni)


def _codex(istem, model, zaman_asimi, cwd, ad):
    """`codex exec`: istem stdin'den ("-"), son ajan mesajı -o dosyasına yazılır. Sandbox salt-okur (YAZMAYI engeller, OKUMAYI
    engellemez), oturum kaydı yok. Kabuk/araç kapatan `-c` anahtarları resmi belgeden doğrulanamadı, uydurulmadı: sınır boş geçici cwd + onaydır."""
    fd, cikis = tempfile.mkstemp(prefix="kut-codex-", suffix=".txt")
    os.close(fd)
    try:
        arg = [_komut("codex"), "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral", "--color", "never",
               "--output-last-message", cikis, *(["--model", model] if model else []), "-"]
        p = _calistir(arg, istem, cwd, zaman_asimi)
        if p.returncode != 0:
            raise _hata(ad, p)
        metin = open(cikis, encoding="utf-8", errors="replace").read().strip()
        if not metin:
            raise RuntimeError(f"{ad}: boş yanıt")
        return Cevap(metin)
    finally:
        with contextlib.suppress(OSError):
            os.remove(cikis)


def _gemini(istem, model, zaman_asimi, cwd, ad):
    """`gemini -p ... -o json`: istem stdin'den (-p metni sonuna eklenir). --yolo asla. Plan kipi salt-okur araçları (dosya okuma, arama,
    web) AÇIK bırakır; bu yüzden: boş geçici cwd; `--admin-policy` ile "*" için deny (genel deny araçları modelin görüşünden de çıkarır);
    GEMINI_CLI_SYSTEM_SETTINGS_PATH ile tools.exclude yedeği. Gemini headless kipi istemdeki `@yol` ifadelerini kendisi okuyup isteme
    ekler; `@` önüne `\\` konur (kaçış)."""
    istem = re.sub(r"(?<![\w.\\])@(?=[\w./~\\])", lambda _: "\\@", istem)  # yalnız `@yol`; e-posta (can@x.com) bozulmaz
    with tempfile.TemporaryDirectory(prefix="kut-gem-") as cfg:
        pol, ayar = os.path.join(cfg, "kut-politika.toml"), os.path.join(cfg, "kut-ayar.json")
        with open(pol, "w", encoding="utf-8") as f:
            f.write(GEMINI_POLITIKA)
        with open(ayar, "w", encoding="utf-8") as f:
            json.dump({"tools": {"exclude": GEMINI_ARACLAR}}, f)
        arg = [_komut("gemini"), "--output-format", "json", "--approval-mode", "plan", "--skip-trust", "--admin-policy", pol,
               *(["--model", model] if model else []), "--prompt", "Yukarıdaki talimatı yerine getir."]
        p = _calistir(arg, istem, cwd, zaman_asimi, env={**os.environ, "GEMINI_CLI_SYSTEM_SETTINGS_PATH": ayar})
    if p.returncode != 0:
        raise _hata(ad, p)
    ham = p.stdout.decode("utf-8", "replace")
    cikti = _json_nesne(ham)
    if isinstance(cikti, dict):
        if cikti.get("error"):
            e = cikti["error"]
            raise RuntimeError(f"{ad}: " + str(e.get("message") if isinstance(e, dict) else e)[:300])
        return Cevap(str(cikti.get("response") or ""))
    return Cevap(ham.strip())


def _ollama(istem, model, zaman_asimi, json_cikti, ad):
    """Yerel HTTP, yalnız 127.0.0.1:11434 (sabit; ayarlanamaz). Proxy kullanılmaz."""
    if not model:
        kurulu = ollama_modeller()
        if not kurulu:
            raise RuntimeError(f"{ad}: yüklü model yok; `ollama pull <model>` ile bir model indir ya da ayarlardan model adı yaz.")
        model = kurulu[0]
    govde = {"model": model, "stream": False, "messages": [{"role": "user", "content": istem}], "options": {"num_ctx": 32768}}
    if json_cikti:
        govde["format"] = "json"
    h = http.client.HTTPConnection(*OLLAMA_ADRES, timeout=zaman_asimi)
    try:
        h.request("POST", "/api/chat", json.dumps(govde), {"Content-Type": "application/json"})
        r = h.getresponse()
        ham = r.read().decode("utf-8", "replace")
    except (OSError, http.client.HTTPException) as e:
        raise RuntimeError(f"{ad} hata verdi: {type(e).__name__}") from None
    finally:
        h.close()
    cikti = _json_nesne(ham)
    if r.status != 200 or not isinstance(cikti, dict) or cikti.get("error"):
        raise RuntimeError(f"{ad} hata verdi: " + str((cikti or {}).get("error") or ham)[:300])
    return Cevap(str((cikti.get("message") or {}).get("content") or ""))


def _ollama_get(yol, zaman=0.4):
    h = http.client.HTTPConnection(*OLLAMA_ADRES, timeout=zaman)
    try:
        h.request("GET", yol)
        r = h.getresponse()
        return json.loads(r.read().decode("utf-8", "replace")) if r.status == 200 else None
    except (OSError, http.client.HTTPException, ValueError):
        return None
    finally:
        h.close()


def ollama_modeller():
    d = _ollama_get("/api/tags", 3)
    return [m["name"] for m in (d or {}).get("models", []) if isinstance(m, dict) and m.get("name")]


def ollama_calisiyor():
    return isinstance(_ollama_get("/api/tags"), dict)


_kilit_bagla()
