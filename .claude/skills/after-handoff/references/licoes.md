# after-handoff — failures behind the rules and how editors use the hand-off

Read this when a build fails in a way SKILL.md does not explain, when you change `ae_builder.jsx` / `ae_composto.jsx` /
`build_ae.py`, or before changing the default motion recipe. The rules themselves live in SKILL.md.

## The failures behind the hard rules
- Units: v1 used the map's cqw values as pixels and every lockup landed off-screen, top-left.
- Keyed Position on a layer the editor wants to move makes it "adjust frame by frame": hence un-keyed `POS ·` nulls.
- Fonts: a family is often installed only as a variable font, whose instances have other PostScript names than the
  static files. A substituted font also breaks every measurement.
- Rows built on the ink box jump with the letters they contain; build them on the font's ascent.
- `layer.parent = x` keeps the world position by rewriting the child's transform: attaching after moving the null
  shifted every child.
- Things that fit at rest left the frame at the end of the camera push.
- Unused template comps with missing fonts opened a blocking dialog.
- Track mattes did not survive 3D; masks do.
- Glow effect added light on top and turned a mid-blue accent fill into near-cyan `51,231,255`.
- Gradient Ramp on a parented, moved layer missed the glyphs.
- Overlapping 3D layers on the same plane z-fought in Classic 3D: text turned into a row of dots, a clock face vanished
  under its hands, the background got grain.

## Talking to After Effects — why
- `AfterFX.exe -r "<path with accents>"` is silently dropped: `ae_run.ps1` copies the script to an ASCII temp path.
- After started cold by `-s` runs headless: it builds and saves, but `saveFrameToPng` writes nothing and it quits.
- Modal dialogs ("Solucionar fontes", untitled alerts) blocked scripts for minutes.
- Heredocs collapse double backslashes and long scripts do not fit in one.

## Long scenes follow the speech (example)
Each row is anchored on its meaningful words after the previous row, so a 13 s checklist spread as
0.3 / 2.2 / 5.6 / 8.2 / 10.6 s instead of everything in the first second.

## PAGINAS
Checked in After on a test episode (2026-11): the route, arrivals on the words and the pull-out ending render.

## How editors really use the hand-off (studied final projects)
Check on every client with `estudo-final`; the client's own numbers go in its STYLE.md.
- **The layout is the real base.** An editor may animate by hand from `01_layout` and never open `02_animado`: clean
  names, un-keyed `POS ·` nulls, one comp per scene and `entra:` markers (the editor times every line on them).
- **Shorter on screen than planned**: scenes trimmed to 2–4 s (overlays on the face ~2 s), not 4.5–6 s.
- **A text entrance editors reach for**: one per-character animator per line, Position y +~100 px and Opacity 0, Range
  Selector Offset −100→100 on linear keys, 0.3–1.2 s (~0.7 s), each line on its word; no exit animation (hard cut, or
  the card background off in 0.1 s). A candidate preset for the builder.
- **"Playing with space" = the camera travels.** Content spread in 3D (blocks outside the frame, e.g. x ±3000 or
  y +1300) and the camera visits them: camera parented to a chain of nulls, each null ONE move of 2 keys (~1.2–2 s,
  fast start, long landing), legs overlapping — arrive, slide to the next block, push through in Z to leave. One huge
  far solid as background so the travel never shows an edge.
- **Readability on the face**: white type with a soft drop shadow, a large dark gradient from the text's side that
  fades in (~0.2 s), the element tile sliding in from that side.
- **What stays in the editing program**: transitions between face and scenes, SFX, music, slow zooms on the talking
  head, recurring templates (subscribe, CTA arrow).
