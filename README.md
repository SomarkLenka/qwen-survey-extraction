# Qwen3-VL directional-survey extraction test

Benchmark of `Qwen/Qwen3-VL-30B-A3B-Instruct` (vLLM, single H200) extracting
RRC directional-survey station tables from PDF filings, scored against
hand-transcribed ground truth.

## Headline

Two filings, 363 stations, ~170 s of GPU time.

- **COMPASS filing (vector text, no OCR layer): 162/162 cells exact.** All
  gates pass. Loadable as-is.
- **PathFinder filing (rotated raster scan): md/inc/azm/tvd 88/88 exact, but
  all 44 offset cells wrong.** A two-level spanning header shifts `ns_ft` and
  `ew_ft` one column left and drops E/W entirely — and **both validation gates
  pass anyway**, because MD/inc/TVD are correct.

Full analysis in [`docs/FINDINGS.md`](docs/FINDINGS.md).
Measured throughput and token counts in [`docs/METRICS.md`](docs/METRICS.md).

## Performance

| | RRCOT_COVER_SHEET.pdf | SUR.pdf |
|---|---|---|
| pages | 14 (8 tables) | 9 (7 tables) |
| stations | 185 | 178 |
| wall clock | 87.4 s | 81.0 s |
| prompt / completion tokens | 66,804 / 16,996 | 43,068 / 15,865 |
| output rate (end-to-end) | 194.5 tok/s | 195.9 tok/s |
| cost per station | 438 ms, 87 output tokens | 440 ms, 87 output tokens |

Model load was ~360 s. TTFT was not measured (non-streaming requests), so the
rate above includes prefill and image encoding. Per-page recordings are in
[`results/metrics.json`](results/metrics.json).

## Layout

```
prompts/INSTRUCTIONS.md   extraction spec, used verbatim as the prompt
src/
  render.py               PDF -> PNG at a given DPI
  extract.py              one request per page -> per_page.json + raw/
  merge.py                per-page -> one record in the spec's schema
  validate.py             MD monotonicity + TVD integration gates
  score.py                cell-level diff against a ground-truth CSV
  metrics.py              timings/token usage -> results/metrics.json
  report_metrics.py       results/metrics.json -> docs/METRICS.md
data/ground_truth/        hand transcriptions used for scoring
results/<doc>/
  per_page.json           per-page output incl. _secs and _usage
  extraction.json         merged, in the spec's schema
  raw/                    unparsed model responses
results/metrics.json      measured performance, aggregate + per page
docs/                     FINDINGS.md, METRICS.md
```

## Reproducing

Serve the model. The DigitalOcean 1-Click Inference image already ships vLLM
v0.19.0, past the v0.11.0 floor Qwen3-VL needs — no `:latest` pull required:

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

Then:

```bash
python3 src/render.py  RRCOT_COVER_SHEET.pdf pages     p 200
python3 src/extract.py --pages pages --prefix p --out results/rrcot
python3 src/merge.py   --in results/rrcot --source RRCOT_COVER_SHEET.pdf
python3 src/validate.py results/rrcot/extraction.json
python3 src/score.py    results/rrcot/per_page.json 9 data/ground_truth/rrcot_p09.csv
python3 src/metrics.py && python3 src/report_metrics.py
```

Requires `pymupdf`. Source PDFs are gitignored.

## Gotcha: GPU lost inside a container

If a container reports `Failed to initialize NVML: Unknown Error` and
`torch.cuda.is_available() == False`, it raced with a previous container's
teardown. A fresh `docker run` recovers it; the restart policy is not the cause.
