# decupagem — verify in Premiere (optional, read-only)

Read this only for step 9, after the editor imported the XML by hand. Why the cut is never built inside Premiere:
`licoes.md`.

The cut is always made by the XML (only it carries camera switching, disabled tracks, `02_TAKES_DESCARTADOS`, `REVER`).
- **The editor imports the XML by hand** (File > Import). Never `import_fcp_xml` through the MCP (modal dialog blocks
  the bridge, then `HOST_RECOVERY_REQUIRED`).
- Editing through the MCP needs `acknowledge_operation_recovery` in its tool profile; otherwise save by hand (Ctrl+S).
- Small fixes only: `ripple_remove_timeline_ranges` (dry-run -> show the user -> apply), ≤ 50 ranges per call, last
  batch first, a new dry-run per batch (single-use token). Anything bigger: fix `edl.json` / `semantic.json`, new XML with `--name`.

Serialize the calls (shared Premiere state):

| Check | Tool | Expect |
|---|---|---|
| Bridge | `verify_premiere_connection` | connected, project + sequence active |
| Sequences | `list_sequences` | `01_DECUPADO`, `02_TAKES_DESCARTADOS`, `00_SINCRONIZADO_BRUTO` (or `--name` ones) |
| Duration, clips | `get_timeline_summary` | 01 = "mantido" in `report.md` (± a frame per clip); clips per track = the XML's |
| Gaps | `get_timeline_gaps` (01, `min_gap_seconds` 0.04) | none on V1/A1 |
| Markers | `list_markers` (01) | as many `REVER` as `report.md` |
| Media | `get_offline_media` | nothing offline |
| Read-back | `set_active_sequence` 01, `export_as_fcp_xml` (into `<episode>/work/readback/`) | user closes any Translation Report; then `python tools/edit_study.py <episode> "<readback.xml>" <sequence> --out <episode>/work/readback` -> removed / restored ≈ 0 words |
| After a timeout | `inspect_operation_recovery` | read what is pending; never retry an edit before |

Report the numbers in a few lines (or in `LEIA-ME.md`); never paste tool output into the conversation.
