# <Cliente> — Style bible

> Single source of truth for this client's motion. Read THIS, never the raw reference videos.
> Updated by the `motion-refs` skill from `_digest/`. Keep under ~250 lines: rules, not essays.
> Every rule carries its evidence in brackets, e.g. [canal/ep12 @0:42] or [insp/foo].

## 0. Snapshot
- Channel / format: <long YouTube? shorts? both> — aspect: <16:9 / 9:16>
- One-line feel: <e.g. "editorial, warm, confident; type does the talking">
- Measured pacing (channel average): <cuts/min>, median shot <s>, motion energy <n>, music <bpm>, <LUFS>

## 1. Identity (non-negotiable)
- Logo / wordmark usage: <files in brand/>, safe area, never <...>
- Colors (hex, role, share): primary <>, accent <>, background <>, text <>
- Type: display <font, weights, case>, UI/caption <font>; tracking / leading habits
- Recurring signature elements: <lower thirds, bug, progress bar, intro sting...>

## 1b. Format choices (mirror them in client.json)
- Presenter (`modo_apresentador`): <sobre = motion over the talking head | bolha = presenter in a round
  bubble inside the motion | tela_dividida = split screen | so_voz = no presenter, full motion under the voice>
- Rhythm (`ritmo`): <calmo = entrances ~0.8 s, something new every 2–4 s | dinamico = entrances ~0.45 s,
  something new every ~1.5 s, a micro-action every ~0.5 s>
- Grid (`grade`): margin <fraction of the short side, e.g. 0.08>, alignment <esquerda | centro>, hierarchy of a
  block <etiqueta → título → serifa → diagrama>, title underline <yes / no>
- Default path of a scene (`caminho_padrao`): <after | codigo | ia>; approved world / model: <e.g. "pages on a
  dotted plane joined by a dotted route">
- Approved diagrams / scene types: <...> [evidence]

## 2. Motion vocabulary — what the channel already does (from refs/canal)
- Entrances / exits: <how text & elements arrive and leave; easing character>
- Transitions between ideas: <cut / wipe / match-cut / zoom ...>
- Text on screen: <when, how long, how many words, highlight method>
- Camera / 2.5D: <push-ins, parallax, shake...>
- Data / numbers / maps / screenshots: <treatment>

## 3. Borrowed ideas (from refs/inspiracao) — allowed, adapted to identity
- <technique> → how it maps to this brand [insp/<file>]

## 4. Sound
- Music character, SFX palette, where hits land, loudness target
- SFX intensity (mirror it in client.json `sfx.intensidade`): subtil / medio / forte — a brief that asks for simple,
  never exaggerated motion is subtil. Movements this client wants silent, sound families it rejected, themes it allows
  (`sfx.incluir` / `sfx.excluir`). Sounds approved by ear for this client: <movement → sound name>.

## 5. Do / Don't
- DO: <...>
- DON'T: <...> (includes the global banned defaults in CLAUDE.md)

## 6. Review scorecard additions
- "Brand accuracy" means: <3–5 concrete checks against sections 1–2>

## 7. Feedback log (newest first — the most valuable section)
- YYYY-MM-DD <project>: approved / rejected <what> because <why> → rule changed: <...>
