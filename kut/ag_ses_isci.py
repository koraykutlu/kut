"""Kut ses işçisi: modeli bir kez yükler, stdin'den satır satır JSON iş alır, stdout'a JSON cevap yazar.

Kut sunucusu (ag_ses.py) bunu kendi Python'uyla değil, modelin kurulu olduğu ortamın Python'uyla başlatır:
  <ema ortamı>/python.exe ag_ses_isci.py oku     → {"metin", "hiz"}   → {"wav": base64}
  <whisper ortamı>/python.exe ag_ses_isci.py yaz → {"pcm": base64 float32 16 kHz mono, "ipucu"} → {"metin"}
  <ortam>/python.exe ag_ses_isci.py indir oku|yaz [model] REPO COMMIT_SHA → kurulum sihirbazı (ag_ses_kur.py): paketi içe aktarır, model
                                                         ağırlıklarını commit sha'ya sabitleyerek HF_HOME'a indirir; stdout'a {"indirilen": bayt} yazar
Her şey bu bilgisayarda çalışır; model dosyaları yalnız yerel önbellekten okunur (HF_HUB_OFFLINE=1). Ses diske yazılmaz.
Tek istisna "indir": kullanıcının onayladığı kurulum sırasında Hugging Face'ten model indirir (çevrimdışı kilit açık değildir).
"""
import base64
import io
import json
import os
import re
import sys
import threading
import wave
from pathlib import Path

if sys.argv[1:2] != ["indir"]:   # indirme kipi dışında hiçbir şey ağa çıkmaz
    os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")
CEVAP = sys.stdout
sys.stdout = sys.stderr  # kütüphanelerin print'leri protokolü bozmasın


def yaz(o):
    CEVAP.write(json.dumps(o, ensure_ascii=False) + "\n")
    CEVAP.flush()


def oku_hazirla():
    from ema_lightning import EMA

    ema = EMA()

    def isle(g):
        import numpy as np

        metin = str(g.get("metin") or "").strip()
        if not metin:
            raise ValueError("metin boş")
        hiz = min(2.0, max(0.5, float(g.get("hiz") or 1.0)))
        ses = ema.say(metin, speed=hiz, sample_rate=24000)
        pcm = (np.clip(ses.audio, -1, 1) * 32767).astype("<i2").tobytes()
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(pcm)
        return {"wav": base64.b64encode(b.getvalue()).decode("ascii"), "sure": round(ses.duration, 2)}

    isle({"metin": "Hazır."})  # ısınma: ilk gerçek cevap beklemesin
    return isle


def yaz_hazirla():
    # pip'in nvidia-* paketlerindeki CUDA DLL'leri Windows'ta elle eklenmeli
    nv = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    if nv.is_dir():
        for b in nv.glob("*/bin"):
            os.add_dll_directory(str(b))
            os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")
    try:
        import av  # noqa: F401
    except ImportError:  # ses çözmeyi kullanmıyoruz (tarayıcı ham PCM gönderir); faster-whisper içe aktarabilsin
        import types
        sys.modules["av"] = types.ModuleType("av")
    import numpy as np
    from faster_whisper import WhisperModel

    model_adi = sys.argv[2] if len(sys.argv) > 2 else "large-v3"
    hesap = sys.argv[3] if len(sys.argv) > 3 else "int8_float16"
    cihaz = "cuda"
    try:
        model = WhisperModel(model_adi, device="cuda", compute_type=hesap)
    except Exception as e:  # GPU yoksa ya da bellek yetmezse işlemcide yavaş ama çalışır
        print(f"GPU açılamadı ({e}); işlemciye geçiliyor", file=sys.stderr)
        model, cihaz = WhisperModel(model_adi, device="cpu", compute_type="int8"), "cpu"

    # Whisper altyazı verisiyle eğitildi: sessizlikte "Altyazı M.K.", "izlediğiniz için teşekkürler" gibi şeyler uydurur
    import re
    uydurma = re.compile(r"(altyaz[ıi]|alt yaz[ıi]|subtitle|izledi[gğ]iniz i[cç]in te[sş]ekk|abone olmay[ıi] unutmay|"
                         r"kanal[ıi]ma abone|bir sonraki videoda)", re.I)

    def isle(g):
        ham = base64.b64decode(g.get("pcm") or "")
        if len(ham) < 16000 * 4 * 0.3:
            return {"metin": ""}
        ses = np.frombuffer(ham, dtype=np.float32)
        parcalar, _ = model.transcribe(ses, language="tr", beam_size=5, vad_filter=True,
                                       vad_parameters={"min_silence_duration_ms": 500},
                                       initial_prompt=(str(g.get("ipucu") or "")[:600] or None),
                                       condition_on_previous_text=False, word_timestamps=True,
                                       hallucination_silence_threshold=1.0, no_speech_threshold=0.5)
        metin = []
        for p in parcalar:
            t = p.text.strip()
            if not t or p.no_speech_prob > 0.6 and p.avg_logprob < -0.7:
                continue   # büyük olasılıkla konuşma yok
            if uydurma.search(t) and len(t) < 60:
                continue   # kısa altyazı imzası / kapanış kalıbı
            metin.append(t)
        sonuc = " ".join(m for m in metin if m).strip()
        sonuc = re.sub(r"[\s.,]*(altyaz[ıi]\s*m\.?\s*k\.?|altyaz[ıi])[\s.]*$", "", sonuc, flags=re.I).strip()   # sona yapışan imza
        return {"metin": sonuc}

    isinma = {"pcm": base64.b64encode(np.zeros(16000, np.float32).tobytes()).decode()}
    try:
        isle(isinma)  # ısınma
    except Exception as e:  # kart yüklendi ama CUDA kitaplıkları eksik olabilir: ilk çözümlemede anlaşılır
        if cihaz != "cuda":
            raise
        print(f"GPU çalışmadı ({e}); işlemciye geçiliyor", file=sys.stderr)
        model = WhisperModel(model_adi, device="cpu", compute_type="int8")
        isle(isinma)
    return isle


def indir():
    """Kurulum sihirbazı için: paketin içe aktarılabildiğini doğrular ve model ağırlıklarını indirir (HF_HOME önbelleğine)."""
    tur, model = sys.argv[2] if len(sys.argv) > 2 else "", sys.argv[3] if len(sys.argv) > 3 else ""
    repo, sha = sys.argv[4] if len(sys.argv) > 4 else "", sys.argv[5] if len(sys.argv) > 5 else ""
    if not (repo and re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise ValueError("model deposu ve 40 haneli commit sha gerekli (sabitlenmemiş indirme yapılmaz)")
    kok = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")

    def boyut():
        return sum(f.stat().st_size for f in kok.rglob("*") if f.is_file()) if kok.is_dir() else 0
    baslangic, bitti = boyut(), threading.Event()

    def izle():  # yarım kalan (.incomplete) dosyalar da sayılır
        while not bitti.wait(1.0):
            try:
                yaz({"indirilen": max(0, boyut() - baslangic)})
            except OSError:
                pass
    threading.Thread(target=izle, daemon=True).start()
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
        if tur == "oku":
            from ema_lightning.api import REPO
            if REPO != repo:
                raise ValueError(f"paketin model deposu ({REPO}) Kut'un sabitlediğinden ({repo}) farklı; indirilmedi")
            for dosya in ("config.json", "ema.pt", "decoder.pt"):
                hf_hub_download(repo, dosya, revision=sha)   # commit sha'ya sabit: depo sonradan değişse de aynı dosyalar
        elif tur == "yaz":
            import ctranslate2  # noqa: F401
            # faster-whisper'ın download_model'inin indirdiği dosyalar; revision=sha ile sabitlenir
            snapshot_download(repo, revision=sha, allow_patterns=["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"])
        else:
            raise ValueError("tür: oku | yaz")
        # çevrimdışı çalışma (HF_HUB_OFFLINE) varsayılan 'main' referansını arar; sha'yla inen önbelleğe bu referans yazılır
        ref = kok / "hub" / ("models--" + repo.replace("/", "--")) / "refs" / "main"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(sha, encoding="utf-8")
    finally:
        bitti.set()
    yaz({"indirilen": max(0, boyut() - baslangic), "bitti": True})


def main():
    tur = sys.argv[1] if len(sys.argv) > 1 else ""
    if tur == "indir":
        try:
            return indir()
        except Exception as e:
            print(f"{type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(1)
    try:
        isle = {"oku": oku_hazirla, "yaz": yaz_hazirla}[tur]()
    except Exception as e:
        yaz({"hazir": False, "hata": f"{type(e).__name__}: {e}"})
        return
    yaz({"hazir": True})
    for satir in sys.stdin:
        if not satir.strip():
            continue
        try:
            yaz({"ok": True, **isle(json.loads(satir))})
        except Exception as e:
            yaz({"ok": False, "hata": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
