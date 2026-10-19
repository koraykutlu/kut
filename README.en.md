# Kut

[Türkçe](README.md) · **English**

**Your personal network, only on your computer.** See the people you know on a photo map, jot down one sentence after every conversation,
and remember who you have been neglecting and who you should write to this week. No account, no cloud; your data sits on your disk as plain Markdown files.

Website: **[koraykutlu.github.io/kut](https://koraykutlu.github.io/kut/)** · Download: [latest release](https://github.com/koraykutlu/kut/releases/latest)

![Kut: map, person card, this week and Compass](docs/img/kut-demo.gif)

> **The interface is in Turkish.** This README describes it in English; button and menu names are given in Turkish with a translation,
> e.g. **Pusula** (Compass), so you can find them on screen. Kut was formerly called "Ağım" ("my network").

All screenshots and the GIF in this README (v1.1 interface) were taken with **fully fictional** data produced by `demo/demo_veri.py` (the person at the centre is "Deniz Demo"), with the fictional import samples under `demo/ornek/` and with the in-app demo "Deniz'in salısı" (Deniz's Tuesday); there are no real people in them.

## Contents
[What it does](#what-it-does) · [Privacy](#privacy) · [Installation](#installation) · [Updating](#updating) · [Trying it with demo data](#trying-it-with-demo-data) ·
[Usage details](#usage-details) · [Supported schools](#supported-schools) · [Adding a school adapter](#adding-a-school-adapter) · [Tests](#tests) · [Licence](#licence)

## What it does

### Network map
You at the centre, the people you know around you. Colour shows a person's type (academia, work, close, circle, event, finance, politics) and the ring shows closeness;
links are drawn by type: friendship, mentorship, manager, business partner, family, rivalry or tension.
The **Dikkat** (Attention) list in the left panel flags possible conflicts of interest from the links (e.g. an acquaintance at a rival company, a tense triangle).
When your network grows (48+ people) the map arranges itself: closeness becomes concentric rings (strong ties inside), type becomes angular slices ("Akademi · 42"), and positions stay the same on every launch; names appear as you zoom in and never overlap,
person-to-person links are faint, and hovering over or selecting someone brings their neighbourhood forward. A person you drag stays where you put them; the ↺ button puts everyone back. Clicking a slice zooms into it.
Small networks (up to 47 people) keep the warm, force-directed view. To try a crowded network: `py -3 demo/kalabalik_veri.py --kisi 400 --hedef FOLDER` (fictional names).

![Network map](docs/img/harita.png)

### Person card and contact rhythm
Every person is a Markdown file: organisation, role, "why they matter", "what I can offer", next step and its date. After a conversation you add a one-sentence
**contact** (temas); last contact, the meeting frequency you declared and a closeness-based neglect threshold (closeness 3: 14 days, 2: 30, 1: 60) are computed from it.
Six relationship scores (warmth, depth, reciprocity, continuity, bridge, common ground) and optional trait scores (expertise, support, reliability...)
are calculated from your records; the "Puanlar neye göre?" (What are the scores based on?) section shows the criteria.

| Profile and traits | Contacts and timeline |
|---|---|
| ![Person card](docs/img/kisi-karti.png) | ![Contacts](docs/img/kisi-temaslar.png) |

### Promises
A promise you gave someone or received from them ("I'll send Ayşe the book", "Mehmet will forward me the internship post") is kept in the **Sözler** (Promises) tab of the person card:
direction, text, optional due date; *Tamamla* (Complete) or *İptal* (Cancel). The source is the `## Sözler` section of the person file:
`- [ ] 2026-10-13 · ben → o · kitabı göndermek (son: 2026-10-17)` (`ben → o` = you gave it, `o → ben` = they gave it; completed is `[x]` with `(tamam: DATE)`, cancelled is `[-]` with `(iptal: DATE)`;
a cancelled line is never deleted, and a copy is saved to `arsiv/surum/` before every write). Overdue promises, or ones due within 7 days, appear in the **Bu hafta** (This week) list with a "söz" (promise) tag,
e.g. "the promise you gave: 2 days overdue"; they do not mix with Compass moves.

![Promises tab on a person card](docs/img/kisi-sozler.png)

If you type "I'll send Ayşe the book on Friday" into **Kut'a sor** (Ask Kut), Kut parses the person, direction, text and date (tomorrow, Friday, next week, end of month, in 3 days, 17 October...) locally and
asks **"Shall I add this as a promise to Ayşe? (due: 16.10)"**; nothing is written until you confirm. Questions, negative, past and conditional sentences (and ambiguous names) produce no suggestion. Promises are part of the person file,
so they reach a remote model only through the privacy gate; if the person is set to **🔒 Bu kişi yapay zekâya gönderilmez** (Never send this person to AI), they never go.

### This week
Next steps that are due, people you are neglecting and overdue/upcoming promises in one list; one click highlights only them on the map. People on the exclusion list never appear in any suggestion.

![This week view](docs/img/bu-hafta.png)

### How do I reach them? Introduction paths
When you want to reach someone (a professor, someone at a company, anyone in a field), the **↗ Nasıl ulaşırım?** (How do I reach them?) button on the person card finds the warmest path through your network: who knows whom, who makes the first move, what you will write.
The side panel shows the chain (You → Baran → Prof. Selin), the strength of each link, the reasoning ("You are close to Baran; last contact 3 days ago"), cautions ("You haven't talked to Baran in 90 days; warm the tie up before asking for an introduction") and a copyable message draft; the path is highlighted on the map and the rest fades.
The *Amaç* (Goal) field rewrites the draft, and *Bu adımı takip et* (Track this step) saves the suggestion to **Pusula → Sonuçlar** (Compass → Outcomes). You can also search by organisation or field instead of a name (**Pusula → Ulaş** (Reach): «Şişecam», «finance»). The calculation is fully local; people on your exclusion list never enter a path.

### Meeting brief
Before you call or meet someone, **Brifing** (Brief) on their card prepares a single page: your relationship, recent conversations, open promises (overdue first), next step, mutual acquaintances, topics you could bring up and what Kut has suggested for this person before. It copies as Markdown, or you can print only the brief.

### Kut comes to you: weekly digest and "How did it go?"
The first time Kut opens each week, if it has something to say, it shows a digest: at most three people who need your attention this week (why, one concrete step, a ready-to-send draft) and the promises you made. You answer *Yaptım / Ertele / Atla* (Done / Postpone / Skip), and a few days later it asks *did it work?*; suggestions adjust to your answer (someone you skipped twice is left alone for four weeks; a path that failed twice is replaced by another). The *Temas olarak kaydet* (Save as contact) box adds a line to the person's contact history.
You can always return to the digest from **Bu hafta → Haftanın özeti** (This week → Weekly digest) in the left panel. Records live in `veri/sonuclar.md` (a readable table you can also edit by hand) and `veri/ozet/`; the numbers for the last 8 weeks are in Pusula → Sonuçlar.

### Notifications even when Kut is closed (optional)
If you turn on ⚙ Ayarlar → **Kut sana gelsin** (Settings → Let Kut come to you), a scheduled task is installed on your computer (Windows Task Scheduler, macOS launchd, Linux systemd) that shows a system notification once a week (or every morning, only on days with something to show). **It is off by default**, and turning it off removes the task. The notification carries only counts («3 people and 1 promise are waiting for you this week»); names have a separate switch whose warning you should read: names may appear on the lock screen and in the notification centre, bypassing Kut's PIN lock. Note, promise and draft text never enter a notification. None of this goes online.

### Inference approval queue ("The assistant asks")
The assistant's (AI) inferences about people (relationship summary, tag, score, link, organisation/role, questions) are **never written to the person file unless you approve them**.
For each one you say *Doğru / Düzelt / Yanlış* (Right / Correct it / Wrong); a rejected inference is never suggested again. What you state directly (opinion, meeting frequency)
takes precedence over inferences and is never overwritten by them. A rule engine (`ag_tutarlilik.py`, no model) closes, without deleting, suggestions that contradict their context.

### Compass: goals, discovery, strategy
You write your goals (title, type, deadline, priority, success criterion, topic keywords); you add progress lines, complete and archive them.
The *Keşfet* (Discover) tabs match public sources (Turkish Parliament (TBMM) member activity, schema.org event pages) against your goals' keywords;
nobody enters your network until you click "Ağa ekle" (Add to network). Parliament data (Vekilpedia) and event scanning are **off** in a new installation; you turn them on in ⚙ Ayarlar → *Kaynaklar* (Settings → Sources) (or `ayarlar.json` → `kesif.vekilpedia` / `kesif.etkinlik: true`). Older installations that already downloaded data keep them on so they don't lose the feature. *Stratejik okuma* (Strategic reading) has a model read your goals and network and produce evidence-backed, goal-linked "moves you haven't seen".

| Moves | Goals |
|---|---|
| ![Compass, moves](docs/img/pusula-hamleler.png) | ![Compass, goals](docs/img/pusula-hedefler.png) |

> The "Strategic reading" content in the screenshots is sample text written by the demo data generator; no model was called.

The Compass is always in sight: a highlighted **◎ Pusula** button in the top bar (shortcut **P**) and a **Compass card** at the top of the left panel. The card shows your active goals, this week's next move (the first move from the strategic reading, with its first step and first piece of evidence) and a button that opens the Compass. Without a goal it says *İlk hedefini yaz* (Write your first goal); if no strategy has been drawn up yet it says *Bu haftanın stratejisini çıkar* (Draw up this week's strategy); the latter asks for confirmation first, because it goes to the selected AI provider (provider choice, the person gate and the secret filter all apply). The Compass window holds only the *Moves, Goals, Discover · Parliament, Discover · Events* tabs; the source, school, update, voice and vault cards are in the ⚙ **Ayarlar** (Settings) window.

### First launch: setup and tour
After you set your first PIN, Kut opens a wizard once; it does the setup first, then introduces the features. The welcome step greets you by the first name in your profile with a short line that depends on the time of day; the *Önce bir örnekle göster* (Show me an example first) button plays a fictional network ([Trying it with demo data](#trying-it-with-demo-data)). Each setup step can be skipped, and the ones already known (saved name and photo, selected provider, installed voice, imported vault people, school and courses) are skipped automatically; *Hazır olanları da gez* (Visit the finished ones too) shows them all: (1) your name and who you are (My profile fields), (2) the AI provider (Claude Code recommended; choosing Codex/Gemini shows a privacy warning and asks for confirmation; uninstalled ones are greyed out), (3) voice (the Whisper + EMA Lightning install question; *Şimdi değil* (Not now) is an option), (4) *Kasadan kişileri al* (Import people from the vault) if a vault is connected (otherwise the step is hidden), (5) school and courses, and a pointer to the Import window. Then the **spotlight tour** starts: the introduced element stays in its own colour at full brightness while everything else is dimmed by a dark overlay; the card next to it has a title, a short explanation, *Geri / İleri / Turu bitir* (Back / Next / Finish tour) and a step counter (keyboard: ← → Esc; transitions are off when `prefers-reduced-motion` is set). Order: network map, person card, Promises, the "Never send this person to AI" switch, Verify ("The assistant asks"), This week, Ask Kut and voice input, Compass, Import, Settings, Lock. If the target is not on screen (empty network, narrow window) the step is skipped silently; a closed panel opens for the tour and returns to its previous state afterwards. Completion is stored in settings (`ayarlar.json` → `sihirbaz.bitti`; the writing endpoint is `/api/sihirbaz`: lock + key + local Origin). Closing the wizard also counts as "done"; ⚙ Ayarlar → *Kurulum ve tanıtımı aç* (Open setup and tour) (or *Yalnız özellik turu*, Feature tour only) reopens it at any time. Adding a tour step means adding one line to the `TUR_ADIMLARI` array in `kut/ag_sablon.html` (`id`, target selector `hedef`, `baslik`, `metin`).

| Welcome step | AI provider step |
|---|---|
| ![Wizard, welcome](docs/img/sihirbaz-karsilama.png) | ![Wizard, AI provider](docs/img/sihirbaz-yapay-zeka.png) |

### Other features
- **Import (WhatsApp, contacts, calendar, LinkedIn, course list):** drop a WhatsApp chat (.txt/.zip, "without media"), a .vcf address book, a calendar export (.ics), a LinkedIn data copy (Connections.csv / messages.csv) or a course list copied from your school into the *İçe aktar* (Import) window; you first see what will happen (the preview writes nothing), then you confirm. Message contents, meeting descriptions and locations are not stored; only who, when and which channel. Details: [Usage](#usage-details).
- **School adapter:** from the school and courses in your profile it fills in your professors, class times and, from the staff page, title/e-mail/CV (with the source, only into empty fields). It is off when no school is set; you pick from the [supported schools](#supported-schools), and if yours isn't there an adapter can be added ([below](#adding-a-school-adapter)). Writing "this term I'm taking ISE 424, ISE 426 and MATH 101" in My profile is enough: the courses are saved to your profile. In Ask Kut the same sentence is not written straight away; Kut answers your question and shows a confirm button in the chat asking "Shall I add ISE 424, ISE 426 and MATH 101 to this term's courses?" (questions, negative and past sentences, month/day names and money amounts are not counted as courses). After you confirm, your professors are added automatically if a school is selected (if not, Kut first asks which school you attend). Professors added from a school source start at closeness 0; only you raise it.
- **Kut'a sor (Ask Kut, `/`):** splits free text like "Talked to Prof. Ayşe today, my application was approved, Berk and I now meet once a week" into contacts, statements, next steps and links and saves them; before every write the person's previous version is copied to `veri/arsiv/surum/`.
- **PIN lock:** a PIN is asked at launch; while locked the server sends no personal data at all (not a visual overlay, enforced on the server side).
- **Second brain bridge (optional, read-only):** shows open tasks from a notes vault and the lines where a person is mentioned; writes nothing to the vault.
- **Local voice (optional):** Whisper turns speech into text, EMA Lightning reads answers aloud in Turkish; everything runs on this computer and no audio is written to disk. If they are not installed, Kut offers to download them with your consent (sizes are shown beforehand).
- **AI provider:** Claude Code (recommended), Codex CLI, Gemini CLI or local Ollama; chosen in the wizard or in Profilim → *Yapay zekâ sağlayıcısı* (My profile → AI provider). Kut neither asks for nor stores API keys; details and limits in [Privacy](#privacy).
- **Look and feel:** a WebGL sky drawn on this computer that follows your computer's clock (night, dawn, sunrise, noon, golden hour, blue hour), day/night theme; short interface sounds on window and tab changes (⚙ Ayarlar → *Arayüz sesleri*, Interface sounds; on by default, can be turned off).

Import previews (with the fictional `demo/ornek/takvim.ics` and `demo/ornek/linkedin-Connections.csv`; the preview writes nothing):

| Calendar (.ics) | LinkedIn (Connections.csv) |
|---|---|
| ![Import, calendar preview](docs/img/ice-takvim.png) | ![Import, LinkedIn preview](docs/img/ice-linkedin.png) |

The ⚙ **Ayarlar** (Settings) window in the top bar gathers setup and tour, interface sounds, optional external sources, the school adapter, updates and voice (and the vault card if a vault is connected) in one place:

![Settings window](docs/img/ayarlar.png)

![Lock screen](docs/img/kilit.png)

## Privacy

**Principle: Kut runs only on your computer.** No cloud, account, sync, mobile app or telemetry. The server listens only on `127.0.0.1`
(not reachable from outside; Host/Origin are checked) and stops by itself ~20 minutes after the page is closed.
Your data lives in the `veri/` folder as plain Markdown and is excluded from the repository by `.gitignore`; import candidates wait under `%LOCALAPPDATA%\agim` (macOS/Linux `~/.agim`).

**Kut does not go online unless you turn something on.** No external source is enabled in a new installation. The ⚙ **Ayarlar** window in the top bar (Sources cards) shows, in one place, the optional sources you can turn on, what they download and from where, with on/off switches (the Compass holds only goals, discovery and strategy):

| Source | What it downloads | From | Default |
|---|---|---|---|
| TBMM / Vekilpedia | members of parliament, parliamentary questions, bills (CSV, CC BY 4.0), weekly | vekilpedia.com | off |
| Events | upcoming event pages (robots.txt permitting), every 12 hours | coderspace.io, lu.ma, eventbrite.com, devpost.com (+ the selected school's event page) | off |
| School adapter | timetable, academic staff page (only if your profile has a school and course codes) | your chosen school's public website ([table](#supported-schools)); at least 0.5 s between requests | none |
| Academic profiles | organisation, publication count and research areas of professors added from your school (only the professor's name is sent; results land in Verify as suggestions) | api.openalex.org, pub.orcid.org | off |

**Paths that can reach the network.** These are all the paths through which Kut can go online; each one is off by default or depends on your explicit consent, and there is no path that isn't on this list:

| Path | Where | When |
|---|---|---|
| Update check | api.github.com (GET only, no data sent) | weekly if you answer *Yes* to the first-launch question; the button works manually |
| Voice installation | PyPI (packages), Hugging Face (models) | only if you say *Yes* to the install offer (`onay: true`); offline afterwards |
| School websites | your chosen school's public website | when a school is selected, your profile has courses and you click "Kaynaktan doldur" (Fill from source) |
| OpenAlex / ORCID | api.openalex.org, pub.orcid.org (professor's name only) | if `kesif.akademik` is on (off in a new installation) |
| Vekilpedia | vekilpedia.com | if `kesif.vekilpedia` is on (off in a new installation) |
| Events | the event sites in the table | if `kesif.etkinlik` is on (off in a new installation) |
| Remote model providers | Anthropic (Claude Code), OpenAI (Codex), Google (Gemini); local Ollama goes nowhere | only when you use analysis / "Ask Kut" / strategy; choosing Codex or Gemini asks for extra confirmation |

**What never goes online.** Imports (WhatsApp, contacts, calendar .ics, LinkedIn CSV/ZIP, pasted course lists) are processed entirely locally on this computer; they are not on the list above because they make no requests at all (for calendar and LinkedIn there is no account connection, secret calendar URL or scraping). Instructions inside a source file are data, not commands. **A developer tool that is not part of the app:** `paketleme/demo_seslendir.py` generates the demo narration once before a release with Google Gemini TTS (the key is read only from the `GEMINI_API_KEY` environment variable; only the fixed demo texts are sent, no person data); it is not included in `Kut.exe` or the running app, and Kut never runs it. The ready-made audio files (`kut/demo_ses/`) ship with the app only to be played.

Details and limits:

1. **Public pages** (table above). Only public pages that require no login are downloaded; none of your network's information is sent with these requests. In older installations that already downloaded data, Vekilpedia and Events count as on; you turn them off in the Sources tab.
2. **Optional AI assistant.** Analysis, "Ask Kut" and strategic reading go to a model through an AI command-line tool installed on your computer (default and recommended: **Claude Code**, `claude -p`; alternatives below).
   If the selected provider (Claude Code, Codex CLI, Gemini CLI or local Ollama) is not installed or not working, these features don't work (the buttons show a Turkish warning naming the selected provider); everything else does. They run only when you use them, with one exception: if the selected provider is ready and you have **an approved (active) goal**, Kut starts the strategic reading by itself at launch once 7 days have passed since the last one. To turn this off: `ayarlar.json` → `"otomatik_strateji": false`. Every piece of person data that goes to a model first passes a local **gate** (`ag_kapi.py`):
   - a person with `remote_allowed: false` (or whose file cannot be read) is present neither in the prompt nor in the temporary data copy prepared for the model. The **🔒 Bu kişi yapay zekâya gönderilmez** (Never send this person to AI) switch on the person card writes/removes this field (a version copy is saved before the write, and the in-memory chat history is cleared immediately); while it is on, a badge appears on the card and "✦ Analiz" (Analyse) and document summarising are disabled for that person (documents are only stored locally);
   - people from organisations/parties matching `veri/haric.md` are left out the same way; the copy also contains no `haric.md`, `ag.html`, `arsiv/`, lock or settings files;
   - the **secret filter** (`ag_sir.py`) turns values such as keys, tokens and passwords (including encoded forms) into `[gizlendi]` (hidden);
   - **with Claude Code**, Kut restricts the tools: file tools are read-only and limited to the filtered temporary copy; write, shell and web tools are off; the copy is deleted on exit. **Codex and Gemini have no such guarantee:** see *The limit of tool-using providers* below.
   - for session-less providers (Codex, Gemini, Ollama) the in-memory chat history passes through this gate and the secret filter again on every turn; it is cleared on lock, on a provider change, or when the gate list (`haric.md`, `remote_allowed`) changes.
   Claude models can be changed in `ayarlar.json` (`analiz_modeli`, `sohbet_modeli`, `strateji_modeli`).

   **Which AI?** Kut is not tied to a single provider; the best option changes over time. You choose in Profilim → *Yapay zekâ sağlayıcısı* (or `ayarlar.json` → `"saglayici"`).
   All of them are command-line tools installed on your computer that manage their own sign-in; **Kut neither asks for nor stores API keys**. Claude Code is recommended (Kut was developed and tested with it).

   | Provider (`saglayici`) | Command | Where data goes | Notes |
   |---|---|---|---|
   | `claude` (default, **recommended**) | `claude -p` | Anthropic | Session resume, read-only file tools and PDF/image document reading fully work |
   | `codex` | `codex exec` | OpenAI | `--sandbox read-only` blocks writing but **not reading**; runs in an empty temporary folder; asks for confirmation when chosen; "Ask Kut" resends the context every turn; does not read PDF/image documents |
   | `gemini` | `gemini -p` | Google | `plan` mode + an "all tools denied" policy, empty temporary folder; asks for confirmation when chosen; "Ask Kut" resends the context every turn; does not read PDF/image documents |
   | `ollama` | local HTTP `127.0.0.1:11434` | **never leaves your computer** | Results can be weak with small models; the data budget is limited |

   Kut gives no file tools to providers other than Claude; for strategy and "Ask Kut" the text of the gated data copy goes inside the prompt. No provider is ever given write access.

   **The limit of tool-using providers (Codex, Gemini): the gate only filters the data Kut sends.**
   - In Codex, `--sandbox read-only` blocks writing but not reading: through shell commands the model can read the whole disk, the real person folder and the people in `haric.md`. The `-c` switches that would disable Codex's shell or tools could not be verified from the official documentation (github.com/openai/codex), and Codex is not installed on this machine so they could not be tested; therefore no made-up flags are used.
   - In Gemini, `--approval-mode plan` leaves read-only tools (file reading, search, web) enabled. Kut additionally passes a `deny` rule for `*` through `--admin-policy` (according to the Gemini CLI 0.62 documentation a global deny also removes tools from the model's view), sets a `tools.exclude` fallback through `GEMINI_CLI_SYSTEM_SETTINGS_PATH`, and escapes `@path` expressions in the prompt (which Gemini would read and attach itself). This configuration was verified from the source code and documentation, but could not be tested in a live model call because the Gemini account on this machine could not sign in (IneligibleTierError).
   - Both run in an empty temporary folder, but that is a precaution, not a boundary: an instruction embedded in a document could read data outside the gate and send it away. That is why **choosing Codex or Gemini requires explicit confirmation** ("These tools can read files on disk with their own tools; Kut's person gate only filters the data Kut sends. For sensitive networks, Claude Code (whose tools Kut restricts) or local Ollama is recommended."); a selection without confirmation is rejected (`POST /api/saglayici` → `onay: true`).
   The gate (`ag_kapi.py`) and the secret filter (`ag_sir.py`) work the same whichever provider is selected; everything except Ollama counts as "remote". A provider that is not installed cannot be selected.
   For non-Claude providers the model name is set in `ayarlar.json` → `"modeller": {"codex": "...", "gemini": "...", "ollama": "..."}`; if empty, the tool's own default (for Ollama, the first installed model) is used.
3. **Version check (GitHub).** A single GET goes only to `api.github.com/repos/koraykutlu/kut/releases/latest` to fetch release information; no data is sent. The automatic check runs weekly only if you answer **Yes** to the question asked at first launch (`ayarlar.json` → `guncelleme.otomatik`; never without asking, never if you say No). The Settings → Sources → *Güncelleme var mı?* (Is there an update?) button always works manually.
4. **Voice installation (Whisper + EMA Lightning).** The first time you tap 🎙 or 🔈 (or in Settings → Sources → *Sesli iletişim*, Voice) Kut asks; nothing is downloaded unless you say **Yes**. If you do, only PyPI (pinned-version packages) and Hugging Face (model files) are contacted; no audio, text or person data is sent. After installation the voice workers run offline. Details: *Voice* below.
   **Installation security and its limits:** `pip` runs isolated (`python -I`, `pip --isolated`; `PIP_INDEX_URL`, `PIP_EXTRA_INDEX_URL`, `PIP_TRUSTED_HOST` and `pip.ini` in the environment are ignored, `HF_ENDPOINT` is not passed on). `ema-lightning 1.1.2` and `normalizer-tr 0.7.0` are pinned to sha256 with **`--require-hashes`** (values taken from the PyPI JSON API). These two packages were published on 10–11 October 2026, i.e. they are **very new**; you accept trusting their publishers. Because the wheel lists of `torch`, `faster-whisper`, `ctranslate2` and the CUDA libraries are very large per platform, they are pinned by version only (no hash), and their dependencies (e.g. `huggingface-hub`, `numpy`) come from PyPI unpinned. Models are pinned to a Hugging Face **commit sha** (`revision=<sha>`: EMA `7a6ba1a…`, Whisper small `536b066…`, medium `08e178d…`, large-v3 `edaa852…`); the same files are downloaded even if the repository changes later. If the installation is cancelled or fails, partial model downloads (including `.incomplete`) are deleted; if something cannot be deleted, the message says so.
5. **Your choice: your own AI agent.** If you open this folder with an agent (e.g. Claude Code), the files the agent reads go to that agent's model; tell it to read only what the task needs.

**Lock (`ag_kilit.py`):** the PIN is never stored in plain text (PBKDF2-SHA256, `ayarlar.json` → `kilit`); after 5 wrong attempts the waiting time grows; while locked every `/api` request returns 401.
Kut locks when it restarts, after the configured idle time (default 15 min) or with 🔒. If you forget your PIN, delete the `"kilit"` key from `ayarlar.json`.
The lock protects the screen; the Markdown files on disk need disk encryption (BitLocker, FileVault).
The people you write into your network are your notes: don't write health details, private life or gossip; don't share the folder with others.

## Installation

Python 3 (standard library) is all you need; no external packages. Voice is optional: with your consent Kut can install the Whisper / EMA environment itself (requires Python 3.11–3.13 on the system).

### Windows (.exe)

No Python needed.

1. Download `Kut.exe` from the GitHub **Releases** page and double-click it.
2. If Windows shows an "unknown publisher" (SmartScreen) warning: **More info → Run anyway**.
3. On first launch you set a **PIN**.

Your data lives as Markdown in the `Documents\Kut` folder; settings and logs are under `%LOCALAPPDATA%\agim`. For another folder: `Kut.exe --veri FOLDER`.
Voice (Whisper / EMA) and AI analysis (Claude Code) are optional; for voice Kut offers a download with your consent (because pip cannot run from inside Kut.exe, Python 3.11–3.13 must be installed on your computer; otherwise it shows [python.org/downloads](https://www.python.org/downloads/)). If Claude Code is not installed, the related buttons show a Turkish warning and everything else works.

To build it yourself: `powershell -ExecutionPolicy Bypass -File paketleme\paketle.ps1` (output `build-exe\dist\Kut.exe`).

### Install with your AI agent

If you have Claude Code, Codex or a similar agent, you can let it do the installation. Just tell the agent:

> `Install Kut from https://github.com/koraykutlu/kut.`

The agent follows the "Kurulum (ajan için)" (Installation, for the agent) section of [AGENTS.md](AGENTS.md) in the repository: it checks for Python 3.10+ (on Windows, suggests `Kut.exe` if missing),
clones the repository, puts **your personal data in a folder outside the repository** (e.g. `<vault>/notes/ag` or `~/Documents/Kut`), installs the desktop/Start shortcut on Windows,
and, if you want, connects your second-brain vault through the read-only bridge. It does not turn on external sources without your consent and never puts your data in the repository.

The agent does **not move** people from your vault into Kut by hand and does not generate placeholder/avatar/initial images for people: if there is no photo, `foto` stays empty and Kut draws a filled square in the type colour.
To import `kind: person` notes from the vault, use Settings → Sources → **Kasadan kişileri al** (Import people from the vault) (or the vault step of the first-launch wizard) (see "Second brain bridge" below).

### With Python

Install Python 3 (Windows: `winget install Python.Python.3.12` or python.org, with "Add to PATH" ticked), download/clone the repository, then:

```powershell
# Windows
py -3 kut.pyw
```
```sh
# macOS / Linux
python3 kut.pyw
```

By default the server opens at `http://127.0.0.1:47318/` and opens the browser (`--tarayicisiz` keeps the browser closed, `--port N` changes the port,
`--veri FOLDER` uses another data folder; the `AGIM_PORT` environment variable also sets the port, `--port` takes precedence).

- **Windows shortcut:** right-click `baslatma\kur.ps1` → *Run with PowerShell* (to keep your data in another folder: `powershell -ExecutionPolicy Bypass -File baslatma\kur.ps1 -Veri FOLDER`). A **Kut** shortcut appears on the desktop and in the Start menu; Kut opens in an Edge/Chrome app window (separate profile). For your default browser, write `"tarayici": "varsayilan"` into `ayarlar.json`.
- **macOS:** run `chmod +x baslatma/Kut.command` once in Terminal, then double-click `baslatma/Kut.command` (Python 3 required: `python3 --version`).

On first launch you set a PIN; then the setup wizard asks for your name, your AI provider and the other optional steps (all can be skipped, see *First launch: setup and tour*). To change them later, click your own node at the centre → **Profilimi düzenle** (Edit my profile) (name, photo, your assistant's name).

## Updating

The version number and update check are in the **Settings → Sources → Update** card (the version lives in `kut/surum.py`). On first launch Kut asks once: *"Shall I check for updates once a week?"*; if you say Yes it fetches only the release information from GitHub once a week, if you say No it never looks by itself. The *Güncelleme var mı?* (Is there an update?) button always works manually. An update changes only the program and never touches the data folder; the previous program is kept so you can go back.

- **Kut.exe:** *Şimdi güncelle* (Update now) downloads the new `Kut.exe` from GitHub Releases (at most 50 MB; only from github.com and GitHub's release CDN addresses), **verifies the SHA-256 checksum** (the release's `digest` field or the `Kut.exe.sha256` file; it won't install if the checksum is missing or doesn't match), puts the old one next to it as `Kut.prev.exe`, makes the new one `Kut.exe` and restarts. *Önceki sürüme dön* (Back to the previous version) swaps the two back. If Kut.exe's folder is not writable (e.g. Program Files), download it by hand.
- **Git installation:** updates the repository with `git fetch --tags` and **only fast-forwards** (`git merge --ff-only`, to the release tag). If the working tree is dirty, local commits prevent a fast-forward, or the folder doesn't track `github.com/koraykutlu/kut`, it touches nothing and only announces the new version. The previous commit is recorded; *Önceki sürüme dön* (`git reset --hard`, only if the tree is clean) brings it back. By hand: `git pull --ff-only`.
- **Zip / copy:** only a notification and a link to the release page; copy the new files over, except `veri/`.
- **Data migration:** if a release changes the data format, `kut/goc.py` runs the required migration and first zips the data folder under `<veri>/arsiv/goc/`. There are no migrations yet; nothing is written.

**For those making releases:** bump `SURUM` in `kut/surum.py`, run `paketleme\paketle.ps1`, create a GitHub Release tagged `vX.Y.Z` and upload **both `build-exe\dist\Kut.exe` and `Kut.exe.sha256`** (the file names must be exactly these; the tag must equal `SURUM`). The release must not be a *pre-release/draft* (`releases/latest` doesn't see those).

## Trying it with demo data

**In-app demo ("Deniz'in salısı", Deniz's Tuesday).** To see it without setting anything up, use the **Önce bir örnekle göster** (Show me an example first) button in the welcome step of the first-launch wizard or in ⚙ Ayarlar → *Kurulum ve tanıtım* (Setup and tour). Six scenes play out in a fictional person's network: the network, a cooled tie the Compass noticed, Ask Kut, promise capture, the tie warming up again, and the lock. It uses the same engine as the spotlight tour. It never touches your data or your settings folder: the demo runs with a separate data copy in a temporary folder, which is deleted when you close it, when the lock closes, after 45 minutes idle or on exit. It goes neither online nor to a model ("Ask Kut" answers are prepared in advance, promise capture is the local rule engine). Narration is optional: if there are audio files under `kut/demo_ses/` they play, otherwise the demo runs silently.

| The Compass noticed | You made a promise, Kut caught it | The tie warmed up again |
|---|---|---|
| ![Demo, Compass](docs/img/demo-sali-pusula.png) | ![Demo, promise capture](docs/img/demo-sali-soz.png) | ![Demo, tie warmed up](docs/img/demo-sali-isinma.png) |

To try it without entering your own data (or to take screenshots/videos), `demo/demo_veri.py` generates 31 fictional people (two of them indirect), relationships, pending inferences,
two goals and a sample strategic reading. All names and organisations are made up; the people have no photos, and the map draws them as filled squares with initials in their type colour.
Dates are generated relative to today, so the "This week" list is always full. To try importing, you can drop the fictional files `demo/ornek/takvim.ics` and `demo/ornek/linkedin-Connections.csv` into the *İçe aktar* (Import) window (the names match this demo data; their dates are fixed; the preview writes nothing, writing happens only with *Onayla ve yaz*, Confirm and write).

```powershell
py -3 demo/demo_veri.py --hedef "$env:TEMP\kut-demo"        # without --hedef a temporary folder is created and its path printed
py -3 kut.pyw --veri "$env:TEMP\kut-demo" --port 47400
```

So that it doesn't affect your own installation, you can run the demo with a separate settings folder (PIN and settings live under `%LOCALAPPDATA%\agim`, macOS/Linux `~/.agim`):

```powershell
$env:LOCALAPPDATA = "$env:TEMP\kut-demo-ayar"
py -3 kut.pyw --veri "$env:TEMP\kut-demo" --port 47400
```

If you want the demo to stay offline with model calls off, write
`{"otomatik_strateji": false, "otomatik_analiz": false, "kesif": {"etkinlik_kaynaklari": [], "vekilpedia": false}}` into `kut-demo-ayar\agim\ayarlar.json`
(so Compass discovery goes to no site and no model is called). On first launch you set your own PIN.

## Usage details

- **+ Kişi ekle / Düzenle (Add person / Edit):** photo, name, type, closeness (0 don't know them · 1 we've messaged · 2 we've met · 3 strong), organisation, contact details,
  next step + its date, "why they matter", "what I can offer".
- **Temas ekle (Add contact):** one sentence after every conversation with the person; last contact and the "This week" list update accordingly.
- **Your statement:** in the edit window, "Ne sıklıkla görüşüyorsunuz?" (How often do you meet? — every day / weekly / monthly) and "Senin görüşün" (Your opinion).
  Even if you keep no records, scores are calculated from this; the assistant's inferences never overwrite it.
- **Bağ kur (Link people):** on the map, **Shift + drag** from one person to another (or *Bağ kur* on the card → click the target), and pick the type with one click:
  friend, works with, mentor, manager, business partner, relative, partner, rival, tension.
- **Asistan soruyor / Doğrula (The assistant asks / Verify):** *Right / Correct it / Wrong* for every inference; answer the questions too. Your answers guide later analyses.
- **Photo:** after uploading, choose the visible part by dragging and zooming; click an existing photo to crop it again.
- **Left panel:** hide/show it with the handle on the edge or the `[` key.
- **CV and documents:** drop a CV, profile page, news article, PDF or screenshot into the person's *Özgeçmiş* (CV) tab
  (or paste the text). The assistant summarises it; the summary, CV items, organisation/role and contact details land in *Doğrula* (Verify) and are written once you approve.
  The file stays in `veri/belgeler/<person>/`; its content goes to the assistant's model for the summary (through the gate).
- **Kut'a sor (Ask Kut, bottom bar, `/`):** ask your network a question or tell it something; you can write about several unrelated people in a row. The assistant separates them
  and saves them to the right people as contacts, statements, opinions, meeting frequency, next steps, contact details or links; it opens new people. What you say
  is a statement and is written directly; if a name is ambiguous it asks. The assistant's own inferences still land in Verify.
- **Your assistant's character:** Profilimi düzenle → "Asistanının karakteri" (Your assistant's character) (if empty: warm, direct, curious; addresses you informally).
- **İçe aktar (Import):** on your phone, WhatsApp chat/group → *Export chat → Without media* (.txt/.zip), contacts → .vcf.
  Drop the file onto the page and pick the candidates you want. Fill in the "WhatsApp'taki adın" (Your name on WhatsApp) field first.
  The window's tabs handle the file types below. **All of them run on this computer, never go online and use no model**; the raw file is not written to disk
  (unless you choose "sohbet metnini sakla", keep the chat text, for WhatsApp); ZIPs go through path, size and zip-bomb checks; upload endpoints require lock + key + local Origin.
  The preview writes nothing; *Onayla ve yaz* (Confirm and write) writes, and uploading the same file twice never writes the same line twice.

  | Source | File | What is taken | What is not | Result |
  |---|---|---|---|---|
  | WhatsApp | .txt / .zip | name, message count, dates, conversation metrics | message content (unless you choose to keep it) | the candidates you pick join the network |
  | Contacts | .vcf | name, phone, e-mail, organisation, role, photo | note fields | the candidates you pick join the network |
  | Calendar | .ics or Google Takeout .zip (Google, Outlook, Apple) | attendees (e-mail + name), date, `SUMMARY` shortened only if "Başlıkları yaz" (Write titles) is on (off by default, "toplantı"/meeting is written; titles such as health/legal/salary become "toplantı" even when it is on) | description, location, link, attachment, alarm | a `DD.MM.YYYY · takvim · toplantı` line for existing people and a `son_temas` that only moves forward; unrecognised attendees become new people if you pick them (closeness 0); an e-mail suggestion for people without an e-mail lands in Verify. Recurring events only in the past, at most 60 per series; meetings with more than 15 attendees don't count towards closeness (optional); your own address is removed |
  | LinkedIn | data copy .zip, `Connections.csv` (may start with "Notes:"), `messages.csv` | connection's name, URL, e-mail, company, position, connection date; for messages only with whom and on which day | message content and subject are never read or stored anywhere; other files in the ZIP are not opened | for existing people only empty linkedin/organisation/role fields as Verify suggestions; connection date as a `## Kaynaklar` (Sources) note; message days as `linkedin` contact lines; new connections only if you pick them (closeness 0, no type guess); search, filter and bulk selection for thousands of connections |
  | Course list | pasted text | course code, course name, professor's name (titles such as Prof. Dr., Doç. Dr., Dr. Öğr. Üyesi, Öğr. Gör., Arş. Gör. are dropped) | nothing | courses go to your profile, professors to the network (closeness 0, type academia, `## Dersler`, `hocasi` link); no request to the school website |

  If you write your own e-mail into the "Takvimdeki e-posta adresin" (Your e-mail address in the calendar) field (or if the calendar name in the file is an e-mail), Kut removes you from the attendees and saves it to `ayarlar.json` → `ben_epostalari`.
  The title preference is remembered as `ayarlar.json` → `takvim_baslik` (true/false).
  Import limits (v1.1): at most 6 million lines and 200 thousand events are processed per calendar file, and parsing + recurrence expansion takes at most 90 s; the total expansion budget for recurrence rules is 2 million occurrences per file (if exceeded, the remaining series count only with their first event and the preview says so), `INTERVAL` is at most 10 000, and a series with broken/overflowing dates is reduced to a single event. Your e-mail address *guessed* from the calendar (the calendar name, or the single address present in every meeting) is used to remove you from the attendees in that import, but it is saved permanently (`ben_epostalari`) only if you tick the separate, unticked-by-default box in the preview; an address you typed yourself is saved without confirmation. Previews don't hold the global data lock (the interface doesn't freeze) and only one upload is processed at a time; a second one returns 429 "Başka bir içe aktarma işleniyor" (Another import is in progress).
- **Exclusion list:** write the names of organisations/parties you don't want to engage with into `veri/haric.md`; they enter no suggestion and never go to a model.
- **Indirect people and focus:** people with no direct tie to you, whom you know only through someone else (closeness 0, no contact record), are hidden on the map
  by default. **Double-click** a person: they move to the centre and only their links are shown; **Esc** or "← Ağıma dön" (Back to my network) undoes it.
  To see everyone: Görünüm → "Dolaylı kişileri de göster" (View → Show indirect people too).
- **Intro animation:** the window plays a short intro on first opening; a click, Esc or Enter skips it. To turn it off completely, run
  `localStorage.setItem("kut-giris", "0")` in the browser console (this also skips the opening sound; there is no separate setting for the sound alone). Click and transition sounds are turned off in Settings → *Arayüz sesleri* (Interface sounds).
- **Second brain bridge:** if you write `"vault": {"yol": "C:\\...\\vault"}` into `%LOCALAPPDATA%\agim\ayarlar.json`, the left panel shows the vault's open tasks (`tasks/*.md`) and
  ideas (`notes/fikirler.md`), and the person card shows the lines where the person appears in the vault. The bridge never writes to the vault; personal notes, rules and the journal are not read (`ag_vault.py`, `HARIC`).
  **Kasadan kişileri al (Import people from the vault):** Settings → Sources → *Kasadan kişileri al* previews the vault's `kind: person` notes ("Found N people in the vault: X new, Y updates") and writes them once you confirm.
  title → name, aliases, `facts` (organisation, role, last contact) → fields; Beyan (Statement) → *Senin beyanların* (Your statements); Temaslar → *Temas* (Contacts); *Çıkarım (onay bekliyor)* (Inference, awaiting approval) → the **Verify** queue (never written directly);
  Sources + the source note's path → *Kaynaklar*. It merges with a person of the same name/alias (only filling empty fields, never overwriting your statements), a copy is saved to `arsiv/surum/` before writing, and running it again is safe.
  **Trust label:** the Statement lines (and `facts.iliski`) of a note with `trust: untrusted`, `trust: quarantined`, `trusted: false`, any unrecognised `trust` value, or `status`/`kind: untrusted` do **not** go into *Your statements*; they land in the Verify queue as "Kasa notu güvenilmez işaretli; şunu doğrula: …" (Vault note marked untrusted; verify this: …); that note's `kurum`, `rol` (as an organisation/role suggestion in Verify), aliases, Contacts lines and `son_temas` date are not written directly either, they become Verify suggestions, and its aliases don't affect unconfirmed matching (same meaning as avenox beyin V3 `_trusted_record`; `quarantined` is Kut's own extra strictness). A note without a label counts as trusted, as in avenox: these are the user's own V3 person notes; in avenox `source` is the source file path, not a trust label.
  Folders whose names contain vault/password/identity/finance/customer/private/secret (kasa/şifre/kimlik/finans/müşteri/özel/gizli) and `visibility: private` notes are never imported. Nothing is written to the vault; no placeholder images are generated, and `foto` is copied only if the note has an explicit link to a real image inside the vault.
- **Pusula (Compass, P):** goals in `veri/hedefler/<id>.md`; discovery in `ag_kesif.py` (parliament data (if on) weekly, events every 12 hours; source list
  `ayarlar.json` → `kesif.etkinlik_kaynaklari`); strategy in `ag_strateji.py` (`veri/strateji/<date>.md`; you mark moves as *done / it worked*,
  and the next reading sees that). With an active goal and Claude Code it runs by itself once a week (turned off with `"otomatik_strateji": false`).
  **Calendar tab** (`ag_ajanda.py`, `GET /api/ajanda?bas=&bit=`): move and goal deadlines, promises, people's next steps and neglect thresholds, events you marked "katılacağım" (I'll attend) and past contacts in a month grid, week view or agenda list (←/→ month, T today). It is local and read-only; no model and no network, and people on the exclusion list don't appear. Selecting a day opens a move's first step, a person's next step or an event's address in the side panel.
- **Voice:** 🎙 in the Ask Kut bar (Ctrl+Space) turns speech into text, "🔈 Sesli cevap" (Spoken answer) reads answers aloud. The models don't run in Kut's Python but in the environments
  they are installed in (`ag_ses.py` → `ag_ses_isci.py`). Environments are searched in this order: (1) an explicit path given in `ayarlar.json` → `"ses": {"oku_python": "<ema env>\\Scripts\\python.exe",
  "yaz_python": "<faster-whisper env>\\Scripts\\python.exe", "yaz_model": "large-v3"}`; (2) the environment Kut installed itself
  (`%LOCALAPPDATA%\agim\ses`); (3) old known paths in the developer's vault; (4) a system Python with the packages and model cache ready.
  Recordings are never written to disk; apart from installation nothing goes online.
  - **Install offer (`ag_ses_kur.py`):** if there is no environment, the first tap on 🎙 / 🔈 asks *"Download Whisper and EMA Lightning for voice?"*
    (Yes · Not now · Don't ask again; later also from Settings → Sources → the *Sesli iletişim* card). Sizes are shown beforehand:
    EMA packages + model ~0.3 GB; Whisper packages ~0.1 GB (+ CUDA libraries ~1.2 GB if there is an NVIDIA card); the Whisper model `small` ~0.5 GB,
    `medium` ~1.5 GB, `large-v3` ~2.9 GB. **Default model:** `large-v3` if there is an NVIDIA card (most accurate for Turkish, fast on the GPU), otherwise `small`
    (on the CPU `large-v3` transcribes much slower than real time; `small` is fast but makes more mistakes, `medium` is in between). Installation
    looks for Python 3.11–3.13 on the system (`py -3.x`, `python`; EMA needs 3.11+, the pinned packages are tested up to 3.13) and creates the `ses/oku/.venv` and `ses/yaz/.venv`
    virtual environments; packages are pinned (`ema-lightning==1.1.2`, `normalizer-tr==0.7.0`, `torch==2.6.0`, `faster-whisper==1.2.1`,
    `ctranslate2==4.8.2`) and installed from wheels only (`--only-binary`); models are downloaded under `ses/hf`. If no Python is found,
    [python.org/downloads](https://www.python.org/downloads/) is shown; installing your own Python is up to you. Progress is shown as a percentage and can be **cancelled**
    (cancelling deletes the environment opened in that installation); if Kut closes during installation, the half-built environment is cleaned up on the next launch. The install log is `%LOCALAPPDATA%\agim\ses-kurulum.log`.
    The *Kut'un kurduğunu kaldır* (Remove what Kut installed) button deletes only the `ses/` folder. Endpoints: `GET /api/ses/kurulum`, `POST /api/ses/kurulum/baslat|iptal|kaldir|ayar`
    (lock + key + local `Origin`; `baslat` requires `{"onay": true}` in the body). "Don't ask again" writes `ayarlar.json` → `ses.kurulum_sorusu: "sorma"`.

### Data files
Markdown is the single source of truth (the `veri/` folder; details in `AGENTS.md`):

| File | Contents |
|---|---|
| `ben.md` | the person at the centre (you): name, interests, assistant's name, school |
| `kisiler/<id>.md` | a person: frontmatter (`ad, tur, kurum, rol, yakinlik, son_temas, sonraki_adim, ...`) + `## Temas` lines (`- DD.MM.YYYY · channel · sentence`) |
| `iliskiler.md` | a `\| a \| b \| tip \| not \| kaynak \| tarih \|` table |
| `cikarimlar.md` | assistant inferences and questions awaiting approval |
| `hedefler/<id>.md` | Compass goals |
| `haric.md` | organisations/parties not to engage with |

### Your own agent
This folder is also the workspace of an AI agent (`AGENTS.md` instructions): if you open the folder with an agent like Claude and say
"Had coffee with Ali, talked about an internship, I'll write to him in 2 weeks", the contact, closeness and next step are saved; you can ask "Who should I focus on this week?".
The agent never writes its inferences directly to a person file beyond suggesting them.

## Supported schools

The drop-down in Settings → Sources → *Okul bağdaştırıcısı* (School adapter) is filled from the `kut/ag_okullar.py` registry. Each source was tested with a live request for robots.txt and accessibility (October 2026);
sources that require a login (OBS/student login), are disallowed by robots.txt or are bot-protected are not used.

| School (key) | Course → professor source | Staff / profile | Course code example |
|---|---|---|---|
| Yeditepe University (`yeditepe`) | yeditepeders.com timetable (JSON) | faculty academic staff page + profile: title, e-mail, photo, CV, ORCID | `ISE 424-1` |
| Istanbul Technical University (`itu`) | obs.itu.edu.tr/public/DersProgram (public timetable; CRN counts as section) | none (course and professor name only) | `BIL 100E`, `BIL 100E-14304` |

School-independent: the *Akademik profiller* (Academic profiles) source (off by default) looks the professor up by name in OpenAlex and ORCID; if name + organisation match a single record it becomes an "About" suggestion, and if the match is ambiguous it becomes an "I'm not sure" question in **Verify**; it is never written directly to the person file.

Tried and not added: METU/ODTÜ (OIBS `robots.txt`: `Disallow: /`), Boğaziçi (registration system `Disallow: /`), Bilkent (STARS allows only a few fixed pages), Sabancı (the Banner "Dynamic Schedule" is technically readable but `robots.txt` `Disallow: /#` = the whole site is disallowed; respected),
YÖK Akademik (bot protection), AVESIS (profile pages are open but search goes through a JS/ES proxy; no course→professor mapping), OBS/OIBS Bologna systems (at most universities; no search by course code, the programme tree is navigated through form submissions).

## Adding a school adapter

**Your school isn't there? Add an adapter.** School features are defined in the `kut/ag_okullar.py` registry; the key is the simplified form of the `okul` field in the profile (lower case, without Turkish characters or accents).
Every adapter provides the same interface: `anahtar`, `ad`, `kisa`, `alan_adi`, `dersler(kodlar)` → `([{kod, sube, ad, hocalar, saat, bolum}], not_found)` and `hoca_profili(name_or_url)` → title/e-mail/photo/CV/ORCID (an empty dict if the source doesn't provide them).

1. Check the source first: is the timetable public and login-free, does `robots.txt` allow it (`#` starts a comment: `Disallow: /#` disallows the whole site), do the terms of use forbid it? Verify with a live request that it can be parsed.
2. Subclass `Baglastirici` and write `dersler()` (for network access use only `al(url)`/`ag_kaynak._istek`: SSRF protection, timeouts, size limits, rate limiting and robots checks are built in; cache results with `onbellekli()`).
3. At the end of the file call `kaydet(YourClassName())`; the drop-down and `ag_kaynak.OKULLAR` update by themselves. Put the school's English name in `kurum_en` (for OpenAlex organisation matching).
4. Take a small HTML/JSON sample from the source (make up the people's names), put it under `tests/fixtures/` and test the parser with a test like `tests/test_okullar.py`; tests must make no network calls.

The `yeditepe` entry is in the old format (inside `ag_kaynak.OKULLAR`, `ders_json` + a Drupal staff block); for a school with a JSON timetable and a Drupal staff page, adding an entry with the same fields is enough:

```python
OKULLAR["okulum"] = {
    "ad": "Okulum Üniversitesi", "kisa": "Okulum",
    "ders_json": "https://ornek.edu/data/courses-{donem}.json",   # public timetable (JSON)
    "ders_kaynak": "ornek.edu", "donem": "2026G", "donem_adi": "Güz 2026",
    "kadro": {"ABC": ("https://fakulte.ornek.edu", "12")},         # course code prefix → academic staff page, department no.
    "kadro_adi": {"ABC": "Okulum Örnek Mühendisliği"},
    "kadro_plugin": "...", "eposta_alani": "ornek.edu",
    "profil_ornek": "ornek.edu/akademik-kadro/<n>",
    "etkinlik_url": "https://ornek.edu/etkinlikler",
}
```

Principles: only public, login-free pages; don't try to get around sites that require a login or are bot-protected (CAPTCHA, blocking); professor photos only from the official institutional domain; information from a source is written with its source, fills only empty fields and never overwrites what you wrote.
If `okul` is empty or unknown in your profile, this feature is off and no request is made to any school website.

## Adding sources

- **New university:** adding an adapter to `ag_okullar.py` is enough ([guide](#adding-a-school-adapter)); it appears in the school list of the *Sources* tab by itself.
- **New event source:** add an address to the `ayarlar.json` → `kesif.etkinlik_kaynaklari` list (no code needed if the page has schema.org Events). It is scanned when event scanning is on via the `kesif.etkinlik` setting.
- **New optional source type:** an entry in `ag_kesif.KAYNAK_AYARLARI` and a `kesif.<id>` gate; while the gate is closed nothing may go online (example: `etkinlik_acik()`).

## Repository layout

```
kut.pyw        launcher (adds kut/ to the path, starts the server; `--ozet` is the scheduled digest task and starts no server)
kut/           application code (ag_*.py), version (surum.py), updater (ag_guncelle.py), data migrations (goc.py), UI (ag_sablon.html), icon
tests/         unit tests
demo/          fictional demo data generator (demo_veri.py) and import sample files (ornek/)
docs/          screenshots (img/), design drafts (tasarim/) and the website (GitHub Pages)
paketleme/     Kut.exe build (kut.spec, paketle.ps1; also produces Kut.exe.sha256)
baslatma/      Windows shortcut installer (kur.ps1), macOS launcher (Kut.command)
AGENTS.md      agent instructions (installation + in-app assistant)
```

Your personal data (`veri/`, or the folder you pass with `--veri`) never enters the repository.

## Tests

```powershell
py -3 -m unittest discover -s tests          # macOS/Linux: python3 -m unittest discover -s tests
```

The tests depend only on the standard library and never touch your real data (each one uses a temporary data folder).

## Licence

[MIT](LICENSE) © koraykutlu
