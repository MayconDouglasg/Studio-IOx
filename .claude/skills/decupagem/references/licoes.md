# decupagem — measured history and long lessons

Read this only when a rule in SKILL.md surprises you, when you tune a threshold (`HALLU`, `esticada_s`, `settle`,
`inner_gap_s`), or when you change `decup.py` / `decup_stage2.py`. The rules themselves live in SKILL.md.

## Transcription by chunks (step 3)
Whisper on the whole file merges takes the speaker repeats in quick bursts and can place words seconds off; every
later step then works on wrong text and keeps the worse take. So `trans` splits at real silences
(`decup.chunk_silence_s`, default 0.45 s), transcribes each chunk and aligns its word times to the voice (Whisper puts
them ~0.2 s early; the printed "word shift median" says by how much). `--whole` / `decup.transcribe: "whole"` is the
old single pass.

## Hallucination filter (step 3)
Whisper writes stock phrases into chunks with no speech (keyboard, mouse, room noise): "Obrigado por assistir",
"Acesse o site www.<marca>.com", "Legenda por <nome>", and it reads the vocab prompt back as a sentence. On a long
episode that was about 4 in 10 of all segments, and three vocab echoes hid real speech. What `trans` does:
- (a) gives the prompt only to chunks long and loud enough to be speech; a short or quiet chunk goes without it first
  (noise then reads no_speech_prob ~0.9 instead of a fluent phrase) and gets the prompt only once it proved to be speech;
- (b) re-transcribes without the prompt any chunk whose text reads the prompt back;
- (c) drops a segment Whisper calls silent, or one with almost no voice in the audio, and a known stock phrase
  (pt/en/es list `HALLUCINATIONS` in `decup_stage2.py`, plus the client's `decup.alucinacoes`) where the voice is weak.
Always checked against the real voice energy: a stock phrase said with real voice stays (flag `h`). Thresholds:
`HALLU` in the code, any key overridable in client.json `decup.alucinacao` (`null` turns the filter off).
Measured on that episode (304 chunks): stock phrases / vocab echoes went from 161 of 403 segments to 0; every dropped
segment had ≤ 0.3 s of real voice; the three hidden passages came back as text; 84 of the 86 clips of the validated cut
kept every word and the other 2 lost only text an independent re-listen had already found hallucinated. Cost: ~13 %
more Whisper calls (the prompted second pass on short real lines).

## Why the cut is made by XML, not inside Premiere
Building the cut inside Premiere through the `premiere` MCP was measured on a long episode: as faithful to the frame,
but without camera switching, disabled tracks, `02_TAKES_DESCARTADOS` or the `REVER` markers, ~60 calls instead of one
import, and a destructive ripple. `import_fcp_xml` through the MCP opened a modal dialog, the bridge blocked (two 120 s
timeouts) until the user closed it, and the MCP then stayed in `HOST_RECOVERY_REQUIRED`, refusing every edit (saving
included) until the recovery was acknowledged. Without `acknowledge_operation_recovery` in the MCP's tool profile one
timeout leaves it read-only until its server restarts.

## Second pass (`polish`) — where the rules came from
From an editor's final cut of a long episode made from our cut: the editor changed **no take** and still removed about
4 s per minute in about 8 places per minute, all small.
- Whisper glues a hesitation, a false start ("foi… foi buscar") or a pause onto the next word, which then lasts far too
  long (a "foi" of 1.2 s). The editor cut the start of about 3/4 of those words, up to where the voice restarts after a
  real silence. `esticada` matched the editor about 70 % of the time, by seconds.
- The same editor kept about 90 % of the crutch words, and no pause or position told the removed ones apart: cutting
  every crutch word that opens a breath group would have been wrong about 4 times out of 5.
- Trial (defaults + 12 decisions): what the editor still removed went from 52 s to 40 s, at the cost of 7 s cut that the
  editor kept (5 of the 12 decisions were wrong: a "basicamente" whose stretched start was already cut, an "e" that
  carried the list, a second "Ok,", a rephrasing taken for a repeat, a click line the editor only shortened). `--auto`
  removed as much but cut 32 s the editor kept. Hence: few `muleta` cuts, only the clear ones.

## Cut points (`settle`)
From an editor's cut: our outs sat 7–28 dB under the speech peak (the word still sounding, the cut felt like it chopped
the sentence); the editor's at 38–46 dB, about 0.1 s after the voice fell under -30 dB. With `settle` (floor + 12 % of
the speech range) the outs landed within ~0.05 s of the editor's.

## What to expect
On a long episode the semantic pass catches most of what the rules leave (about 3/4 of the words the editor would
still remove) at the cost of a few choices between two versions of the same sentence (they stay in
02_TAKES_DESCARTADOS). Measure it per client with `edit_study.py` and keep the numbers in the client's STYLE.md.
