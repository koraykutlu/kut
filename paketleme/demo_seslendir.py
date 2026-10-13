"""Kut demo önizlemesinin ("Deniz'in salısı") anlatım seslerini Gemini TTS ile ÖNCEDEN üretir.

Neden ön üretim: Kut çalışırken internete çıkmaz. Anlatım, yayın öncesi bir kez burada üretilip `kut/demo_ses/<sahne>.wav` olarak
pakete konur (paketleme/kut.spec varsa ekler). Dosya yoksa demo sessiz çalışır; bu betik Kut'un çalışma zamanına ait DEĞİLDİR.

Kullanım:
    py -3 paketleme/demo_seslendir.py --kuru                 # metin listesini yazdırır; ağ yok, anahtar gerekmez
    set GEMINI_API_KEY=...                                    # anahtar YALNIZ ortam değişkeninden okunur
    py -3 paketleme/demo_seslendir.py [--sahne ag,pusula] [--yeniden] [--model AD] [--ses SES]

Anahtar hiçbir yere yazılmaz, günlüğe düşmez, komut satırı bayrağı da değildir; istek başlığında (`x-goog-api-key`) gider, adrese eklenmez.
Metinler kut/ag_demo.py SAHNELER[*]["anlatim"] alanındadır (tek kaynak). Çıktı: 24 kHz, 16 bit, tek kanal WAV.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import wave

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "kut"))
import ag_demo  # noqa: E402  (yalnız metinler ve sahne kimlikleri; ağ ya da veri açmaz)

VARSAYILAN_MODEL = "gemini-2.5-flash-preview-tts"   # güncel TTS model adı değişebilir: --model ile geçersiz kılınır
VARSAYILAN_SES = "Sulafat"                          # sıcak ses; Gemini'nin hazır ses adlarından biri (--ses ile değişir)
YONERGE = "Sakin, sıcak, samimi bir anlatıcı gibi; acele etmeden, abartmadan, yumuşak bir tonla ve Türkçe doğal vurguyla oku:"
UC = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
ORNEKLEM, GENISLIK, KANAL = 24000, 2, 1
CIKTI = os.path.join(KOK, "kut", "demo_ses")


def istek_govdesi(metin, ses):
    return {"contents": [{"parts": [{"text": f"{YONERGE}\n{metin}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": ses}}}}}


def sentezle(metin, model, ses, anahtar, deneme=3):
    """Ham PCM (L16, 24 kHz) baytlarını döndürür. Hata iletisinde yalnız durum kodu ve kısa sunucu iletisi bulunur (anahtar asla)."""
    veri = json.dumps(istek_govdesi(metin, ses)).encode("utf-8")
    for n in range(1, deneme + 1):
        r = urllib.request.Request(UC.format(model=model), data=veri, method="POST",
                                   headers={"Content-Type": "application/json", "x-goog-api-key": anahtar})
        try:
            with urllib.request.urlopen(r, timeout=120) as y:
                j = json.loads(y.read().decode("utf-8"))
            return base64.b64decode(j["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and n < deneme:
                time.sleep(4 * n)
                continue
            try:
                ileti = str(json.loads(e.read().decode("utf-8")).get("error", {}).get("message", ""))[:160]
            except Exception:
                ileti = ""
            raise SystemExit(f"Gemini TTS hatası: HTTP {e.code} {ileti}".strip())
        except (KeyError, IndexError, ValueError):
            raise SystemExit("Gemini TTS cevabı beklenen biçimde değil (model adı ya da ses adı geçersiz olabilir)")
    raise SystemExit("Gemini TTS yanıt vermedi")


def wav_yaz(yol, pcm):
    with wave.open(yol, "wb") as w:
        w.setnchannels(KANAL)
        w.setsampwidth(GENISLIK)
        w.setframerate(ORNEKLEM)
        w.writeframes(pcm)


def main(argv=None):
    p = argparse.ArgumentParser(description="Kut demo anlatım seslerini Gemini TTS ile üretir (GEMINI_API_KEY ortam değişkeni).")
    p.add_argument("--kuru", action="store_true", help="Yalnız metin listesini yazdır (ağ ve anahtar yok)")
    p.add_argument("--sahne", default="", help="Virgüllü sahne kimlikleri (varsayılan: hepsi)")
    p.add_argument("--yeniden", action="store_true", help="Var olan dosyaların üzerine yaz")
    p.add_argument("--model", default=VARSAYILAN_MODEL)
    p.add_argument("--ses", default=VARSAYILAN_SES)
    p.add_argument("--cikti", default=CIKTI, help="Çıktı klasörü (varsayılan: kut/demo_ses)")
    a = p.parse_args(argv)
    secili = [x.strip() for x in a.sahne.split(",") if x.strip()]
    bilinmeyen = [x for x in secili if x not in ag_demo.SAHNE_IDLERI]
    if bilinmeyen:
        raise SystemExit("bilinmeyen sahne: " + ", ".join(bilinmeyen))
    isler = [(s["id"], s["anlatim"]) for s in ag_demo.SAHNELER if not secili or s["id"] in secili]
    if a.kuru:
        print(f"model={a.model} ses={a.ses} cikti={a.cikti}")
        print(f"yonerge: {YONERGE}")
        for sid, metin in isler:
            print(f"[{sid}] {metin}")
        return 0
    anahtar = os.environ.get("GEMINI_API_KEY", "")
    if not anahtar:
        raise SystemExit("GEMINI_API_KEY ortam değişkeni yok (denemek için --kuru)")
    os.makedirs(a.cikti, exist_ok=True)
    for sid, metin in isler:
        yol = os.path.join(a.cikti, sid + ".wav")
        if os.path.exists(yol) and not a.yeniden:
            print(f"atlandı (var): {sid}")
            continue
        wav_yaz(yol, sentezle(metin, a.model, a.ses, anahtar))
        print(f"yazıldı: {yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
