# AGENTS.md

Operating guide for agents working on this repo: provisioning a machine,
serving the model, and running filings through the production pipeline.

Read [`docs/FINDINGS.md`](docs/FINDINGS.md) before trusting any output. There
is a known, reproducible defect that **passes every automated gate**, and it is
the first thing you need to understand.

---

## 1. Ground rules

1. **Never load `ns_ft`/`ew_ft` from a document flagged `SPANNING_HEADER`.**
   See §7. MD/inc/azm/TVD from those documents are fine.
2. **Do not "fix" numbers.** The spec (`prompts/INSTRUCTIONS.md`) requires
   `null` plus a flag over a guess. A confident wrong digit is worse than a
   gap, because the gap is recoverable downstream.
3. **No unit conversion, ever.** Values stay in usft/degrees as printed.
4. **Preserve signs and hemisphere labels exactly.** A dropped `−`, or an `S`
   read as `N`, mirrors the whole lateral. This is the worst error class.
5. **Never commit secrets.** `.env` is gitignored; keep it that way (§9).
6. **Re-score after any prompt change.** A prompt edit that is not re-scored
   against `data/ground_truth/` is an unverified change. Run §8.

---

## 2. Provisioning a new machine

Target: one NVIDIA H200 (141 GB) or H100 (80 GB). The model is ~61 GB in
bf16, so a 141 GB card leaves comfortable KV-cache headroom at 64K context.

### 2.1 If using the DigitalOcean 1-Click Inference image

The image already ships Docker, the NVIDIA driver, CUDA and vLLM. Two things
about it differ from the published docs — both verified on a live droplet:

- **The bundled vLLM is newer than documented.** The image carries
  `vllm/vllm-openai:v0.19.0` (docs say 0.9.0). Qwen3-VL needs ≥ 0.11.0, so the
  preinstalled image is already sufficient. **Do not pull `:latest`** — it is a
  ~10 GB download that buys nothing.
- **Port 8000 is already occupied** by a placeholder container (named `vllm`,
  command `tail -f /dev/null`) that holds the port without serving a model.
  Remove it before starting your own.

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker rm -f vllm            # the idle placeholder
sleep 2                      # see §2.3 — do not skip
```

### 2.2 Verify the GPU is actually reachable from a container

Host-level `nvidia-smi` is not sufficient evidence. Check inside a container:

```bash
docker run --rm --gpus all --entrypoint /bin/bash vllm/vllm-openai:v0.19.0 \
  -c "nvidia-smi -L; python3 -c 'import torch;print(torch.cuda.is_available())'"
```

Expect the GPU listed and `True`.

### 2.3 Gotcha: container starts but cannot see the GPU

Symptoms: `Failed to initialize NVML: Unknown Error`,
`torch.cuda.is_available() == False`, vLLM dying with
`AssertionError: DP adjusted local rank 0 is out of bounds`, or
`Triton is installed but 0 active driver(s) found`.

Cause: the container raced a previous container's teardown. It is **not** the
`--restart` policy (all of `-d`, `-d --restart unless-stopped`, `-d --ipc=host`
were tested clean) and **not** a host driver fault.

Fix: `docker rm -f <name>`, wait ~2 s, start again. A fresh `docker run`
recovers it. Never `docker exec` into a container showing this — it will stay
broken for that container's lifetime.

### 2.4 Host dependencies

```bash
pip install --user --break-system-packages pymupdf   # PDF -> PNG rendering
```

`python3-venv` is absent on the DO image and `pip install --user` alone is
blocked by PEP 668, hence `--break-system-packages`. `poppler-utils`
(`pdftotext`, `pdfinfo`) is optional and useful for inspecting text-layer
pages, but the pipeline does not need it.

---

## 3. Serving the model

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

Notes:

- The image's `ENTRYPOINT` is `vllm serve`, so the model is a **positional**
  argument — no `--model` flag.
- Bind to `127.0.0.1`, not `0.0.0.0`. The API is unauthenticated; anything that
  reaches the port can use the GPU.
- First start downloads ~61 GB and takes **~6 minutes** to become ready.
  Mount the HF cache so restarts are fast.
- `--ipc=host` already shares host `/dev/shm`; adding `--shm-size` is redundant.

Wait for readiness rather than guessing:

```bash
until curl -sf http://127.0.0.1:8000/v1/models >/dev/null; do sleep 10; done
echo ready
```

---

## 4. Running filings through the pipeline

`src/pipeline.py` is the production entry point. It accepts a URL, a local
path, or a JSONL manifest of either.

```bash
# fetch by URL
python3 src/pipeline.py --url https://webapps.rrc.state.tx.us/dpimages/img/...

# local file
python3 src/pipeline.py --file /data/filings/well123.pdf

# batch, mixed sources
cat > jobs.jsonl <<'EOF'
{"url": "https://webapps.rrc.state.tx.us/dpimages/img/aaa.pdf"}
{"file": "/data/filings/bbb.pdf"}
EOF
python3 src/pipeline.py --manifest jobs.jsonl --out out
```

Useful flags: `--only 1,2` restricts pages (testing only), `--force`
reprocesses a document that already has a `STATUS`, `--out` sets the output
root.

### Output layout

```
out/<doc_id>/
    source.pdf        fetched or copied input
    pages/            rendered PNGs (200 dpi)
    per_page.json     per-page model output incl. _secs and _usage
    raw/              unparsed model responses, for debugging
    extraction.json   merged record in the INSTRUCTIONS.md schema
    report.json       gates, review flags, timings, token counts
    STATUS            OK | REVIEW | FAIL
out/summary.json      one row per document in the run
```

`doc_id` is `sha256(pdf)[:16]`. This makes runs **idempotent** — re-running
skips completed documents, and the same filing fetched from two different URLs
collapses to one output directory. Use `--force` to override.

### Exit codes

| code | meaning | CI action |
|---|---|---|
| 0 | all documents `OK` | auto-load |
| 2 | at least one `REVIEW` | load md/inc/azm/tvd; queue offsets for a human |
| 1 | at least one `FAIL` | do not load; investigate |

---

## 5. Ingest safety

The fetcher enforces these before a byte reaches the model:

- **Magic-byte check.** The body must start with `%PDF`. A URL serving HTML
  (a login page, an error page, a redirect interstitial) is rejected rather
  than rendered into meaningless images and billed to the GPU.
- **200 MB cap**, checked against `Content-Length` and again on the body.
- **Permanent vs. transient retries.** 4xx (except 429) and wrong content type
  fail immediately. 5xx, 429 and network errors retry three times with
  exponential backoff. Do not "improve" this by retrying everything — hammering
  a state agency's website three times for a 404 is how you get blocked.

---

## 6. Interpreting review flags

| flag | meaning | what to do |
|---|---|---|
| `SPANNING_HEADER` | vendor layout nests N/S and E/W under one spanning header; offsets are shifted | Load md/inc/azm/tvd only. Discard offsets. See §7 |
| `NO_STATION_TABLE` | no page classified as a station table | Probably a plat or cover-only filing. Confirm it is the right document |
| `NO_API` | well identity missing | Cannot match to a well; reject per spec |
| `MD_GAP` | interval > 500 ft between stations | A page may have been dropped or mis-classified. Check `per_page.json` |
| `LATE_START` | shallowest station > 1000 ft MD | Tie-in/zero row may be missing. Cross-check against the cover letter's stated From MD |
| `NULL_REQUIRED` | null md/inc/azm | Model flagged illegible values. Human transcription needed |

`MD_GAP` and `LATE_START` are heuristics and do produce false positives —
a genuine survey may legitimately start deep. They downgrade to `REVIEW`, never
`FAIL`, precisely because they are advisory.

---

## 7. The defect you must respect

On vendor layouts using a **two-level spanning header** — PathFinder's
`TOTAL Rectangular Offsets` spanning N/S and E/W is the known case — the model
allots the spanning label one column slot and everything after `TVD` shifts one
position left:

| emitted field | column actually read |
|---|---|
| `ns_ft` | Vertical Section |
| `ew_ft` | N/S offset |
| *(absent)* | E/W offset — dropped |

MD, inclination, azimuth and TVD remain exactly correct (88/88 cells on the
audited page). COMPASS-style flat headers are unaffected (162/162 exact).

**Both validation gates pass on a document with this defect.** The TVD
integration residual was 0.03 usft — *better* than the document that was read
correctly — because TVD/inc/MD are all right. Do not treat a clean gate run as
evidence the offsets are good.

A real check requires independent geometry: terminus vs. the plat's stated
bottom-hole location, or closure distance/azimuth recomputed from the offsets
and compared against the printed closure columns. Neither is implemented yet.

---

## 8. Changing the prompt or adding a vendor format

The prompt is `prompts/INSTRUCTIONS.md`, used verbatim. Any change must be
re-scored, not eyeballed:

```bash
python3 src/extract.py --pages pages --prefix p --out results/rrcot
python3 src/score.py results/rrcot/per_page.json 9 data/ground_truth/rrcot_p09.csv
python3 src/score.py results/sur/per_page.json  2 data/ground_truth/sur_p02.csv
```

Expected today: RRCOT p9 `162/162 (100%)`, SUR p2 `88/132 (66.67%)` with all 44
offset cells wrong. **A prompt change that fixes SUR must not regress RRCOT.**

To onboard a new vendor format, hand-transcribe one dense table page into
`data/ground_truth/<name>.csv`. Two column shapes are supported:

- `md,inc,azm,tvd,ns_ft,ew_ft` — signed offsets (COMPASS)
- `md,inc,azm,tvd,ns_val,ns_lab,ew_val,ew_lab` — N/S/E/W labels (PathFinder)

Ground truth is currently one page per document — a spot check, not coverage.
Treat per-format confidence accordingly.

---

## 9. Secrets

`.env` holds credentials and is gitignored; `.env.example` documents the keys.
Before any push:

```bash
git status --porcelain | grep -E '\.env$' && echo "ABORT"
git diff --cached | grep -nE 'ghp_[A-Za-z0-9]{20,}|github_pat_'
```

When pushing with a PAT, do not embed it in the remote URL or a credential
helper — it persists in `.git/config`. Use a per-invocation header:

```bash
B64=$(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)
git -c http.extraheader="Authorization: Basic $B64" push origin main
```

`Authorization: Bearer` does **not** work for git over HTTPS to GitHub; Basic
with `x-access-token` does.

---

## 10. Performance envelope

Measured on 1×H200, 200 dpi renders, sequential requests
(full numbers in [`docs/METRICS.md`](docs/METRICS.md)):

| | value |
|---|---|
| throughput | ~198 tok/s output on table pages |
| per station | ~440 ms, ~87 output tokens |
| per page | ~4,770 prompt tokens (near-constant), ~12 s for a dense table |
| non-table pages | ~1 s — the model exits early rather than inventing rows |
| model load | ~360 s cold, fast with a warm HF cache |

Two planning notes: throughput is flat regardless of layout, so **scanned pages
cost the same as vector-text pages** — output volume drives runtime, not
difficulty. And `--max-num-seqs 4` is set but unexercised, since the pipeline
runs pages sequentially; concurrent batching is untested headroom, and is the
obvious first optimization for large backlogs.

---

## 11. Do not

- Do not raise `--limit-mm-per-prompt` and batch many pages into one request
  without re-scoring. One request per page keeps context small, isolates
  failures to a page, and is what every number in this repo was measured with.
- Do not bind the API to `0.0.0.0`.
- Do not commit source PDFs or rendered pages; both are gitignored.
- Do not trust `temperature` above 0 for extraction.
- Do not delete `raw/` — it is the only record of what the model actually
  emitted when a parse fails.
