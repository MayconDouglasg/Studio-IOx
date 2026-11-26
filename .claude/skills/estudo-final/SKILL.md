---
name: estudo-final
description: Study a finished episode at the source — the editor's final After Effects project and Premiere project — to learn what was really used, changed, added or dropped compared with what the system delivered, and write the lessons into the client's STYLE.md and the skills. Use when the user says a video is finished/delivered and asks to analyse the final files, learn from the editor, compare with what we made, or "melhorar a inteligência" for a client.
arsenal:
  etapa: 7
  area: pipeline
  titulo: "Estudo final"
  resumo: "Lê o .aep e o .prproj finais do editor e grava as lições no estilo do cliente."
  entradas: ["prproj|projeto final do Premiere", "aep|projeto final do After", "json|o que entregamos"]
  saidas: ["md|final_study/ANALISE.md", "md|STYLE.md atualizado", "md|skills com regras novas"]
  ferramentas: ["study_final.py"]
  modelo: "Opus"
  pedidos: ["O <episódio> foi finalizado: o Premiere é <projeto>, sequência <nome>; o After é <arquivo>."]
---

# estudo-final

The last stage of an episode: the editor's finished files teach the next episode. Read the files, never the
rendered video (that costs images); `tools/study_final.py` turns both projects into text.

## Inputs (ask for what is missing)
- The final **Premiere project** (.prproj) and the name of the **final sequence** (the one exported).
- The final **After Effects project** (.aep) the editor animated.
- The episode folder (for `motion/motion_map.json`, `study/`, the delivered `.aep`s) and the client's STYLE.md.

## Steps (from motion-studio/)
1. **After**: `python tools/study_final.py ae "<final.aep>" <episode>/final_study/after [--ae "<AfterFX.exe>"]`
   -> `study.txt` (every comp, layer, keyframe with ease, expression, effect, text with font/size/colour, marker).
   The project is opened read-only and never saved. "created with a newer version" in the output = pass `--ae`
   with that version (e.g. a project saved by a beta After). Then
   `python tools/study_final.py ae-detail <episode>/final_study/after [--ae ...]` -> `study_detail.txt`
   (what each text animator changes, effect parameters, masks). Close After afterwards if the user is not using it.
2. **Premiere**: `python tools/study_final.py pr "<project.prproj>" "<sequence>" <episode>/final_study/premiere`
   -> `sequence.txt` / `sequence.json`: every track, clip (media, nested sequence, After linked comp, mogrt), OFF
   clips, effects with keyframes, Premiere graphic texts (font, size, colour), transitions, audio (music, SFX).
   Two sequences with the same name: the exported one wins.
3. **Read in this order** (light first): the track summary of `sequence.json` (which tracks hold what, OFF counts),
   the enabled After linked-comp ranges (= which of our scenes reached the final video), then `study.txt` scene by
   scene against `motion/motion_map.json`. Note per scene: used / trimmed (seconds on screen) / changed / dropped,
   and what the editor added that we never planned (cold open, showcases, mogrts, transitions, zooms, SFX).
4. Write `<episode>/final_study/ANALISE.md` in Portuguese for the user (what was used, what changed, what he
   added, what it means for the next episode, open questions).
5. **Record the lessons** (CLAUDE.md "Client work"): everything about this client (numbers, scenes, taste,
   sound, templates) goes in the client's STYLE.md (a "how the editor finished <episode>" block + section 7 log).
   A lesson goes into a skill only when it holds for any client, written without client, episode or brand names.
   Do not silently change approved defaults: list the proposed rule changes and ask the user to confirm them.

## What to look for (checklist)
- Which of our scenes reached the video (enabled ranges of the After linked comp) and how long each stays on
  screen; which were dropped and where in the episode they were (body vs hook).
- Whether the editor animated from `01_layout` or `02_animado`, and his own recipe: text animators (what they
  change, timing, ease), camera rig and moves, how cards enter and leave, readability on the face.
- What he added that we never planned: cold open, showcases, templates/mogrts, transitions, zooms, colour, music
  and SFX (names, how many, where).
- The After version that saved the project.
