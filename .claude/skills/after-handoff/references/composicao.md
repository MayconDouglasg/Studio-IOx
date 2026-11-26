# after-handoff — composed scenes spec (`composicao_after.json`)

Read this only when a scene's type has no recipe in the builder and you write or fix `composicao_after.json`.

- Spec: `<episode>/motion/composicao_after.json` -> `"cenas": {"<scene code>": {...}}` (client values live there, never in
  the repo). `fundo`: `mundo` (paper + corner glow 2D, grid wall far in 3D, optional `chao`) or `cara` (face overlay
  with `sombras`: vig / low / edgegrid / lado-esq / lado-dir). `camera`: `deriva` (arrive, drift, push out; `forca` 0.33
  over the face) or `viagem` (`paragens` {x, y, z, palavra}, reached in `ritmo.viagem_s`).
- `els` in px of the approved still: `texto` (partes key / ser, cor `grad`, `top` = CSS top), `icone` (`nome` from
  `assets/icones/<nome>.svg` then `icones` sources, or inline `svg`), `caixa`, `circulo`, `linha` (SVG `d`), `media`,
  `grupo` (own comp, local px), `moeda`, `segmentos`. Each: `entra` {palavra | t, como: sobe / serifa / escreve / pop /
  voa / desenha / fade}, `anim` [{prop, de, ate, v}], `z`. List order = stacking order. `corte.insercoes` maps word times
  to a newer cut.
- Built by `tools/ae_composto.jsx` (inserted into `ae_builder.jsx`); icons via `tools/svg_shapes.py`. A word said twice in
  a scene without `"n"` WARNs (the 1st wins): fix it in the spec.
