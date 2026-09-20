# Qwen3-VL directional-survey extraction test

Benchmark of `Qwen/Qwen3-VL-30B-A3B-Instruct` (vLLM, single H200) extracting
RRC directional-survey station tables from PDF filings, scored against
hand-transcribed ground truth.

## Result summary

| | `RRCOT_COVER_SHEET.pdf` | `SUR.pdf` |
|---|---|---|
| Well | EDITH GRAY SCHENDEL USW A 1 | ADAMS UNIT A #1 |
| API | 42-255-35146 | 42-123-32400 |
| Vendor format | COMPASS 5000.14 | PathFinder Energy Services |
| Page type | vector text, **no OCR layer** | rotated 90° raster scan |
| Stations | 185 (MD 1,018.83 → 22,690.00) | 178 (MD 195.00 → 19,166.00) |
| MD strictly increasing | pass (0 violations) | pass (0 violations) |
| TVD integration residual | max 0.17 usft / mean 0.008 | max 0.03 usft / mean 0.004 |
| Cell-level diff vs ground truth | **162/162 exact** (p9) | **88/88 exact** on md/inc/azm/tvd; **0/44** on offsets |

Runtime: ~11 s per table page, ~100 s per document, 200 DPI renders.

## The important finding: spanning headers break column mapping

On `SUR.pdf` the offset columns are shifted one position left:

| emitted field | column actually read |
|---|---|
| `ns_ft` | Vertical Section |
| `ew_ft` | N/S offset |
| *(missing)* | E/W offset — dropped |

Root cause is **not** rotation or scan quality. PathFinder's table uses a
two-level header where `TOTAL Rectangular Offsets` spans two sub-columns
(N/S and E/W). The model reads the header correctly — it lists both
`Vertical Section` and `TOTAL Rectangular Offsets` in its `columns` output —
but allots the spanning label a single column slot. COMPASS uses flat
single-level headers, which is why `RRCOT_COVER_SHEET.pdf` scored 100%.

**This defect is invisible to the standard validation gates.** MD, inclination
and TVD are all exactly correct, so MD-monotonicity and TVD-vs-inclination
integration both pass cleanly (0.03 usft) while the lateral geometry is wrong.
Catching it requires an independent check such as terminus vs. the plat's
bottom-hole location.

## Secondary findings

- `SUR.pdf` contains **two surveys** (Gyrodata gyro + PathFinder MWD, tied in
  at 3718 ft MD). The model reported only `tool: "MWD"` and did not split them.
- Zero rows were flagged illegible across 363 stations, so the
  flag-rather-than-guess path is untested by this run.
- On `RRCOT_COVER_SHEET.pdf`, `operator` returned the survey contractor
  ("Precision Energy Services") rather than the operator of record
  (Burlington Resources), and `well_name` absorbed the operator string.
  Low impact — matching is on API, which was correct.
- Non-table pages (headers, plats, certification letters) were classified
  correctly and returned zero stations rather than hallucinating rows.

## Files

| file | contents |
|---|---|
| `extract.py` | per-page extraction harness (COMPASS doc) |
| `extract_sur.py` | same, pointed at the scanned doc |
| `results.json`, `results_sur.json` | raw per-page output, timings, token counts |
| `rrcot_extraction.json` | 185 stations, merged, **passes all gates** |
| `sur_extraction.json` | 178 stations, carries `_WARNING`; **do not load `ns_ft`/`ew_ft`** |
| `gt_p09.csv`, `gt_s02.csv` | hand transcriptions used for scoring |
| `raw_p*.txt`, `raw_s*.txt` | unparsed model responses |

## Reproducing

Serve the model (the DigitalOcean 1-Click Inference image already ships
vLLM v0.19.0, which is past the v0.11.0 floor Qwen3-VL needs — no `:latest`
pull required):

```bash
docker run -d --name qwen3-vl --restart unless-stopped \
  --gpus all --ipc=host \
  -p 127.0.0.1:8000:8000 \
  -v "$HOME/hf-cache:/root/.cache/huggingface" \
  vllm/vllm-openai:v0.19.0 \
  Qwen/Qwen3-VL-30B-A3B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --dtype bfloat16 --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 65536 --max-num-seqs 4 \
  --limit-mm-per-prompt '{"image":8,"video":0}'
```

Render pages to PNG at 200 DPI into `pages/` (PyMuPDF), then:

```bash
python3 extract.py        # all pages
python3 extract.py 1,5    # specific pages
```

`INSTRUCTIONS.md` (the extraction spec, kept outside this repo) is read at
runtime and used as the prompt.

### Gotcha: GPU lost inside a container

If a container reports `Failed to initialize NVML: Unknown Error` and
`torch.cuda.is_available() == False`, it raced with a previous container's
teardown. A fresh `docker run` recovers it; the restart policy is not the cause.
