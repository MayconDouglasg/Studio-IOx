---
name: storyboard
description: Plan the motion graphics of an edited episode — pick the beats from the final transcript, write the scene spec with the client's lockups, anchor every scene to the spoken words, publish a review page the user marks scene by scene, iterate, then list and map the assets. Use when the editor sends the final cut (XML + reference mp4) and asks for animations, text inserts, a storyboard, marking where motion goes, or wants to validate the visual ID before After Effects.
arsenal:
  etapa: 5
  area: pipeline
  titulo: "Storyboard"
  resumo: "Escolhe os momentos de motion no corte final (ou na voz), ancora tudo na palavra falada, decide o caminho de cada cena (After, código ou IA) e publica uma página para aprovar cena a cena."
  entradas: ["xml|XML final do Premiere", "mp4|MP4 leve do corte final", "wav|voz (peça só com voz)", "md|STYLE.md"]
  saidas: ["html|página de revisão", "json|motion/motion_map.json", "pasta|lista de assets", "mp4|cenas pelo caminho do código"]
  ferramentas: ["edit_study.py", "motion_map.py", "build_storyboard.py", "codigo.py", "check.py"]
  modelo: "Opus, ou o mais capaz para as escolhas criativas"
  pedidos: ["O XML final e o vídeo do <episódio> estão em <pasta>, vamos para as animações.", "Faz um motion só com a voz <arquivo>, no modelo de páginas do <cliente>.", "Apliquei todas as notas na página de revisão, gera a próxima versão."]
---

# storyboard

Between the edit and After Effects. Output: an approved `motion/motion_map.json` (every scene's words, layout,
element, asset) — the only input `after-handoff` needs.
Lessons behind the rules and the dynamic types in full: `references/licoes.md` (read it for a client's first long
episode, a rejected idea, or a type you have not built yet).

## Inputs (stop and ask for what is missing)
- The editor's final XML and a low-res mp4 of the final edit; the client's STYLE.md (sections 1–3, 5–7) and client.json
  (`modo_apresentador`, `ritmo`, `grade`, `caminho_padrao`); the latest `final_study/ANALISE.md` if any.
- Voice-only piece (`modo_apresentador: so_voz`): the voice file; `python tools/codigo.py palavras <folder> <voice>`
  writes `words.json`.
- `episode.json`: `vocab`, `partner` (name, bg, accent, site print or reference time + crop), `media`.

## Step 0 — a client with no approved ID yet
If no episode has `motion/id_aprovada/`, first approve an ID from 6–9 test stills: `references/id-inicial.md`.

## Steps (from motion-studio/)
1. **Study the final cut**: `python tools/edit_study.py <episode> "<final.xml>"` -> `study/final_words.json`,
   `study/final_transcript.md`, `study/study.json` (camera / screen / AI-insert segments).
2. **Pick the beats** from `study/final_transcript.md` only:
   - Hook (first ~45–60 s): a graphic beat every 2–4 s. Body: key claims, numbers, tool / brand names, list items, the
     partner, the CTA (every ~15–30 s). Default: After scenes for the cold open + hook (~10); body beats listed as
     editing-program items, unless STYLE.md says otherwise. Over screen recordings only a short callout.
   - **On-screen text = the speaker's exact words, in his order** (excerpts, never paraphrase; ASR spellings fixed by
     `brand_names`). Sentences start with a capital.
   - One element per scene that means the word. Scenes last **2–4 s** (face overlays ~2 s).
3. **Anchor everything to the spoken word**: scene start, every row, camera arrival, micro-action and SFX (`anchor`,
   `palavra`). A camera travel ENDS on its word. Rhythm from `ritmo` (calmo: entrance ~0.8 s, new thing every 2–4 s;
   dinamico: entrance ~0.45 s, new thing every ~1.5 s, micro-action every ~0.5 s, 3 changes in the first 2.5 s).
4. **Path per scene** (`caminho`, default `caminho_padrao`):
   - `after`: two .aep for the editor. Lockups, 3D camera with depth, anything the editor will touch.
   - `codigo`: HTML -> MP4 (or ProRes 4444 over the presenter): full motion under a voice, diagrams, interfaces, style tests.
   - `ia`: a 4–5 s generated clip only for realistic 3D objects, living texture, photographic images. Always a layer
     BEHIND type; never text, numbers or logos in the prompt; client palette only; approve a still before any video.
5. **Write `motion/scenes_spec.json`**:
   ```json
   {"episode": "<ep>", "brand_names": {"<asr spelling>|<other spelling>": "<Brand>"},
    "scenes": [{"near": 13.5, "anchor": "short form", "dur": 4.4, "type": "CARD", "lock": "C",
                "key": "Short form", "serif": "muito à frente", "small": ["te pode pôr", "organicamente"],
                "el": "smartphone com um vídeo gerado", "motion": "...", "sfx": "...", "trans": "whip", "caminho": "after"}]}
   ```
   - `anchor` = first words as said, `near` = approximate second; `at` forces a start (opening before the first word).
   - After types: `OPEN-WALL`, `CARD`, `CARD-STRIKE`, `CARD-CHECKLIST` (lock LIST), `CARD-CONNECT` (two logos + hand
     line, `tiles`), `3D`, `3D-NUM`, `PARTNER-CARD` (partner bg + site print, our type; `pill`, `sub`), `LEG` (on the
     face; `pos` left / right / center).
   - Lockups (`lock`): **A** key + serif under (+ small); **B** small, key, (small +) serif; **C** key, small + serif,
     small; **D** serif, key + stacked smalls; **LIST** optional `title` [small, key], `rows` [[small, key struck]...],
     closing `serif`. Every line of a block scaled to the same width; the serif crosses the key only when clearly shorter.
   - Dynamic types (descriptions in `references/licoes.md`; STYLE.md says which the client approved): `PAGINAS` (After:
     camera route between `blocks`; code: a world of pages), `GRADE-ONDA`, `NOS`, `GALHO`, `PAINEL-CONSULTA`,
     `CHECKLIST`, `PISO-3D`, `UI-CARDS`, `BOARD`. Transitions with texture, never a dissolve; one accent, same jobs.
   - `trans`: wipe / whip / cut / iris; dynamic: empurrao / zoom-blur / glitch. `strike` on the key word.
   - `sfx` (read by `tools/sfx.py plan`): movement words ("whoosh", "pop", "clique", "papel por item"; "por item" = one
     cue per row) or `[{"mov": "impacto", "palavra": "milhares"}]`; omitted = defaults. Match `sfx.intensidade`.
6. `python tools/motion_map.py <episode>` -> `motion/motion_map.json`. Fix every `MISS`, read the warnings (overlap with
   an AI insert or the sting). **A newer cut** from the editor: re-run step 1 on the new XML and step 6 on the same spec
   (anchors are words, times follow; never rebuild the storyboard); check flagged scenes and those after an insertion.
7. **Review page**: `python tools/build_storyboard.py <episode> review<N> --frames "<reference.mp4>"` ->
   `storyboard/index.html`. Load `artifact-design` and `artifact-capabilities`, publish with `capabilities: {db: {}}`
   (same file path every version = same URL; new collection `review<N>` per version). Check the page yourself first
   (`node tools/shot_frames.mjs <index.html> <outdir> 0 1 2`).
   - **Every scene shows a drawn still from round 1** (code render, beside the reference frame), never text only.
   - References in another style mid-way: add an **option B** beside the approved A on the same page, never swap A out.
   - Ask the user to mark **every** scene, all notes in one pass; with an approved ID aim for 1–2 rounds. Several reels
     of one client can share a page.
8. **Read the review** with ArtifactData (`list`, collection `review<N>`; doc `s<id>` = {status ok / ajustar / remover,
   note}). Apply, save `storyboard/prev_notes.json`, bump N, republish. Log every approval / rejection in STYLE.md 7 and
   change the rule it touches. Repeat until approved.
9. **Assets**: list per scene in `ASSETS.md`, ask the user to download them (animated icons as mp4 on white, logos png
   with alpha, phone mockup .aep). Set each scene's `asset` and re-run step 6:
   `{"kind": "ICON", "path": "assets/3d/02_claquete.mp4"}`, `{"kind": "LOGO", "path": "brand/logos/x.png", "dark": true}`,
   `LOGO-TEASER`, `{"kind": "LOGOS", "path": [a, b]}`, `{"kind": "PHONE", "path": "...x.aep", "video": "<clip>"}`,
   `SQUARES3`. Paths relative to the episode, then the client folder, then motion-studio.
10. Hand off: `after` scenes to `after-handoff`; `codigo` scenes through the code path below.

## Scene rules (general; a client's STYLE.md overrides; client taste goes to STYLE.md 7, never here)
- The approved ID fixes colour, type, background, icon style and "text = the speaker's words"; each scene still gets
  its own idea for its sentence. Never reuse ID stills as layouts; never strip scenes to "minimal".
- Over screen recordings never propose the editor's own tools (punch-ins, zooms, blur, highlight boxes); a card
  mid-tutorial only for a strong number or key claim.
- Two consecutive beats of one idea, or two linked words in a sentence: one scene, one camera travel between two blocks.
- Never fake 3D by squashing a flat drawing: real perspective or flat and frontal.
- Partner identity (colours, logo, UI) only inside the partner's window; outside it a single-colour partner logo; their
  accent never leaks into our elements.
- Phone-size check (~1/3 size) before showing a still: at 1080p card captions ≥ ~50 px, pill text ~76 px.

## Presenter mode (client.json `modo_apresentador`)
`sobre` (default): `LEG` overlays and full-frame cards over the face. `bolha`: presenter in a round bubble, the world never
stops behind it. `tela_dividida`: presenter on one half, impact words cross the split. `so_voz`: whole piece is motion
under the voice, usually one continuous `PAGINAS` world on the code path.

## Code path (scenes with `caminho: codigo`)
1. `python tools/codigo.py novo <folder> --client <slug>`: a new folder per version, never over a delivered file. An
   unknown slug stops it. A "uses the INSTALLED family" warning = put the font files in the client's `brand/fonts` first.
2. `python tools/codigo.py palavras <folder> <voice>` -> words.json. Content file (`paginas.json`) with a `palavra` on
   every beat (repeated or short words: anchor on a phrase); add a diagram to the starter only when no type fits
   (generic, no client values). Over the presenter: `abre_s` = second the first insert starts; render at the editor's
   frame rate (`--fps 30`).
3. `node render.mjs --project <folder> --timeline` -> `python tools/codigo.py trilha <folder>` -> `python tools/codigo.py
   mix <folder>` (bed ~0.22 under the voice, -14 LUFS). Over the presenter: `trilha --janelas 4.6-21.2,25.5-` and
   `mix --janelas <same>`. Library SFX instead: `python tools/sfx.py plan <folder>` (`sfx` skill).
4. `node render.mjs --project <folder> --contact` (or `--at 1,2.5,4 --name pontos` for a few moments). **Do not open the
   sheet here:** hand the folder to the `conferir-frames` agent (Agent tool, `subagent_type: conferir-frames`) with the
   client's `client.json` path, `ritmo` and the scene/word list; it returns short text findings per scene. Score
   (CLAUDE.md loop), fix the 3 worst, repeat. Open one image yourself only to settle a finding marked DOUBT.
   **Gate before showing:** `python tools/check.py frames <stills or render>` and, on the final file,
   `python tools/check.py render <file>`. Only 0 defects goes to the review page or the user.
5. `node render.mjs --project <folder>` (H.264) or `--alpha` (ProRes 4444 over the presenter).
6. Preview over the presenter: `python tools/codigo.py compor <folder> <presenter video> --janelas <same> --out <new file>`.
