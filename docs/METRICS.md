# Measured performance

Recorded by `src/extract.py` on every request: wall-clock per page and the
server's `usage` block. Regenerate with `python3 src/metrics.py` and
`python3 src/report_metrics.py`.

## Environment

| setting | value |
|---|---|
| `model` | Qwen/Qwen3-VL-30B-A3B-Instruct |
| `server` | vLLM v0.19.0 (vllm/vllm-openai:v0.19.0) |
| `gpu` | 1x NVIDIA H200 141GB |
| `dtype` | bfloat16 |
| `max_model_len` | 65536 |
| `max_num_seqs` | 4 |
| `gpu_memory_utilization` | 0.9 |
| `render_dpi` | 200 |
| `temperature` | 0 |
| `requests` | non-streaming, one per page, sequential |
| `model_load_time_s` | 360 |
| `ttft_measured` | False |

**TTFT was not measured** — requests are non-streaming, so there is no
first-token timestamp. `output_tok_per_s` is end-to-end (prefill + image
encode + decode) and understates pure decode throughput.

## RRCOT_COVER_SHEET.pdf

| metric | value |
|---|---|
| pages | 14 (8 station tables) |
| stations extracted | 185 |
| wall clock | 87.4 s (6.24 s/page avg) |
| prompt tokens | 66,804 (4,772/page) |
| completion tokens | 16,996 (1,214/page) |
| total tokens | 83,800 |
| output rate (end-to-end) | 194.5 tok/s |
| table pages only | 81.0 s, 198.2 tok/s |
| cost per station | 438 ms, 87 output tokens |

### Recorded per page

| page | type | stations | secs | in_tok | out_tok | tok/s |
|---:|---|---:|---:|---:|---:|---:|
| 1 | header | 0 | 0.9 | 4,771 | 176 | 195.6 |
| 2 | header | 0 | 1.1 | 4,771 | 134 | 121.8 |
| 3 | plat | 1 | 1.6 | 4,771 | 234 | 146.2 |
| 4 | header | 0 | 1.0 | 4,771 | 117 | 117.0 |
| 5 | other | 0 | 0.7 | 4,771 | 146 | 208.6 |
| 6 | station_table | 19 | 8.1 | 4,771 | 1,588 | 196.0 |
| 7 | station_table | 26 | 10.6 | 4,771 | 2,106 | 198.7 |
| 8 | station_table | 25 | 10.7 | 4,771 | 2,132 | 199.3 |
| 9 | station_table | 27 | 11.7 | 4,771 | 2,329 | 199.1 |
| 10 | station_table | 27 | 11.9 | 4,773 | 2,378 | 199.8 |
| 11 | station_table | 27 | 11.9 | 4,773 | 2,372 | 199.3 |
| 12 | station_table | 27 | 11.9 | 4,773 | 2,370 | 199.2 |
| 13 | station_table | 7 | 4.2 | 4,773 | 780 | 185.7 |
| 14 | header | 0 | 1.1 | 4,773 | 134 | 121.8 |
| **total** | | **185** | **87.4** | **66,804** | **16,996** | **194.5** |

## SUR.pdf

| metric | value |
|---|---|
| pages | 9 (7 station tables) |
| stations extracted | 178 |
| wall clock | 81.0 s (9.0 s/page avg) |
| prompt tokens | 43,068 (4,785/page) |
| completion tokens | 15,865 (1,763/page) |
| total tokens | 58,933 |
| output rate (end-to-end) | 195.9 tok/s |
| table pages only | 78.4 s, 198.2 tok/s |
| cost per station | 440 ms, 87 output tokens |

### Recorded per page

| page | type | stations | secs | in_tok | out_tok | tok/s |
|---:|---|---:|---:|---:|---:|---:|
| 1 | header | 0 | 1.4 | 4,770 | 176 | 125.7 |
| 2 | station_table | 22 | 9.4 | 4,770 | 1,843 | 196.1 |
| 3 | station_table | 27 | 11.7 | 4,839 | 2,315 | 197.9 |
| 4 | station_table | 27 | 11.4 | 4,770 | 2,270 | 199.1 |
| 5 | station_table | 27 | 11.6 | 4,770 | 2,301 | 198.4 |
| 6 | station_table | 27 | 11.8 | 4,839 | 2,336 | 198.0 |
| 7 | station_table | 27 | 12.0 | 4,770 | 2,387 | 198.9 |
| 8 | station_table | 21 | 10.5 | 4,770 | 2,090 | 199.0 |
| 9 | plat | 0 | 1.2 | 4,770 | 147 | 122.5 |
| **total** | | **178** | **81.0** | **43,068** | **15,865** | **195.9** |

## Notes

- Prompt tokens are near-constant (~4,771/page): the spec prompt is fixed and
  every render is the same pixel count, so image tokens do not vary.
- Non-table pages cost ~1 s; the model exits early rather than inventing rows.
- Throughput is flat at ~198 tok/s on table pages regardless of layout, so the
  scanned document is no slower than the vector-text one. Output volume, not
  page difficulty, drives runtime.
- Sequential, one request per page. `--max-num-seqs 4` was set but never
  exercised; batching pages concurrently is untested headroom.
