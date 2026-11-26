---
name: imagens-apoio
description: Find supporting footage and photos (b-roll) for an edited video from its script and its final cut — pick the moments that need an image, anchored to the second the word is spoken, search the client's own footage first and then stock (Magnific, Pexels, Pixabay) or AI generation, download the picks with credits into the episode folder and write one marker per moment into a new copy of the Premiere XML. Use when the user asks for imagens de apoio, b-roll, stock footage, cobertura, inserts of footage over the talking head, or "coloca imagens nos momentos certos".
arsenal:
  area: pipeline
  ao_lado: storyboard
  titulo: "Imagens de apoio"
  resumo: "Lê o roteiro e o corte final, escolhe os momentos que pedem imagem e baixa os clipes (acervo do cliente, Magnific, Pexels, Pixabay ou IA) com créditos e marcas no XML."
  entradas: ["xml|XML final do Premiere", "md|roteiro / briefing (PDF ou texto em MATERIAL)", "pasta|acervo do cliente (opcional)"]
  saidas: ["pasta|APOIO/<vídeo>/ com os clipes numerados", "md|CREDITOS.md", "json|manifest.json", "xml|cópia do XML com uma marca por momento"]
  ferramentas: ["apoio.py"]
  modelo: "Opus"
  pedidos: ["Imagens de apoio para o <vídeo> do <slug>: o XML final é <arquivo.xml> e o roteiro está em MATERIAL.", "Troca a imagem do momento 3 pela opção 2 e baixa de novo."]
---

# imagens-apoio

After the editor's cut, beside the storyboard. Output: a folder of supporting clips named by order and moment,
`CREDITOS.md`, `manifest.json` and a NEW copy of the Premiere XML with one marker per moment. The editor places
the clips; there is no review page in this version. Everything heavy runs on this PC; Claude reads only the
transcript, the script and the tool's numbers, and at most one compact contact sheet.

## Inputs (stop and ask for what is missing)
- The editor's final XML exported from Premiere (or the reference mp4 of the final cut, `--video`).
- The script / briefing: episode.json `briefings`, else PDF / TXT / MD in the episode's `MATERIAL/` folder.
- The client's `STYLE.md` (what images fit the brand, what is forbidden) and `client.json` `apoio` block.
- Format: from the XML's sequence size, else episode.json / client.json `frame` (vertical 9:16 or horizontal 16:9).

## Sources (client.json `apoio.sources`, in order; each one is skipped cleanly when not configured)
1. `local` — the client's own footage: client.json `apoio.local_dirs` (relative to the client folder; default
   `APOIO`, `acervo`, `broll`) or `--local-dir`. Matched by file and folder names; `--clip` adds CLIP on the GPU
   (open_clip ViT-B-32, ~600 MB downloaded once; image embeddings cached in the client's `_digest/apoio_clip.npz`).
   Use `--clip` only when the folder has camera names (IMG_1234) instead of descriptive names.
2. `magnific` — stock videos/photos via API (`MAGNIFIC_API_KEY`). Each download calls the API's download endpoint,
   which is what counts and reports it to Magnific; the tool keeps a per-PC daily ledger (`apoio_downloads.json`,
   limit `keys.magnific_daily`, default 100) and stops there. Premium items need a plan that allows them.
3. `pexels` — `PEXELS_API_KEY`. 4. `pixabay` — `PIXABAY_API_KEY`.
5. `ia` — last resort: the tool lists the moments in `gerar_ia.json`; generate them with the `media-use` skill.
`python tools/apoio.py fontes <episode>` says which are configured (no network).

## Steps (from motion-studio/, one fresh session)
1. **Transcribe the final cut**: `python tools/apoio.py palavras <episode> --xml "<final.xml>" [--seq <name>]
   [--name <video>]` -> `APOIO/<video>/_work/{words.json, transcript.md, roteiro.txt, source.json}`. The audio is
   rebuilt from the XML's speech track (reusing the decupagem's `work/audio/*.wav` when they exist); with nested
   sequences pass `--video <reference.mp4>`.
2. **Pick the moments** reading only `_work/transcript.md` and `_work/roteiro.txt` (not the media). Write
   `APOIO/<video>/momentos.json`:
   ```json
   {"moments": [{"anchor": "conta de energia", "near": 12.3, "dur": 3, "desc": "pessoa olhando a conta de luz",
                 "q": "person looking at electricity bill", "q_pt": "conta de luz", "local": ["conta", "energia"],
                 "kind": "video"}]}
   ```
   - `anchor` = the words as said (the tool finds the exact second), `near` = approximate second, `dur` 2–5 s.
   - `q` = stock search in English (Pexels / Magnific search best in English), `q_pt` = Portuguese (Pixabay,
     client folder), `local` = words likely in the client's file names; `kind` video (default) or photo.
   - What deserves an image: a thing, place, product, person type or action that is named; an idea that has an
     obvious concrete picture; a number with a visual (money, people). Follow the script's own image directions
     ("Imagem:", "Visual:") first — they are the client's intent.
   - What does not: the hook's first seconds when the speaker must be seen, the CTA, lines that become motion
     cards in the storyboard (product lists, on-screen text), abstract filler. Propose only where it helps —
     there is no fixed rhythm. Defaults: at least `min_gap_s` (4) between moments and at most `max_per_min` (6);
     the client's `apoio` block and STYLE.md override them.
   - Never use stock that shows another brand, logos, or claims the client cannot make (STYLE.md section 6).
   - **Region**: images must look like the client's country and audience. Mark `"regional": true` on every moment
     whose picture changes by country — places, cities, government, city halls, money, documents, streets, homes,
     shops, everyday scenes — and the tool appends client.json `apoio.regiao` (en / pt) to its queries
     (`regional_padrao: true` does it for every moment). Name a landmark when there is one ("Brasilia national
     congress"). Generic terms bring foreign capitols and dollars: reject them on the sheet even if the query was regional.
   - When the user asks for a list said fast (products, services), one image per item as a quick montage is fine:
     the `PERTO` / `DENSO` warnings are expected there.
3. `python tools/apoio.py checar <episode> --name <video>` — every moment must resolve; fix each `MISS`
   (anchor not said that way) and read `PERTO` / `DENSO`.
4. **Search**: `python tools/apoio.py buscar <episode> --name <video> [--per 4] [--clip]` (`--dry` prints the
   queries without calling anything). Writes `_work/candidates.json` and `_work/folha_1.jpg` (one row per moment,
   candidates numbered, `CROP` in red = wrong orientation). Read the printed lines first — each candidate's title
   is printed under its moment; check it before picking (a thumbnail of banknotes or a capitol does not show the
   country) — and look at the sheet once, only if a choice is doubtful. Candidate 1 is the default; change it in `momentos.json` with `"pick"`:
   a number, `"<source>:<id>"`, `"ia"`, `"arquivo:<path>"` (a file you already have) or `"nada"`. A new `q` needs a
   new `buscar`: pass `--ids 7,8` to search only those moments and keep every other candidate (and pick) as it is.
   Adding moments later: keep `id` in time order; rename already downloaded files to their new `NN_` prefix so
   `baixar` reuses them instead of downloading again.
5. **Download**: `python tools/apoio.py baixar <episode> --name <video>` -> `APOIO/<video>/NN_MMmSSs_<desc>.ext`,
   `CREDITOS.md` (source, author, license, link, id), `manifest.json`; already downloaded files are kept.
   Moments marked `ia` (or with no candidate when `ia` is a source) go to `gerar_ia.json`: generate them with the
   `media-use` skill in the right frame size, save them in the same folder with that file name, set
   `"pick": "arquivo:<path>"` (and `"credit"`) and run `baixar` again.
6. **Markers**: `python tools/apoio.py marcas <episode> --name <video>` -> `APOIO/<video>/<xml>_apoio.xml`, the
   sequence renamed `<name>_APOIO`, one marker per moment (start = the spoken word, length = `dur`, comment =
   description | file | source | crop note | the words). Never overwrites: it adds `_v2`, `_v3`. Tell the editor
   to import that XML and drag the clips from `APOIO/<video>/` onto the markers.
7. Report: moments, sources used / skipped (no key), downloads left today on Magnific, crops to do. Log the
   user's approvals and rejections of the images in STYLE.md section 7 and turn them into `apoio` rules there.

## Tests and safety
- `--out <folder>` on every command writes nothing in the episode (CLIP cache also stays there).
- Keys live only in environment variables, the user's `~/.motion-studio/chaves.json` (`apoio.py chaves` creates
  it) or the per-PC `studio.config.json` (`keys`), never in git or in a client file. Never ask the user to paste a
  key in the chat: they paste it in that file. Do not search the web or scrape sites for footage: only these APIs and the client's folders.
- Several reels of one client: run `palavras` once per XML (`--name V1`, `V2`...) in the same session.
