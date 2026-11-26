# storyboard — lessons and full descriptions

Read this when planning a client's first long episode, when a scene idea gets rejected and you want the reason behind
the rule, or when you build a dynamic scene type you have not built before. The rules themselves live in SKILL.md.

## What reaches the final cut (studied final projects)
- Editors keep the After scenes where attention is decided: the **cold open and the hook** (first ~100 s). In a long
  episode about half of the candidate beats survive, and the body is finished in the editing program. Default: plan
  After scenes for the cold open + hook (~10) and list the body beats as **editing-program items** for the editor
  (result showcases, subscribe reminder, CTA arrow at sponsor mentions, logo sting) — unless the client's STYLE.md says
  the body gets After scenes too.
- A **cold open** of the episode's strongest visuals (e.g. generated results in 3D) before the first spoken word is a
  common opening; propose it when the episode has such material.
- Scenes stay on screen **2–4 s** (overlays on the face ~2 s).
- Before planning a client's new episode, read its STYLE.md and the latest `final_study/ANALISE.md` (`estudo-final`):
  its own numbers override these defaults.

## Review rounds cost
Each extra review round costs about US$ 1 (five rounds on one long episode cost US$ 18). A text-only round (scenes
described, no drawn still) was a wasted round: the user judges pictures.

## Scene ideas — the reasons
- **The approved ID is a style base, not a set of templates.** Re-using the ID stills as layouts for every scene got
  rejected; so did a "minimal" round that stripped scenes down — richer compositions won.
- **Over screen recordings** punch-ins, zooms, blur around a window, highlight boxes on the UI are the editor's own
  tools in the editing program; proposing them wastes a scene.
- **Two linked words** ("time → money"): two icons side by side in one frame read weaker than one camera travel
  between two blocks, each landing on its word.
- **Fake 3D** (rotateY / scaleX on a coin, a disc, a logo) reads as a bug.
- **Phone-size**: at 1080p captions on cards under ~50 px did not read; text in pills ~76 px.

## Dynamic scene vocabulary — full descriptions
- `PAGINAS`: each spoken topic is a block (page) at a fixed place on a large plane. The camera travels a VISIBLE route
  (dotted line in the accent) from block to block, pulls back a little mid-travel so the route reads, arrives on the
  word and keeps drifting while the block animates. Every block follows the client's `grade`: same margin, alignment,
  hierarchy etiqueta -> titulo -> serifa -> diagrama. Opens close on the first block's element and pulls back; ends
  with a gentle pull-out that shows more of the world. Code: `starters/paginas` (`paginas.json`, one entry per page;
  each text and diagram beat has its `palavra`). After: type `PAGINAS` with `blocks` (after-handoff).
- `GRADE-ONDA`: isometric grid of cards (names / items) that rise in a cascade and light up in a wave on the word.
- `NOS`: two or three nodes (brand / you / ...) joined by a connector that draws itself, a bridge pill on its word.
- `GALHO`: a line of nodes that grows a new branch with a "+" node ("one more front", "a new option").
- `PAINEL-CONSULTA`: an interface that uses itself: query typed with a cursor, highlighter on the key word, list of
  rows, scan line, rows checking one by one, a closing stamp bar.
- `CHECKLIST`: rows that check one by one, each on its own word.
- `PISO-3D`: cards lying on a floor in perspective, the camera flying low over them, rows lifting on the words. Tilt
  the camera toward the middle of the floor, or the floor leaves the frame.
- `UI-CARDS`: interface cards arriving in a cascade (~0.1 s apart), a pointer that moves, clicks (click ring in the
  accent) and toggles.
- `BOARD`: a board larger than the screen with sticky notes and connectors; the camera pans block to block and finally
  pulls back to show everything.
- Transitions with texture, never a dissolve: `EMPURRAO` (the next block pushes in, ~0.4–0.5 s), `ZOOM-BLUR` (cut on
  the word with a zoom blur that collapses in ~0.2 s; the camera is still, so this IS the move's blur), `GLITCH` (short
  offset copies of the title in the client's own colors, as punctuation).
- A strong change every 2–3 s and, with `ritmo: dinamico`, a micro-action (click, check, highlighter, counter) every
  ~0.5 s between them. One accent only, always the client's, in the same jobs (highlighter, click ring, eyebrow,
  route). Real space (plane, floor, depth) instead of zooming one flat card.

## Code path — word matching details
Each page's words are searched from 1.5 s before its arrival: the exact word first, a 5-letter prefix only as a
fallback. A word the speaker repeats or a short common word: anchor on a phrase ("a diferença").
