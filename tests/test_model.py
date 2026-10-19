"""Model sağlayıcı katmanı (ag_model): her bağdaştırıcının komut satırı ve çıktı ayrıştırması. Alt süreç ve HTTP taklit edilir; gerçek model çağrılmaz."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401  (kut'tan önce: LOCALAPPDATA/AGIM_VERI geçici)

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kut")
sys.path.insert(0, KOK)
import ag_ice_aktar as ia  # noqa: E402
import ag_model as mdl  # noqa: E402

SIR = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.eski = ia.AYARLAR
        ia.AYARLAR = os.path.join(self.t.name, "ayarlar.json")
        self.cwd = os.path.join(self.t.name, "calisma")
        mdl._gecmis.clear()
        self.yol = mock.patch.object(mdl, "yol_bul", side_effect=lambda s: s + "-yolu")
        self.yol.start()

    def tearDown(self):
        mock.patch.stopall()
        ia.AYARLAR = self.eski
        self.t.cleanup()

    def sec(self, sag, **ek):
        ia.ayar_yaz({"saglayici": sag, **ek})

    def sahte(self, stdout=b"", rc=0, yaz=None):
        yakalanan = {}

        def run(arg, **kw):
            yakalanan.update(arg=arg, istem=kw["input"].decode("utf-8"), cwd=kw["cwd"], timeout=kw["timeout"])
            if yaz:
                yaz(arg)
            return subprocess.CompletedProcess(arg, rc, stdout, b"hata ayrintisi" if rc else b"")
        mock.patch.object(mdl.subprocess, "run", side_effect=run).start()
        return yakalanan

    # ---- seçim ve ayar ----
    def test_varsayilan_claude_ve_eski_model_anahtarlari(self):
        self.assertEqual(mdl.secili(), "claude")
        self.assertEqual(mdl.model_adi("analiz"), "haiku")
        self.assertEqual(mdl.model_adi("sohbet"), "haiku")
        self.assertEqual(mdl.model_adi("strateji"), "opus")
        ia.ayar_yaz({"analiz_modeli": "a", "sohbet_modeli": "s", "strateji_modeli": "t"})
        self.assertEqual([mdl.model_adi(g) for g in ("analiz", "sohbet", "strateji")], ["a", "s", "t"])
        ia.ayar_yaz({"analiz_modeli": "a"})
        self.assertEqual(mdl.model_adi("sohbet"), "a")   # eski geri düşüş
        self.assertEqual(mdl.model_etiketi("strateji"), "opus")   # eskisi gibi düz kimlik

    def test_bilinmeyen_saglayici_claude_sayilir(self):
        self.sec("uydurma")
        self.assertEqual(mdl.secili(), "claude")

    def test_uzak_sayilir_ollama_disinda(self):
        self.assertEqual([k for k, s in mdl.SAGLAYICILAR.items() if not s["uzak"]], ["ollama"])

    def test_kurulu_olmayan_secilemez(self):
        with mock.patch.object(mdl, "hazir", side_effect=lambda s=None: s != "codex"):
            with self.assertRaises(ValueError):
                mdl.ayarla({"saglayici": "codex"})
            self.assertEqual(mdl.ayarla({"saglayici": "gemini", "onay": True, "modeller": {"gemini": "gemini-x", "claude": "yok-sayilir"}})["secili"], "gemini")
            self.assertEqual(ia.ayarlar()["modeller"], {"gemini": "gemini-x"})
            with self.assertRaises(ValueError):
                mdl.ayarla({"modeller": {"gemini": "--yolo"}})   # bayrak enjeksiyonu
            d = mdl.durum()
        self.assertEqual(d["saglayicilar"][0]["id"], "claude")
        self.assertTrue(d["saglayicilar"][0]["onerilen"])
        self.assertFalse([p for p in d["saglayicilar"] if p["id"] == "codex"][0]["kurulu"])

    def test_hata_mesaji_secili_saglayiciyi_anar(self):
        self.sec("gemini")
        with mock.patch.object(mdl, "hazir", return_value=False):
            with self.assertRaises(RuntimeError) as e:
                mdl.cagir("analiz", "x", cwd=self.cwd)
        self.assertIn("Gemini", str(e.exception))
        self.assertNotIn("claude", str(e.exception).lower())

    # ---- Claude: eski çağrılarla birebir ----
    def cevap_claude(self, sid="s1"):
        return json.dumps({"result": "tamam", "session_id": sid}).encode()

    def test_claude_analiz_argumanlari_birebir(self):
        y = self.sahte(self.cevap_claude())
        r = mdl.cagir("analiz", "merhaba", zaman_asimi=900, json_cikti=True, cwd=self.cwd)
        self.assertEqual(y["arg"], ["claude-yolu", "-p", "--output-format", "json", "--no-session-persistence", "--model", "haiku",
                                    "--disallowedTools", "Bash", "Edit", "Write", "Glob", "Grep", "WebFetch", "WebSearch", "NotebookEdit", "Task", "Read"])
        self.assertEqual((y["cwd"], y["timeout"]), (self.cwd, 900))
        self.assertEqual((r.metin, r.oturum), ("tamam", "s1"))

    def test_claude_belge_okuma_yalniz_o_klasorde(self):
        y = self.sahte(self.cevap_claude())
        mdl.cagir("analiz", "x", okuma_klasoru=self.t.name, cwd=self.cwd)
        self.assertEqual(y["arg"][-3:], ["Task", "--allowedTools", "Read"])
        self.assertNotIn("Read", y["arg"][y["arg"].index("--disallowedTools"):y["arg"].index("--allowedTools")])
        self.assertEqual(y["cwd"], self.t.name)

    def test_claude_sohbet_ve_strateji_argumanlari_birebir(self):
        y = self.sahte(self.cevap_claude())
        oturum = "a" * 24
        mdl.cagir("sohbet", "s", sistem="ROL", zaman_asimi=240, oturum=oturum, oturum_kalici=True, veri_klasoru="/v", cwd=self.cwd)
        self.assertEqual(y["arg"], ["claude-yolu", "-p", "--output-format", "json", "--model", "haiku", "--add-dir", "/v",
                                    "--allowedTools", "Read", "Grep", "Glob", "--disallowedTools", "Bash", "Edit", "Write", "WebFetch", "WebSearch",
                                    "NotebookEdit", "Task", "--append-system-prompt", "ROL", "--resume", oturum])
        mdl.cagir("sohbet", "s", sistem="ROL", oturum="gecersiz!", oturum_kalici=True, veri_klasoru="/v", cwd=self.cwd)
        self.assertNotIn("--resume", y["arg"])
        mdl.cagir("strateji", "s", sistem="ROL", veri_klasoru="/v", cwd=self.cwd)
        self.assertEqual(y["arg"][:8], ["claude-yolu", "-p", "--output-format", "json", "--no-session-persistence", "--model", "opus", "--add-dir"])
        self.assertNotIn("--resume", y["arg"])

    def test_claude_hatalari(self):
        self.sahte(b"", rc=1)
        with self.assertRaisesRegex(RuntimeError, "Claude Code hata verdi: hata ayrintisi"):
            mdl.cagir("analiz", "x", cwd=self.cwd)
        self.sahte(json.dumps({"is_error": True, "result": "kota"}).encode())
        with self.assertRaisesRegex(RuntimeError, "Claude Code: kota"):
            mdl.cagir("analiz", "x", cwd=self.cwd)

    # ---- sır süzgeci her sağlayıcıda ----
    def test_sir_her_saglayicida_gizlenir(self):
        for sag, cikti in (("claude", self.cevap_claude()), ("codex", b""), ("gemini", b'{"response": "ok"}')):
            self.sec(sag)
            y = self.sahte(cikti, yaz=lambda arg: open(arg[arg.index("--output-last-message") + 1], "w").write("ok") if "--output-last-message" in arg else None)
            mdl.cagir("analiz", f"api_key={SIR} selam", sistem="rol", cwd=self.cwd)
            self.assertNotIn(SIR, y["istem"], sag)
            self.assertIn("[gizlendi]", y["istem"], sag)

    # ---- Codex ----
    def test_codex_komutu_ve_cikti(self):
        self.sec("codex", modeller={"codex": "gpt-ornek"})

        def yaz(arg):
            open(arg[arg.index("--output-last-message") + 1], "w", encoding="utf-8").write("  codex cevabi \n")
        y = self.sahte(b"gurultu", yaz=yaz)
        r = mdl.cagir("sohbet", "soru", sistem="ROL", oturum="a" * 24, oturum_kalici=True, cwd=self.cwd)
        a = y["arg"]
        self.assertEqual(a[:2], ["codex-yolu", "exec"])
        self.assertEqual(a[a.index("--sandbox") + 1], "read-only")
        self.assertEqual(a[a.index("--model") + 1], "gpt-ornek")
        for bayrak in ("--skip-git-repo-check", "--ephemeral"):
            self.assertIn(bayrak, a)
        self.assertEqual(a[-1], "-")
        for yasak in ("--resume", "resume", "--full-auto", "--dangerously-bypass-approvals-and-sandbox", "workspace-write", "danger-full-access"):
            self.assertNotIn(yasak, a)
        self.assertTrue(y["istem"].startswith("ROL") and y["istem"].endswith("soru"))   # sistem istemi öne eklenir
        self.assertEqual((r.metin, r.oturum), ("codex cevabi", ""))
        self.assertFalse(os.path.exists(a[a.index("--output-last-message") + 1]))   # geçici dosya silindi

    def test_codex_model_bos_ise_bayrak_yok(self):
        self.sec("codex")
        y = self.sahte(yaz=lambda arg: open(arg[arg.index("--output-last-message") + 1], "w").write("x"))
        mdl.cagir("analiz", "x", cwd=self.cwd)
        self.assertNotIn("--model", y["arg"])
        self.assertEqual(mdl.model_etiketi("analiz"), "codex:varsayılan")

    def test_codex_bos_yanit_ve_hata(self):
        self.sec("codex")
        self.sahte(yaz=lambda arg: None)
        with self.assertRaisesRegex(RuntimeError, "OpenAI Codex CLI: boş yanıt"):
            mdl.cagir("analiz", "x", cwd=self.cwd)
        self.sahte(rc=2)
        with self.assertRaisesRegex(RuntimeError, "OpenAI Codex CLI hata verdi"):
            mdl.cagir("analiz", "x", cwd=self.cwd)

    # ---- Gemini ----
    def test_gemini_komutu_ve_cikti(self):
        self.sec("gemini", modeller={"gemini": "gemini-ornek"})
        y = self.sahte(b'Uyari: bir sey\n{"response": "gemini cevabi", "stats": {}}\n')
        r = mdl.cagir("analiz", "soru", cwd=self.cwd)
        a = y["arg"]
        self.assertEqual(a[0], "gemini-yolu")
        self.assertEqual(a[a.index("--output-format") + 1], "json")
        self.assertEqual(a[a.index("--approval-mode") + 1], "plan")
        self.assertEqual(a[a.index("--model") + 1], "gemini-ornek")
        for yasak in ("--yolo", "-y", "auto_edit", "yolo"):
            self.assertNotIn(yasak, a)
        self.assertTrue(y["istem"].endswith("soru"))
        self.assertEqual(r.metin, "gemini cevabi")

    def test_gemini_hata_nesnesi_ve_duz_metin(self):
        self.sec("gemini")
        self.sahte(b'{"error": {"message": "kota doldu"}}')
        with self.assertRaisesRegex(RuntimeError, "Google Gemini CLI: kota doldu"):
            mdl.cagir("analiz", "x", cwd=self.cwd)
        self.sahte(b"duz metin")
        self.assertEqual(mdl.cagir("analiz", "x", cwd=self.cwd).metin, "duz metin")

    # ---- Ollama ----
    def sahte_http(self, durum=200, govde=None):
        yakalanan = {}

        class Baglanti:
            def __init__(self, *a, **kw):
                yakalanan["adres"] = a
            def request(self, yontem, yol, body=None, basliklar=None):
                yakalanan.update(yontem=yontem, yol=yol, body=json.loads(body) if body else None)
            def getresponse(self):
                yol = yakalanan["yol"]
                d = govde if yol == "/api/chat" else {"models": [{"name": "yerel:1b"}]}
                return mock.Mock(status=durum if yol == "/api/chat" else 200, read=lambda: json.dumps(d).encode())
            def close(self):
                pass
        mock.patch.object(mdl.http.client, "HTTPConnection", Baglanti).start()
        return yakalanan

    def test_ollama_yalniz_yerel_json_ve_model(self):
        self.sec("ollama")
        y = self.sahte_http(govde={"message": {"content": "{\"a\": 1}"}})
        r = mdl.cagir("analiz", "soru", json_cikti=True, cwd=self.cwd)
        self.assertEqual(y["adres"], ("127.0.0.1", 11434))
        self.assertEqual((y["yontem"], y["yol"]), ("POST", "/api/chat"))
        self.assertEqual(y["body"]["model"], "yerel:1b")   # ayar boşsa yüklü ilk model
        self.assertEqual(y["body"]["format"], "json")
        self.assertFalse(y["body"]["stream"])
        self.assertEqual(r.metin, '{"a": 1}')
        self.assertFalse(mdl.uzak_mi())
        mdl.cagir("analiz", "soru", cwd=self.cwd)
        self.assertNotIn("format", y["body"])

    def test_ollama_hata(self):
        self.sec("ollama")
        self.sahte_http(durum=404, govde={"error": "model bulunamadi"})
        with self.assertRaisesRegex(RuntimeError, "model bulunamadi"):
            mdl.cagir("analiz", "x", cwd=self.cwd)

    # ---- yetenek düşürme ----
    def test_veri_klasoru_claude_disinda_istem_icinde_verilir(self):
        veri = os.path.join(self.t.name, "kopya")
        os.makedirs(os.path.join(veri, "kisiler"))
        os.makedirs(os.path.join(veri, "gelen", "whatsapp"))
        open(os.path.join(veri, "kisiler", "ada.md"), "w", encoding="utf-8").write("# Ada gizli-not")
        open(os.path.join(veri, "gelen", "whatsapp", "x.txt"), "w", encoding="utf-8").write("ham sohbet")
        self.sec("gemini")
        y = self.sahte(b'{"response": "ok"}')
        mdl.cagir("strateji", "soru", sistem="ROL", veri_klasoru=veri, cwd=self.cwd)
        self.assertIn("### kisiler/ada.md", y["istem"])
        self.assertIn("gizli-not", y["istem"])
        self.assertNotIn("ham sohbet", y["istem"])
        self.assertNotIn(veri, y["arg"])   # dosya erişimi (dizin) hiçbir bayrakla verilmez
        self.assertNotIn("--include-directories", y["arg"])

    def test_ollama_veri_butcesi_kirpilir(self):
        veri = os.path.join(self.t.name, "kopya")
        os.makedirs(os.path.join(veri, "kisiler"))
        for i in range(5):
            open(os.path.join(veri, "kisiler", f"k{i}.md"), "w", encoding="utf-8").write("x" * 20000)
        özet = mdl.klasor_ozeti(veri, mdl.DOSYA_BUTCE["ollama"])
        self.assertLess(len(özet), 41000)
        self.assertIn("Veri bütçesi doldu", özet)

    def test_belge_okuma_yalniz_claude(self):
        for sag in ("codex", "gemini", "ollama"):
            self.sec(sag)
            with mock.patch.object(mdl, "hazir", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "belge okuyamaz"):
                    mdl.cagir("analiz", "x", okuma_klasoru=self.t.name, cwd=self.cwd)

    # ---- Y2: araçlı uzak sağlayıcılar boş cwd'de, Gemini'de araçlar kapalı ----
    def test_codex_ve_gemini_bos_gecici_klasorde_calisir(self):
        gorulen = []
        self.sec("codex")

        def yaz(arg):
            open(arg[arg.index("--output-last-message") + 1], "w").write("x")
        y = self.sahte(yaz=yaz)
        eski = mdl._calistir
        mock.patch.object(mdl, "_calistir", side_effect=lambda a, i, cwd, z, env=None: (gorulen.append((cwd, os.listdir(cwd))), eski(a, i, cwd, z, env))[1]).start()
        mdl.cagir("sohbet", "s", cwd=self.cwd, veri_klasoru=None)
        self.sec("gemini")
        self.sahte(b'{"response": "ok"}')
        mdl.cagir("sohbet", "s", cwd=self.cwd)
        self.assertEqual(len(gorulen), 2)
        for cwd, icerik in gorulen:
            self.assertNotEqual(os.path.realpath(cwd), os.path.realpath(self.cwd))   # Kut'un kendi klasörü değil
            self.assertEqual(icerik, [])                                              # boş
            self.assertFalse(os.path.exists(cwd))                                     # çağrı sonunda silindi
        self.assertNotEqual(y["cwd"], self.cwd)

    def test_gemini_araclar_politikayla_kapali(self):
        self.sec("gemini")
        kayit = {}

        def run(arg, **kw):
            pol = arg[arg.index("--admin-policy") + 1]
            kayit["politika"] = open(pol, encoding="utf-8").read()
            kayit["ayar"] = json.load(open(kw["env"]["GEMINI_CLI_SYSTEM_SETTINGS_PATH"], encoding="utf-8"))
            kayit["pol_yolu"], kayit["istem"] = pol, kw["input"].decode("utf-8")
            return subprocess.CompletedProcess(arg, 0, b'{"response": "ok"}', b"")
        mock.patch.object(mdl.subprocess, "run", side_effect=run).start()
        mdl.cagir("sohbet", "bak @C:/gizli/dosya.txt ve a@b.com", cwd=self.cwd)
        self.assertIn('toolName = "*"', kayit["politika"])
        self.assertIn('decision = "deny"', kayit["politika"])
        for arac in ("run_shell_command", "read_file", "read_many_files", "list_directory", "glob", "grep_search", "web_fetch", "google_web_search", "write_file"):
            self.assertIn(arac, kayit["ayar"]["tools"]["exclude"])
        self.assertIn("\\@C:/gizli/dosya.txt", kayit["istem"])   # @yol enjeksiyonu kaçışlı: Gemini dosyayı kendisi okuyup eklemez
        self.assertNotRegex(kayit["istem"].replace("\\@", ""), r"@C:")
        self.assertFalse(os.path.exists(kayit["pol_yolu"]))        # geçici yapılandırma silindi

    def test_arac_riskli_saglayici_onaysiz_secilemez(self):
        with mock.patch.object(mdl, "hazir", return_value=True):
            for sag in ("codex", "gemini"):
                for onay in (None, False, "evet", 1):
                    with self.assertRaisesRegex(ValueError, "Onay gerekli"):
                        mdl.ayarla({"saglayici": sag, **({} if onay is None else {"onay": onay})})
                self.assertEqual(mdl.secili(), "claude")   # reddedilen seçim kaydedilmedi
                self.assertTrue(next(p for p in mdl.durum()["saglayicilar"] if p["id"] == sag)["uyari"])
            self.assertEqual(mdl.ayarla({"saglayici": "ollama"})["secili"], "ollama")        # Ollama ve Claude onaysız
            self.assertEqual(mdl.ayarla({"saglayici": "claude"})["secili"], "claude")
            self.assertEqual(mdl.ayarla({"saglayici": "codex", "onay": True})["secili"], "codex")
            self.assertEqual(mdl.ayarla({"saglayici": "codex", "modeller": {"codex": "m"}})["secili"], "codex")   # aynı seçim: model adı onaysız değişir
            self.assertIn("Claude Code", mdl.ARAC_UYARISI)
            self.assertIn("Ollama", mdl.ARAC_UYARISI)
            u = {p["id"]: p["uyari"] for p in mdl.durum()["saglayicilar"]}
            self.assertIn("Codex", u["codex"]); self.assertNotIn("Gemini", u["codex"])   # her sağlayıcı yalnız kendi notunu taşır
            self.assertIn("Gemini", u["gemini"]); self.assertNotIn("Codex", u["gemini"])
            self.assertNotIn("{not}", u["codex"] + u["gemini"])
            self.assertEqual(u["claude"], ""); self.assertEqual(u["ollama"], "")

    # ---- O1: konuşma geçmişi ----
    def test_gecmis_saglayici_degisince_ve_kilitlenince_silinir(self):
        mdl.gecmis_ekle("o1", "s", "c")
        with mock.patch.object(mdl, "hazir", return_value=True):
            mdl.ayarla({"saglayici": "ollama"})
        self.assertEqual(mdl.gecmis_al("o1"), [])
        mdl.gecmis_ekle("o1", "s", "c")
        import ag_kilit
        mdl._kilit_bagla()   # test_kilit modülü ag_kilit'i yeniden yükleyebilir
        ag_kilit.kapat()
        self.assertEqual(mdl.gecmis_al("o1"), [])
        mdl.gecmis_ekle("o1", "s", "c")
        ag_kilit.kapat("yok-boyle-belirtec")
        self.assertEqual(mdl.gecmis_al("o1"), [])

    def test_gecmis_imza_degisince_silinir(self):
        mdl.gecmis_imza_denetle(("codex", ("a",)))
        mdl.gecmis_ekle("o1", "s", "c")
        mdl.gecmis_imza_denetle(("codex", ("a",)))
        self.assertEqual(len(mdl.gecmis_al("o1")), 1)
        mdl.gecmis_imza_denetle(("codex", ("a", "b")))   # kapı listesi değişti
        self.assertEqual(mdl.gecmis_al("o1"), [])

    def test_oturum_tip_denetimi_model_katmaninda(self):
        for kotu in (["a"], {"a": 1}, 5, b"x"):
            self.assertEqual(mdl.gecmis_al(kotu), [])
            mdl.gecmis_ekle(kotu, "s", "c")
        mdl.gecmis_ekle("ok", ["s"], "c")
        self.assertEqual(len(mdl._gecmis), 0)
        self.sec("claude")
        y = self.sahte(self.cevap_claude())
        mdl.cagir("sohbet", "s", oturum=["x"], oturum_kalici=True, cwd=self.cwd)   # liste oturum çökertmez, --resume eklenmez
        self.assertNotIn("--resume", y["arg"])

    def test_claude_sistem_istemi_sir_suzgecinden_gecer(self):
        y = self.sahte(self.cevap_claude())
        mdl.cagir("sohbet", "s", sistem=f"ROL api_key={SIR}", cwd=self.cwd)
        sistem = y["arg"][y["arg"].index("--append-system-prompt") + 1]
        self.assertNotIn(SIR, sistem)
        self.assertIn("[gizlendi]", sistem)

    def test_uzak_mi_arayuz_durumunda_kullanilir(self):
        d = {p["id"]: p["uzak"] for p in mdl.durum()["saglayicilar"]}
        self.assertEqual(d, {"claude": True, "codex": True, "gemini": True, "ollama": False})

    def test_gecmis_bellek_ici_sinirli(self):
        o = mdl.yeni_oturum_id()
        for i in range(30):
            mdl.gecmis_ekle(o, f"s{i}", f"c{i}")
        g = mdl.gecmis_al(o)
        self.assertEqual(len(g), mdl.GECMIS_TUR)
        self.assertEqual(g[-1], ("s29", "c29"))
        for _ in range(mdl.GECMIS_OTURUM + 3):
            mdl.gecmis_ekle(mdl.yeni_oturum_id(), "a", "b")
        self.assertLessEqual(len(mdl._gecmis), mdl.GECMIS_OTURUM)
        self.assertEqual(mdl.gecmis_al("yok"), [])


if __name__ == "__main__":
    unittest.main()
