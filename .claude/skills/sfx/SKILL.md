---
name: sfx
description: Sound for the motion — pick sound effects from the team's SFX library for each motion event of an episode (text entrances, pops, camera travels, transitions, glitches, clicks, typing, checks, impacts on numbers, risers, the final pull-out, the logo sting), from sounds the user approved by ear, and write the SFX plan plus a new copy of the Premiere XML with the cues on their own audio tracks. Use when the user asks for SFX, sound effects, efeitos sonoros, sons nos motions, "põe os sons", a sound plan, to review / approve sounds per movement, or to learn which sounds the editor used.
arsenal:
  area: pipeline
  ao_lado: after-handoff
  titulo: "Sons dos motions (SFX)"
  resumo: "Para cada movimento do motion (entrada de texto, viagem de câmera, transição, glitch, clique, impacto, riser...) escolhe sons da biblioteca que você aprovou de ouvido e monta o plano de SFX com uma cópia do XML."
  entradas: ["json|motion/motion_map.json (ou out/timeline.json do código)", "xml|XML do corte em que o motion foi ancorado", "pasta|biblioteca de SFX deste PC"]
  saidas: ["json|work/sfx_plan.json", "xml|cópia do XML com as faixas de SFX", "html|página local para aprovar sons"]
  ferramentas: ["sfx.py", "sfx_revisar.html"]
  modelo: "Opus"
  pedidos: ["Abre a revisão de SFX para eu aprovar os sons por movimento.", "Faz o plano de SFX do <episódio>: o XML é <arquivo.xml>.", "Faz uma prévia de SFX do <episódio> para eu ouvir no contexto.", "Aprende os sons que o editor usou no <episódio> finalizado."]
---

# sfx

After the storyboard (motion_map approved) or the code path's timeline, beside `after-handoff`. Output: `<episode>/work/sfx_plan.json`
(time, movement, file, gain, layer per cue) and a NEW copy of the editor's XML with the SFX on new audio tracks. Placing them
on the timeline directly (Premiere MCP) comes later; until then the editor imports the XML copy.

## The one rule
**No sound is used before the user approved it by ear.** `pick` and `plan` only return sounds marked ok on the review page.
`plan --previa` fills the rest with the top of the shortlist ONLY to hear them in context: the file and the sequence say PREVIA,
never deliver it. Never mark ok / não yourself (not on the page, not by writing sfx_motion.json): that is the user's ear.

## Inputs (stop and ask for what is missing)
- The SFX library on this PC: `studio.config.json` `sfx_library` (`python tools/sfx.py biblioteca "<folder>"`). Never write the
  path into the repository. The tool reads the library's catalog and favourites and writes only `_sistema/dados/sfx_motion.json`;
  never move, rename or edit sounds, the catalog, the library's scripts or its favourites.
- The client's `client.json` `sfx` (intensidade auto | subtil | medio | forte, excluir, incluir, ganho_db, musica) and STYLE.md
  section 4 (sound). A brief that asks for simple, never exaggerated motion = `subtil`.
- The episode: `motion/motion_map.json` (+ `after/*_build.jsx` for the row times as built, `study/final_words.json`,
  `study/study.json` for the logo sting) or a code folder's `out/timeline.json` (`node render.mjs --project <f> --timeline`).
- The XML the motion was anchored on (the editor's final cut the storyboard studied). A newer cut with an insertion shifts every
  time: re-run the storyboard's step 1 + motion_map on it first (the anchors are words), then plan.

## Steps (from motion-studio/)
1. `python tools/sfx.py index` — measures every sound a movement can use (cached; a re-run measures only new files) and ranks
   each movement's pool. Run it again after sounds are added to the library (`Atualizar Biblioteca.bat`).
2. Approval by ear: `python tools/sfx.py revisar` opens `http://127.0.0.1:8767` (6–10 sounds per movement, play, ok / não,
   licence per pack). Ask the user to go through every movement the episode needs in one pass. `python tools/sfx.py movimentos`
   shows how many are approved per movement.
3. `python tools/sfx.py plan <episode> --xml "<final.xml>"` -> `work/sfx_plan.json` + `premiere/<xml>_sfx.xml` (never overwrites).
   Read its table: movements with "sem som aprovado" stay silent; packs with licence "?" are flagged. `--musica <file>` adds a
   licensed bed (never `80_Musica/Com Copyright`).
4. Tell the user: cues per movement, which movements are silent and why, licence warnings, the XML to import.
5. Finished episode: after `estudo-final`, `python tools/sfx.py aprender <episode>` reads the editor's final sequence and
   records which library sounds he used for which movement (a ranking bonus and a place on the review page, never an approval).

## How cues are placed (implemented in sfx.py)
- The sound's measured peak lands on the event (the spoken word / the arrival): a whoosh peaks as the camera arrives, a
  riser peaks on the reveal (the sting when the storyboard says "até à vinheta"), typing and markers start on the word.
- One sound per movement for the whole episode, and the same sound always on the same layer (its own audio track).
- Rows built at the same instant give one cue; the shortest gap between two cues of the same movement is 0.5 s (subtil),
  0.3 s (medio), 0.15 s (forte).
- Levels from measured loudness (K-weighted, momentary max) to a target per movement and intensity; overlapping cues are lowered
  together until the sum of their peaks is under -1 dBTP (0.5 dB margin). A long file is cut at the movement's maximum length
  with a short fade. Music bed: 20 dB under the -14 LUFS voice, ending 2 s after the last motion event with a fade.
- The storyboard's `sfx` text names the sounds of a scene ("riser curto + hit suave", "papel por item", "marcador no risco"):
  those words win over the defaults. A structured list also works: `"sfx": [{"mov": "impacto", "palavra": "milhares"}]`.
- Default sounds when the storyboard is silent: full-frame card in / out = transicao (whip, wipe = papel, iris = brilho,
  glitch); each text row = entrada_texto; checklist rows = check; strike = escrita; numbers = impacto; opening = riser;
  PAGINAS block arrivals = viagem_camera; logo segment = logo_sting; last scene = saida_suave.

## Movement vocabulary
`python tools/sfx.py movimentos` lists them: entrada_texto, pop_palavra, contador, carrossel, viagem_camera, transicao, glitch,
flash_luz, brilho, ui_clique, ui_digitar, ui_notificacao, check, escrita, papel, impacto, riser, saida_suave, logo_sting.
A new kind of motion event gets a movement in `M` (sfx.py) with its pool and measured targets, and a mapping in `CODE_EVENTS`
or `after_events` — general, never a client's sound.

## Off by default
`80_Musica` (part is copyrighted: YouTube claims), `15_Memes_Cartoon_Famosos`, `98_Revisar`, `90_Video_Overlays_LUTs`, the
horror and weapons themes, and any file named like a rip from a video site. A client switches a theme on with `sfx.incluir`.

## Feedback
Sound approvals live in sfx_motion.json (per library, all clients). A client's taste (intensity, a family of sounds it rejected,
a movement it wants silent) goes to its STYLE.md section 4 and client.json `sfx`; a general lesson changes this skill or `M`.
