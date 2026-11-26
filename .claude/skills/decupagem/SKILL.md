---
name: decupagem
description: Rough-cut a multicam recording for Premiere — sync cameras + screen recordings by audio, transcribe locally, remove silences, repeated takes and production talk, read the transcript for what rules miss, switch cameras like the editor, export an editable Premiere XML. Use when the user sends raw episode footage, asks for decupagem, sync, silence removal, camera switching, or a Premiere/XML rough cut.
arsenal:
  etapa: 3
  area: pipeline
  titulo: "Decupagem"
  resumo: "Bruto multicâmera vira um XML do Premiere sincronizado, cortado e com troca de câmera."
  entradas: ["pasta|bruto das câmeras e da tela", "json|episode.json (vocab)", "json|client.json (câmeras)"]
  saidas: ["xml|premiere/<ep>_decupagem.xml", "md|report.md", "json|manifest.json"]
  ferramentas: ["decup.py", "decup_stage2.py", "edit_study.py", "check.py"]
  modelo: "Opus"
  pedidos: ["Decupa o bruto do <slug> <episódio> que está em <pasta>.", "Decupa estes reels do <slug> em lote: <pastas>."]
---

# decupagem

Everything heavy runs locally (ffmpeg, numpy, faster-whisper on the GPU). Claude spends tokens only on the summary
lines, `report.md` and one compact transcript (~6k tokens for a 15-min cut).
Measured history and the reasons behind the thresholds: `references/licoes.md` (read it only when tuning a
threshold, changing `decup.py`, or when a rule here surprises you).

## Before starting
- Episode folder: `python tools/studio.py new-episode <client> <episode>`. Put the episode's special words in
  `episode.json` `"vocab"` (they join the client's `transcribe_prompt`).
- Camera roles: client.json `decup.roles` (file-name patterns), `master_audio`, `home_camera`. Check them for a new
  client before `scan`; a file with no role is skipped and listed.

## Steps (from motion-studio/)
1. `python tools/decup.py scan <episode> "<raw folder>"` — sessions around each master file; originals referenced, never copied.
2. `python tools/decup.py sync <episode>` — every line `[OK]`. A constant "vs clock" = camera clock offset (normal).
   `CHECK` -> `probes` in manifest.json.
3. `python tools/decup.py trans <episode>` (set `HF_HUB_DISABLE_SYMLINKS_WARNING=1`). Splits at real silences
   (`decup.chunk_silence_s`), aligns word times to the voice; `--whole` = old single pass; `--out <dir>` for a test
   (`polish --transcript <dir>` reads it). **Hallucination filter on by default**: drops stock phrases / prompt echoes
   where the voice is weak (list `HALLUCINATIONS` in `decup_stage2.py` + client `decup.alucinacoes`; thresholds `HALLU`,
   override in `decup.alucinacao`, `null` = off). A stock phrase said with real voice stays, flagged `h`,
   `[FRASE-FEITA?]` in `semantic_in.txt` and in `report.md`; dropped ones are in `work/transcript/sN.json` `hallucinations`.
   **Check the transcript before cutting**: the same phrase twice in a row, a sentence mixing two attempts, word times
   off the voice.
4. `python tools/decup.py cut <episode>` — silences, breaths, repeated takes, production talk, restarts, orphan
   fragments. Read `report.md`'s "Repetição" lines.
5. **Semantic pass (always):** `python tools/decup.py semantic-export <episode>` -> read `work/semantic_in.txt`
   (`s1-012 [01:07.0] [TELA] text`) and write `work/semantic.json`:
   ```json
   {"drop":   [{"ids": ["s1-002", "s1-025..s1-029"], "why": "take refeito em s1-030"}],
    "trim":   [{"ids": ["s1-019"], "from": "e a realidade é que", "why": "recomeço"},
               {"ids": ["s1-047"], "until": "com o MCP ligado aqui", "why": "recomeço dentro da frase"}],
    "review": [{"ids": ["s1-031"], "why": "termina em '...' antes de 'Corta.'"}]}
   ```
   `from` cuts from the LAST occurrence of the phrase to the clip end; `until` cuts the clip start up to the FIRST
   occurrence (the phrase stays). Then `python tools/decup.py semantic-apply <episode>` (rule cut kept in
   `edl_auto.json`; drops go to `02_TAKES_DESCARTADOS`, reviews get an orange `REVER` marker — nothing is lost).
6. **Second pass (always):** `python tools/decup.py polish <episode>` -> read `work/polish_in.txt`, write
   `work/polish.json`, run `python tools/decup.py polish <episode> --apply` (see "Second pass"). The previous cut stays
   in `edl_pre_polish.json`; every cut and REVER is listed in `report.md`.
7. `python tools/decup.py xml <episode>` -> `premiere/<episode>_decupagem.xml` with `01_DECUPADO` (camera switching),
   `02_TAKES_DESCARTADOS`, `00_SINCRONIZADO_BRUTO`. The camera line must look like the client's numbers. Validate:
   parse, no overlaps, no duplicate ids. client.json: `decup.sequence_size` (default [1920, 1080]),
   `decup.screen_video_enabled` (screen audio always off), `decup.screen_scale` `"fill"` | `"fit"`.
   **Gate before showing:** `python tools/check.py decup <episode>` (timeline, cut points still in the voice, and a
   re-transcription of the kept audio: the same phrase twice, words cut across a join). Only 0 defects goes to the
   user's review; a defect you choose to keep is listed by timecode in LEIA-ME and gets a `REVER`, never passed silently.
8. Write `LEIA-ME.md` in the episode folder (sequences, tracks, numbers, what to review).
9. Optional, after the editor imported the XML by hand: **verify in Premiere** (`references/verificar-premiere.md`).

## What the semantic pass removes
- Drop: production talk (slates "câmera 1, câmera 2", "corta", "vou parar/repetir a gravação", "passar para o PC",
  "esconde os chats", instructions to the editor); a take said again later (keep the LAST one said complete and fluent —
  no stutter, slip, wrong or swear word — even when only the ending differs; if the last has a slip, keep the last clean
  one before it); false starts and 1–3-word fragments before the real sentence; a segment the speaker announces he will
  redo; waiting talk once the result is shown ("vamos esperar mais uns minutos").
- Trim: a clip ending in a restart or a dangling word ("vou", "e", "porque"); a clip beginning with a restart.
- Review (keep, marked): anything unsure; a clip ending in "..." right before "Corta."; any sentence joined from two takes.
- Never drop content you only find weak: the editor decides that.
- Inside a chosen take cut only what the speaker redoes right after. Face camera full frame (no screen on top): keep the
  sentence whole, only shorten pauses; tighter cuts belong under the screen recording (STYLE.md can override).
- After the cut, read the kept text once more: the same phrase twice in a row = two takes survived or a merged transcript.

## Second pass: `polish`
Candidates in `work/polish_in.txt` (`p012 [TELA] 425.5 muleta: ...context [[eu]] quero...`):
- `esticada`: start of a stretched word (glued hesitation / false start / pause) — **cut unless you `keep` it**
  (`decup.esticada_s`, default 0.6 s; null = off).
- `muleta`: a word of `decup.muletas` opening a breath group (`decup.muleta_pausa_s`, default 0.3 s) or a connective
  dangling at the end. Stays unless you `cut` it.
- `repete`: the same 1–3 words twice in a row (deliberate doubles like "muito muito" are not proposed). Stays unless `cut`.
- `clique`: a short line under the screen recording that only narrates a click (`decup.narra_clique`). Gets `REVER`
  unless you `cut` (whole line) or `keep` it.

`work/polish.json`: `{"cut": ["p003", "p010..p012"], "keep": ["p007"], "review": [{"ids": ["p020"], "why": "..."}]}`
(`{}` = defaults). Crutch words cannot be cut by rule — editors keep most of them:
- Cut a `muleta` only when the sentence reads the same without it (a hesitation, an "e" gluing two sentences, a word
  dangling before a pause). Keep it when it carries the logic ("Mas", "Ou seja", a turning "Portanto") or the sentence flows.
  Few cuts, only the clear ones.
- Cut a `repete` unless it is emphasis or a rephrasing. Cut a `clique` when the line says nothing the screen does not show.
- When unsure, `review`. `--auto` cuts every `muleta` and `repete`: only for a client whose editor was measured to remove them all.
Under a screen recording a cut lands on the quietest point between two words; with the face full frame only a piece's
head or tail is cut and an inner cut becomes a `REVER` ("câmara cheia, cortar?"). Cuts ≥ 0.5 s also go to
`02_TAKES_DESCARTADOS`. Still for you: a phrase restarted with another first word, a sentence abandoned mid-way
(`semantic.json` `trim`).

## Cut points: never cut while the voice still sounds
- Every in / out and inner join lands where the voice has decayed: `settle` (`decup.settle`, default 0.12; `null` = off),
  then `pad_in_s / pad_out_s`.
- Pauses inside a sentence are cut only from `decup.inner_gap_s` (default 0.25 s); raise it per client for sentences
  the editor wants whole.
- **One continuous take over a patchwork.** A sentence complete in one take is used whole. Between two complete takes:
  the fluent one, then the one closest to the script, then the last.
- **Duration targets are soft.** Never squeeze pauses to fit a reel target: note the overrun in LEIA-ME.
- **Never cut outside the tool.** A missing format (vertical, 60 fps) is fixed in `decup.py` on a development branch,
  never with a one-off script in the episode (it skips `settle`, the audit and the re-transcription check).

## Camera switching (client.json `camera_switch`)
Home camera most of the time; short inserts of the second camera (lengths / gaps from `camera_switch`), each starting
and ending ~0.1 s before a word, never during a screen recording (`never_during_screen`), only where the second camera
exists. In the XML an insert is a **disabled piece of the home camera** (label Lavender); the editor re-enables it to
undo. `--no-cams` turns it off; single-camera clients have `camera_switch.enabled = false`. Check the printed insert
count and median against the client's numbers.

## Learning from the editor's final cut
`python tools/edit_study.py <episode> "<final.xml>"` -> `study/` (removed / restored, padding, breaths, camera stats,
final transcript). Fold the numbers into client.json (`camera_switch`, `decup.pad_in_s / pad_out_s`, `decup.study_roles`)
and STYLE.md; new general semantic lessons go in the list above. To measure another cut without touching study/:
`... --edl edl_x.json --out <folder>`; compare `speech_removed_by_editor` (lower is better) and
`speech_restored_by_editor` (must stay near 0).

## Verify in Premiere (optional, step 9)
Read-only checks through the `premiere` MCP after the editor imported the XML by hand (File > Import): the tool
table and the limits are in `references/verificar-premiere.md`. Never `import_fcp_xml` through the MCP.

## Known traps
- faster-whisper + PyAV: pass the decoded numpy wav, not a path. CUDA DLLs come from pip `nvidia-*`
  (`decup_stage2._cuda_dlls()`). `python -I` hides the user site-packages: run these tools without `-I`.
- A REVER on a short clip whose text is a brand name or stock phrase in quiet audio is usually a hallucination: check
  by the voice, not the text.
- Misspelled brand names touch only markers and transcript, not the cut: fix them in what you write, do not re-transcribe.
- Never regenerate an XML the editor already imported with the same name: use `--name` for a test.
