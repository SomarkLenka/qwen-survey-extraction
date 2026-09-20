# Findings

## Accuracy

| | `RRCOT_COVER_SHEET.pdf` | `SUR.pdf` |
|---|---|---|
| Well | EDITH GRAY SCHENDEL USW A 1 | ADAMS UNIT A #1 |
| API | 42-255-35146 | 42-123-32400 |
| Vendor format | COMPASS 5000.14 | PathFinder Energy Services |
| Page type | vector text, **no OCR layer** | rotated 90° raster scan |
| Stations | 185 (MD 1,018.83 → 22,690.00) | 178 (MD 195.00 → 19,166.00) |
| MD strictly increasing | pass (0 violations) | pass (0 violations) |
| TVD integration residual | max 0.17 usft / mean 0.008 | max 0.03 usft / mean 0.004 |
| Cell diff vs ground truth | **162/162 exact** (p9) | **88/88** on md/inc/azm/tvd; **0/44** on offsets |

Ground truth is hand-transcribed, one page per document, under
`data/ground_truth/`. It is a spot check, not full coverage: 1 of 8 table pages
audited for RRCOT, 1 of 7 for SUR.

## The defect: spanning headers shift column mapping

On `SUR.pdf` the offset columns are shifted one position left:

| emitted field | column actually read |
|---|---|
| `ns_ft` | Vertical Section |
| `ew_ft` | N/S offset |
| *(absent)* | E/W offset — dropped |

Root cause is **not** rotation or scan quality. PathFinder's table uses a
two-level header where `TOTAL Rectangular Offsets` spans two sub-columns
(N/S and E/W). The model reads the header correctly — it lists both
`Vertical Section` and `TOTAL Rectangular Offsets` in its `columns` output —
but allots the spanning label a single column slot, so everything downstream
of `TVD` shifts by one.

COMPASS uses flat single-level headers (`N/S`, `E/W` as distinct columns),
which is why `RRCOT_COVER_SHEET.pdf` scored 100%.

Evidence, `SUR.pdf` p2 row 1 — printed: `Vertical Section -0.01`,
`N/S 0.62 S`, `E/W 0.29 W`. Emitted: `ns_ft: -0.01`, `ew_ft: 0.62`.

### Why the validation gates miss it

MD, inclination and TVD are all exactly correct, so both gates pass cleanly —
TVD integration residual is 0.03 usft, better than the document that was
actually read correctly. The gates in `src/validate.py` only exercise
md/inc/tvd; they are structurally incapable of catching an error confined to
the offset columns.

This is the error class `INSTRUCTIONS.md` calls the worst one: it mirrors the
lateral. Catching it needs an independent check — terminus vs. the plat's
stated bottom-hole location, or closure distance/azimuth recomputed from the
offsets and compared to the printed closure columns.

## Secondary findings

- **Multi-survey packet not split.** `SUR.pdf` p2 carries the notes
  *"THE FOLLOWING ARE GYRODATA DIRECTIONAL SURVEYS"*, *"TIED INTO GYRODATA
  DIRECTIONAL SURVEY @ 3718'MD"* and *"THE FOLLOWING ARE PATHFINDER MWD
  SURVEYS"*. The model reported only `tool: "MWD"` and merged both into one
  trajectory, against the spec's multi-survey rule.
- **Flag path untested.** Zero rows were flagged illegible across 363
  stations, so the flag-rather-than-guess behaviour this spec depends on was
  never exercised by these two documents.
- **Operator vs. contractor.** On RRCOT, `operator` returned "Precision Energy
  Services" (the survey contractor) rather than Burlington Resources (operator
  of record), and `well_name` absorbed the operator string. Low impact —
  matching is on API, which was correct on both documents.
- **Negative signs preserved.** On the COMPASS document all 7 negative N/S
  values on the audited page survived exactly.
- **Non-table pages handled correctly.** Headers, plats and certification
  letters were classified as such and returned zero stations rather than
  hallucinating rows. The datum line (`NAD 1927 / Texas South Central 4204`)
  was captured, which the spec requires before grid coordinates are usable.

## Suggested next step

Revise the prompt to force enumeration of leaf sub-columns under any spanning
header before emitting rows, then re-run `SUR.pdf` and re-score p2 against
`data/ground_truth/sur_p02.csv`. The scoring harness already supports the
labelled-offset ground-truth shape, so it is a one-command check.
