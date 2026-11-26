---
name: novo-cliente
description: Set up a new client (or register an existing client folder) in motion-studio — folder, client.json brand tokens, STYLE.md, fonts, logos, references — and a new episode for a client. Use when the user mentions a new client, a different channel or brand, asks to configure the system for someone else, or starts an episode for a client that is not registered on this PC.
arsenal:
  etapa: 1
  area: pipeline
  titulo: "Cliente novo"
  resumo: "Cria ou registra a pasta do cliente e abre cada episódio."
  entradas: ["pasta|pasta do cliente (nova ou existente)", "fonte|fontes e logos", "mp4|3 a 6 vídeos do canal"]
  saidas: ["json|client.json", "md|STYLE.md", "pasta|projects/<episódio>/episode.json"]
  ferramentas: ["studio.py"]
  modelo: "Opus"
  pedidos: ["Vamos configurar um cliente novo.", "Registra o cliente <slug>, a pasta é <pasta>.", "Episódio novo do <slug>: <episódio>."]
---

# novo-cliente

Every tool finds a client through `studio.config.json` (per PC, never in git). A client is a folder
anywhere on the disk (usually next to the client's other work) with:

```
<client folder>/
  client.json     tokens the tools read: colors, fonts (PostScript names for After), camera roles,
                  camera-switch numbers, motion intensity / transitions, transcription prompt
  STYLE.md        the brief Claude reads (prose rules, feedback log)
  brand/fonts     the font files (install them on every PC that builds for this client)
  brand/logos     logos (png with alpha); brand/mockups optional
  refs/canal      the client's own published videos (+ optional .txt note "até 01:20")
  refs/inspiracao outside animations the client likes
  _digest/        written by tools/ingest.py
  projects/<episode>/   one folder per episode
```

## New client
1. Ask (one AskUserQuestion, only what you cannot see): client name and slug; where the folder should
   live; the cameras they record with (file-name patterns, which one carries the audio, which is the
   main camera); language / accent of the videos; partner or sponsor worlds that recur; and the three format
   choices: where the presenter is (`modo_apresentador`: sobre / bolha / tela_dividida / so_voz), the rhythm
   (`ritmo`: calmo / dinamico) and the default path of a scene (`caminho_padrao`: after / codigo / ia).
   If they do not know yet, keep the template defaults (sobre, calmo, after) and decide on the first approved test.
   Ask too how much sound the motion should carry (`sfx.intensidade`: subtil / medio / forte; "simple, never exaggerated"
   = subtil; unknown = `auto`, which follows `motion.intensity`) and whether any theme is welcome (`sfx.incluir`).
2. `python tools/studio.py new-client <slug> "<folder>" --name "<Name>"` (creates the folders, copies
   the templates, registers the client).
3. Ask the user to drop: fonts in `brand/fonts`, logos in `brand/logos`, 3–6 channel videos in
   `refs/canal`, inspirations in `refs/inspiracao`. Install the fonts (Windows: right click > Install
   for all users) — After Effects only sees installed fonts. Channel videos can come straight from links:
   ask for 3–6 links of the client's own videos (recent, in the current format) and run
   `python tools/studio.py refs <slug> <url...>` (motion-refs skill, "Getting the videos"). Fewer than 3
   is not enough to average the style: ask for more before step 4.
4. Run the `motion-refs` skill (ingest + STYLE.md). Then fill `client.json` from what you measured:
   `colors`, `fonts` (family, weight, italic, PostScript names: check them in After with
   `app.fonts.getFontsByPostScriptName`, a variable font may expose a different name), `google_fonts`
   (for the storyboard page; if the font is not on Google Fonts, say so — the page will fall back),
   `decup.roles` / `master_audio` / `home_camera`, `transcribe_prompt`, `language`; `fonts.<role>.file` (font file
   in brand/fonts for the code path), `modo_apresentador`, `ritmo` (calmo: entrada_s 0.8, novo_a_cada_s 3,
   viagem_s 0.6; dinamico: 0.45 / 1.5 / 0.45), `grade` (margin, alignment, hierarchy etiqueta → título → serifa →
   diagrama, underline) — measured from refs/canal or from the first approved test, and written in STYLE.md 1b too.
5. `camera_switch` and `decup.pad_*` start from the template; after the client's first edited episode,
   run `tools/edit_study.py` and replace them with the measured numbers (decupagem skill).
6. `python tools/studio.py doctor` must end with "all good".

## Existing client folder (moved PC, shared drive, colleague's folder)
`python tools/studio.py add-client <slug> "<folder>" [--projects "<episodes folder>"]` then `doctor`.

## New episode
`python tools/studio.py new-episode <slug> <episode>` creates `projects/<episode>/` with `episode.json`:
`vocab` (brand / tool names for the transcription), `partner` ({name, bg, accent, site or
site_from_reference_at_s + site_crop}) when the episode has a sponsor, `media` (generated clips) when
they are not in the editor's XML. Then: decupagem -> (editor edits) -> storyboard -> after-handoff.

## Lessons (learned setting up clients)
- The template `client.json` holds neutral placeholders (Arial / Georgia, grey paper) and `_template: true`:
  replace colors, fonts, decup roles, camera_switch and motion for the client and delete `_template`.
  `studio.py doctor` flags a client still on template values.
- Read the episode briefing first (PDF: `pip install pypdf`, print with `PYTHONIOENCODING=utf-8`): it usually
  gives fonts, colors, icon source, webcam bubble style, blur list, LUT, music, language. Mark colors that
  come only from prose as `_provisional` until measured from refs/canal.
- Usual layout: client data in `<Clientes>/<Name>/motion/` (subfolder), raw episode folders stay next to it
  untouched; store the raw/brief/media paths in `episode.json` (`raw`, `brief`, `media_folder`).
- Single-camera clients: `decup.roles` only `frontal` + `tela`, `master_audio`/`home_camera` = `frontal`,
  `camera_switch.enabled = false`.
- **Check a font file's glyph count** before pointing `fonts.<role>.file` at it: a web / Latin-subset file
  (~300 glyphs) looks right in a test but misses accented letters, symbols or numerals. Count with
  `python -c "from fontTools.ttLib import TTFont; import sys; print(len(TTFont(sys.argv[1]).getGlyphOrder()))" <file>`
  and point `fonts.*.file` at the full family file (usually 600+ glyphs); keep the subset out of `brand/fonts`.
- **Grid / line / divider colours** of the client's sheets are measured too (sample the pixels on the digest
  sheet or the approved stills) and mapped to a **mix of the client tokens** (e.g. ink at 12 % over paper),
  written in client.json as that mix — never as a new colour.
- Extra file patterns the study tools should recognise (generated b-roll, logo sting) go in
  `decup.study_roles` (e.g. `{"broll_ia": ["result-*"], "logo": ["<LOGO>*"]}`).

## Rules
- Never copy one client's STYLE.md rules into another; the template is neutral on purpose.
- Client folders hold media and are never committed to the motion-studio repository.
