# Motion studio rules

## Pipeline (one skill per stage — read the skill before running its tools)
1. `novo-cliente` — register a client / start an episode (`tools/studio.py`).
2. `motion-refs` — learn the client's style from references -> STYLE.md + client.json.
3. `decupagem` — raw multicam -> synced, cut, camera-switched Premiere XML (editor finishes the edit).
4. `storyboard` — editor's final cut -> scene spec, review page, approved motion_map + assets.
5. `imagens-apoio` — script + editor's final cut -> supporting footage (client folder, Magnific, Pexels, Pixabay,
   AI) downloaded with credits into `<episode>/APOIO/<video>/` + a new XML copy with one marker per moment
   (`tools/apoio.py`; optional, beside the storyboard). API keys only in env vars / `studio.config.json`.
6. `after-handoff` — motion_map -> two After Effects projects (01_layout, 02_animado), checked by frames.
   `sfx` (beside it) — motion events -> SFX plan + a new XML copy with the cues on audio tracks (`tools/sfx.py`).
7. `estudo-final` — when the episode is finished: read the editor's final .aep + .prproj (`tools/study_final.py`),
   compare with what we delivered and write the lessons into the client's STYLE.md and the skills.
`python tools/studio.py doctor` checks this PC; `python tools/selfcheck.py` checks the repository (run it before
every commit; CI runs it too); `GUIA.md` is the team's guide (Portuguese), `README.md` the public front page.
`python tools/studio.py arsenal` writes `arsenal.html` (catalog of every skill + this PC; not in git);
`--serve` adds a local control panel (127.0.0.1 only, a closed list of studio.py actions).
- **Every new skill or agent gets an `arsenal:` block** in its front matter (etapa, area, titulo, resumo,
  entradas, saidas, ferramentas, modelo, pedidos; format in `tools/arsenal.py`). A new external skill gets an
  entry in `arsenal/extras.json` instead (updates overwrite its files). The page lists any skill without one.

## Token economy (measured on a long episode, 2026-11)
Cost comes from re-reading the conversation on every call, not from the work: at the end of one episode each
call re-read 400–735k tokens and that alone was US$ 30 of US$ 70. On the Pro plan 1 % of the 5-hour
limit is about US$ 0.50 of API-priced usage. Target: a long episode about US$ 10, a reel about US$ 7
(US$ 3–3.5 in a batch).
1. **One fresh session per stage** (decupagem / storyboard / imagens-apoio / assets / after-handoff). The skills and
   the files carry everything a stage needs; when a stage is approved, say so and suggest the next
   stage in a new session instead of continuing in a long one. Never chain several episodes or
   stages in one conversation.
2. **Model per stage**: Opus for the mechanical stages (decupagem, assets, building and checking the
   After projects); the most capable model only for the creative choices of the storyboard, if the
   user wants it. Switch models between sessions, not mid-session (it resets the cache).
3. **Few storyboard rounds**: ask for every note in one pass on the review page and apply them all
   at once; with an approved ID aim for 1–2 rounds.
4. **Batch short videos**: several reels of the same client in one decupagem run, one storyboard page
   and one After build, so the fixed cost is shared.
5. **Light images**: read logs and numbers before images; look at one compact contact sheet first and
   zoom only into the scenes with a problem. Every image stays in the context for every later call, so frame
   checks go to the `conferir-frames` agent (Sonnet), which looks at the images and returns only text findings.
6. **Development apart from production**: improving tools, skills or rules happens in its own session
   (and branch), never in the middle of an episode.

## Client work
- A client is a folder anywhere on disk, registered in `studio.config.json` (per PC, not in git;
  `python tools/studio.py clients` lists them, `where <slug>` prints the path). Unregistered clients
  fall back to `clients/<slug>` and `projects/<slug>` inside motion-studio.
- Before any motion for a client, read its `STYLE.md` — that is the brand brief. Tools read the
  machine tokens from its `client.json`. Never open raw reference videos; use the `motion-refs` skill
  (`tools/ingest.py` digests each video once, Claude reads only new digests).
- Episodes live in the client's projects folder, each with an `episode.json` (vocab, partner, media).
  "Brand accuracy" = STYLE.md section 6.
- Any approval/rejection from the user gets logged in STYLE.md section 7 (feedback log), and the rule it
  touches is changed in STYLE.md or in the stage's skill — after every approved stage, write the
  lessons down and ask the user what else to confirm.
- **This repository is for every client.** Skills, tools, CLAUDE.md, GUIA.md and `clients/_template` hold only
  general rules and neutral defaults — never a client's name, episode, numbers, colors, fonts or taste. Those
  live in the client's folder (STYLE.md, client.json), which is never committed. Turn a client lesson into a
  general rule before it enters a skill, and keep the client's version in its STYLE.md.
- The look rules below are defaults; a client's STYLE.md overrides them where it says so.
- Never overwrite something already delivered (an .aep, an XML the editor imported): test with
  `--out` / `--name`.

## After Effects hand-off
- Use the `after-handoff` skill (build with `tools/build_ae.py`, run with `tools/ae_run.ps1`, check with
  `tools/ae_shots.py`). Layout never carries keyframes; deliver `01_layout` and `02_animado`;
  look at frames rendered by After before saying it is done.

## Code path (HTML -> MP4 / ProRes 4444)
- A scene or a whole film whose `caminho` is `codigo` (storyboard skill) starts from `starters/<modelo>/`
  with `tools/codigo.py novo`: the page reads the client's tokens (client.json), the voice's word times
  (words.json) and its own content file; it never hard-codes a client's colors or fonts.
- `node render.mjs --project <folder>` renders any folder on disk; `--alpha` exports ProRes 4444 with alpha
  for the editor to lay over the presenter; `--timeline` hands the film's events to the sound step.

## Render contract
- Every film is a pure function of time: `window.seek(t)` paints frame t.
- No CSS transitions, no setTimeout, no requestAnimationFrame in render mode,
  no state carried between frames. Seeded noise only (mulberry32), never Math.random.
- Render with `node render.mjs`, encode H.264 yuv420p, CRF 16.

## Look
- Banned defaults: centered title on gradient, everything fading in,
  corner labels and frame borders, glow on UI chrome, generic particle bursts.
- One display face, one UI face. One accent color unless the brief says otherwise.
- Every 2 to 4 seconds something new must happen on screen (a client with `ritmo: dinamico` in client.json:
  every ~1.5 s, entrances ~0.45 s).
- Never invent a color: only the colors in the client's client.json, and tints / shades mixed from them.
  A "support" color the client never used (an extra dark blue, a neon) is the first thing to be rejected.
- Never open on an empty frame: frame 0 already shows an element (start close on it and pull back).
- Never end on a whip: close with a gentle pull-out that decelerates into the last frame.
- Motion blur once per move: the shutter (sub-frames in code, layer motion blur in After). Never stack a
  second blur (directional, zoom, Force Motion Blur) on the same travel.
- Every movement lands on the spoken word: anchor scenes, camera arrivals and SFX to word times.

## Sound
- Score and SFX are synthesized in code unless a track is supplied. SFX from the team's library come from the `sfx` skill
  (`tools/sfx.py`): one sound per movement, picked only from sounds the user approved by ear, peak on the word, the same
  sound always on the same layer, stacked cues under -1 dBTP; the library path is per PC (`sfx_library` in
  studio.config.json), never in the repository.
- Place hits on the measured beat grid (beats.json) or, under a voice, on the spoken words. Loudness -14 LUFS.
- Under a voice the bed sits low (about 0.22 of its level; `tools/codigo.py mix`) and the SFX land on the words.

## Loop before you show me anything
0. Zero measurable defects first: `python tools/check.py decup|render|frames ...` (report only; it never fixes).
   Fix what it counts and run it again; taste review only starts at 0 defects.
1. Render one frame per beat as a contact sheet and have it LOOKED at (`conferir-frames` agent; text findings back).
2. Score it 1-10 on: hook in first 2s, readability at phone size,
   motion quality, variety, brand accuracy, sound sync.
3. Fix the 3 worst problems. Repeat until every score is 8+.
4. Only then do the full render.
