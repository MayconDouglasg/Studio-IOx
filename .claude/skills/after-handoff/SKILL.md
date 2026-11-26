---
name: after-handoff
description: Build the After Effects projects for an episode from the approved storyboard — one layout-only project and one animated project (3D camera, depth, per-character type) — and verify them with frames rendered by After Effects. Use when the user asks for the After Effects file/structure, precomps ready to animate, to fix or rebuild an .aep, or approves a storyboard and wants it in After.
arsenal:
  etapa: 6
  area: pipeline
  titulo: "After Effects"
  resumo: "Do motion_map aprovado para dois projetos do After, conferidos por frames: câmera que viaja entre blocos na palavra, abre colada no conteúdo e fecha num recuo suave."
  entradas: ["json|motion/motion_map.json", "mp4|MP4 de referência", "json|client.json"]
  saidas: ["aep|<ep>_01_layout.aep (sem keyframes)", "aep|<ep>_02_animado.aep", "png|frames de conferência"]
  ferramentas: ["build_ae.py", "ae_builder.jsx", "ae_run.ps1", "ae_shots.py", "check.py"]
  modelo: "Opus"
  pedidos: ["Storyboard do <episódio> aprovado, gera o After.", "Refaz o 02_animado do <episódio> com <ajuste>, sem sobrescrever o entregue."]
---

# after-handoff

The editor animates in After Effects. Claude never hand-edits an .aep: a generator writes an ExtendScript, After runs
it, and the frames After rendered are checked before saying done.
The failure behind each rule and how editors really use the hand-off: `references/licoes.md` (read it when a build
fails in a way not explained here, or before changing the builder or the motion recipe).

## Inputs (if one is missing, stop and say which)
- `<episode>/motion/motion_map.json` (approved, from `storyboard`); `study/final_words.json` (word times of the final edit).
- client.json (colors, fonts as PostScript names, `motion.intensity`, `motion.transitions`, `motion.long_scene_s`,
  `ritmo.viagem_s` / `ritmo.fim_s`, `grade.alinhamento`) and `episode.json` (`partner`, `media`).
- Assets from `ASSETS.md`; the reference edit (.mp4); the client's STYLE.md.

## Steps (from motion-studio/)
1. `python tools/build_ae.py <episode> "<reference.mp4>" [layout] [motion] [--out <folder>]` writes
   `<episode>_01_layout_build.jsx` and `_02_animado_build.jsx`. Read its table: one transition per card scene, row
   times per scene, any `WARN` (a long scene whose rows all enter at the start = wrong word times: fix before building).
   **Testing on a delivered episode: always `--out <test folder>`** — never overwrite a delivered `.aep`.
2. Run each: `powershell -File tools/ae_run.ps1 -Jsx <build.jsx> -Done <after/build_log_<mode>.txt>`. Every scene must say
   `ok`; any `!`, `ERR` or `FATAL` is a failure to fix.
3. Shoot frames from the project left open in After:
   `python tools/ae_shots.py <episode>/after/check_layout layout` (1 frame per scene) and
   `python tools/ae_shots.py <episode>/after/check_motion motion` (8 per scene + overlays on the edit).
   Read the build log first. **Do not open the sheets here:** hand each folder to the `conferir-frames` agent (Agent
   tool, `subagent_type: conferir-frames`) with the client.json path, the motion_map path and the mode (layout / motion);
   it returns short findings per scene (outside the safe area, colour not in client.json, empty frame 0, whip or push at
   the end, overlapping / z-fighting layers, unreadable text, keyed motion visible in the layout). For a doubtful scene
   shoot a strip and send it too: `python tools/ae_shots.py <dir> motion "^S04" "0.2,0.27,0.33,..."` then
   `python tools/sheet.py <dir> 04 5 640`. Open one image yourself only to settle a finding the agent marks doubtful.
   **Gate first:** `python tools/check.py frames <episode>/after/check_motion` (text outside the title safe area,
   WCAG contrast, flat colours not in client.json). Only 0 defects goes to the agent and to the user's review.
4. Fix in `tools/ae_builder.jsx` / `tools/build_ae.py`, rebuild, check again. Only then tell the user.
5. Write/refresh `after/LEIA-ME.md` (what each file is, how to adjust) and log the feedback (below).

## Deliverable
- `<episode>_01_layout.aep` — everything placed, inside the frame, **zero keyframes**. It must stand on its own (an
  editor may animate from it and never open 02): clean names, un-keyed `POS ·` nulls, one comp per scene, `entra:` markers.
- `<episode>_02_animado.aep` — same layout, animated. **Deliver both every time.**
- Main comp `MAIN · …`: reference edit + one precomp per scene at its time, with markers. Scene comps
  `S<id>_<mm>m<ss>s_<TYPE>_<slug>`. Folders 01_MAIN … 05_MOCKUP.
- Rebuilding recreates both projects from zero: say so before overwriting work the editor did by hand.

## Hard rules (each one was a real failure)
1. **Units.** Layout values are cqw (1 cqw = 19.2 px at 1920): convert EVERY x / y / cy.
2. **Layout never carries keyframes.** Blocks move on un-keyed `POS · …` nulls; animation lives on text animators
   (`ENTRADA` / `SAÍDA`), child layers of the null, and the camera.
3. **Fonts by installed PostScript name** (`app.fonts.getFontsByPostScriptName`, first non-substitute). List both the
   variable-font and static names in `ps`.
4. **Measure with the real font** (`sourceRectAtTime`); build rows on the font's ascent, not the ink box.
5. **Parent first, transform after**: attach children while the null is at identity, then move / scale the null.
6. **Stay in frame**: clamp to the safe area (70 px sides, 56 px top / bottom) and re-check after the camera push.
7. **The serif punch sits in front** of the key word; it crosses it only when ≤ 80 % of its width, otherwise touches.
8. **List rows share one size**; never fit each row on its own.
9. **Mockup = `replaceSource` inside the screen comp** (`Screen - …`), never a footage item by name; one duplicate of
   phone + screen comps per scene; remove the template's unused comps.
10. **Clips inside scenes are muted**; short icon clips loop with Time Remap (last key one frame before the end,
    `loopOut("cycle")`); round corners with masks, not track mattes.
11. **Classic 3D renderer** (`comp.renderer = 'ADBE Ernst'`).
12. **Glow = coloured shadows behind** (Drop Shadow, distance 0), never the Glow effect. Measure a flat fill pixel against
    client.json after the build.
13. **Gradient Ramp points are comp px of an unparented, untransformed layer**: gradient type / icons get their own small
    comp (`TXT · …`, `ICO · …`).
14. **No two overlapping 3D layers on the same plane**: each element / child its own tiny depth step; full-frame
    backgrounds 2D; never a frame-sized transparent comp over other 3D type.
15. Keyed actions start from where the entrance lands (`keyValue(numKeys)`), not from the value at frame 0.

## Talking to After Effects (Windows)
- Always through `tools/ae_run.ps1` (ASCII temp copy, `AfterFX.exe -s "$.evalFile(...)"`; it opens After with its window
  first and dismisses modal dialogs via `tools/ae_win.ps1 -Close auto`). No `alert()` in build scripts: write a log file.
- `saveFrameToPng` is asynchronous and does nothing inside the build's undo group: shoot afterwards with `ae_shots.py`.
- A dirty open project is saved aside (`_trabalho-nao-salvo_*.aep`) before replacing it — never discard the editor's work.
- ExtendScript is ES3. After `addProperty`, re-fetch sibling properties by path.
- Write `.jsx` files with the file tool and patch them with small Python replaces, never shell heredocs.
- A project saved by a newer After cannot be opened by an older one: to study or rebuild the editor's file use his
  version (`ae_run.ps1 -AfterExe <AfterFX.exe>`; `study_final.py ... --ae`).

## Default motion recipe (`02_animado`; a client's STYLE.md overrides)
- **Camera in every scene** (two-node, 35 mm, z = -1866.67), four position keys: arrives fast, decelerates INTO a slow
  drift (never a full stop), pushes through on the way out; sides alternate; face overlays ~1/3 of the card travel.
- **Depth**: key word z 0, serif -110, connectors +90, elements -200 to -260, phone -240; every 3D layer compensated so
  the hero-camera frame equals the approved layout.
- **Type**: per-character cascade (Range Selector, Ramp Up, offset -100 to 100, Ease Low 100). Key word tips up from the
  baseline (X rotation, 0.95 s); serif from the camera side (Z, 0.85 s); connectors rise by word (0.7 s). Each row on its word.
- **Elements**: tile turns to face the camera while coming forward (~1 s, decelerating), then floats (`value + sin` on the
  child, never on the POS null).
- **Full-frame cards**: background slides in from below 0.2 s before the word (partner world: from the right), leaves the
  same way; content exits by cascade just before.
- **Opening scene** (first scene, `OPEN-WALL`, or `"abre": true`): frame 0 never empty; the camera starts close and pulls
  back; first row already mid-entrance.
- **Closing scene** (last, or `"fecha": true`): gentle decelerating pull-out; no push-through, exit cascade, card slide or
  whip (`build_ae.py` turns a whip there into a cut).
- **Motion blur once**: layer motion blur (shutter 180) only; never a directional / zoom blur or Force Motion Blur on top.
  No overshoot, no bounce.

## Builder defaults
- **Intensity** `motion.intensity` (1 calm, 1.5 bolder) multiplies camera travel, depth and entrance amplitude; every move
  still decelerates; the final push is limited per scene by distance to the edge (`maxForward`).
- **Card transitions rotate** `motion.transitions` (wipe from below; whip right-to-left, blurred; iris from the element;
  cut), never the same on two cards in a row; the opening is a cut; a scene's `trans` forces one.
- **Long scenes follow the speech**: each row anchored on its meaningful words (stop-words ignored, 5-letter prefix, in
  order, else its longest word) after the previous row; `WARN` flags rows still bunched.

## PAGINAS (camera travelling between blocks)
- Spec: `"type": "PAGINAS", "blocks": [{lock, key, serif, small...}, ...]`; rows anchored on their words across the scene.
- Each block on a page at a fixed place on a large plane (snake: right, down, left, down); a far `mundo` solid in a tint
  of the client's paper/ink covers the travel. One-node camera parented to `RIG · rota da câmera`: arrives on each
  block's first spoken row (`ritmo.viagem_s`, decelerating), pulls back ~0.3 of the camera distance mid-travel, slow
  push while the block animates, `value + sin` drift. Dashed `rota` shape in the accent, revealed leg by leg.
- Layout: every block on its own page, visible only during its words (in / out points, no keyframes), `chega:` / `entra:` markers.

## Composed scenes (types the builder has no recipe for)
Spec in `<episode>/motion/composicao_after.json` (client values live there, never in the repo), built by
`tools/ae_composto.jsx`; format in `references/composicao.md`. A word said twice in a scene without `"n"` WARNs: fix the spec.

## Outside After
Transitions face↔scene, music, slow zooms on the face, recurring templates stay in the editing program unless STYLE.md
asks. SFX for the After scenes: `sfx` skill (`tools/sfx.py plan <episode> --xml <final.xml>`, reads this build's row
times); re-run it after a rebuild that moves rows.

## Feedback
Any approval / rejection of a hand-off goes to the client's STYLE.md section 7 with the date; the rule it changes is
edited here or in STYLE.md — not appended as a duplicate.
