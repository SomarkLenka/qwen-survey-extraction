#!/usr/bin/env python3
"""Render results/metrics.json into docs/METRICS.md so the doc stays in sync."""
import json, pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
m = json.loads((REPO / "results" / "metrics.json").read_text())
env = m["environment"]

L = ["# Measured performance", "",
     "Recorded by `src/extract.py` on every request: wall-clock per page and the",
     "server's `usage` block. Regenerate with `python3 src/metrics.py` and",
     "`python3 src/report_metrics.py`.", "",
     "## Environment", ""]
L += [f"| setting | value |", "|---|---|"]
for k, v in env.items():
    L.append(f"| `{k}` | {v} |")
L += ["", "**TTFT was not measured** — requests are non-streaming, so there is no",
      "first-token timestamp. `output_tok_per_s` is end-to-end (prefill + image",
      "encode + decode) and understates pure decode throughput.", ""]

for d in m["documents"]:
    t = d["table_pages_only"]
    L += [f"## {d['document']}", "",
          f"| metric | value |", "|---|---|",
          f"| pages | {d['pages']} ({d['station_table_pages']} station tables) |",
          f"| stations extracted | {d['stations_extracted']} |",
          f"| wall clock | {d['wall_clock_s']} s ({d['wall_clock_s_per_page']} s/page avg) |",
          f"| prompt tokens | {d['prompt_tokens']:,} ({d['prompt_tokens_per_page']:,}/page) |",
          f"| completion tokens | {d['completion_tokens']:,} ({d['completion_tokens_per_page']:,}/page) |",
          f"| total tokens | {d['total_tokens']:,} |",
          f"| output rate (end-to-end) | {d['output_tok_per_s_end_to_end']} tok/s |",
          f"| table pages only | {t['wall_clock_s']} s, {t['output_tok_per_s']} tok/s |",
          f"| cost per station | {t['ms_per_station']} ms, {t['output_tokens_per_station']} output tokens |",
          "", "### Recorded per page", "",
          "| page | type | stations | secs | in_tok | out_tok | tok/s |",
          "|---:|---|---:|---:|---:|---:|---:|"]
    for r in d["per_page"]:
        rate = r["completion_tokens"] / r["secs"] if r["secs"] else 0
        L.append(f"| {r['page']} | {r['page_type']} | {r['stations']} | {r['secs']:.1f} | "
                 f"{r['prompt_tokens']:,} | {r['completion_tokens']:,} | {rate:.1f} |")
    L.append(f"| **total** | | **{d['stations_extracted']}** | **{d['wall_clock_s']:.1f}** | "
             f"**{d['prompt_tokens']:,}** | **{d['completion_tokens']:,}** | "
             f"**{d['output_tok_per_s_end_to_end']}** |")
    L.append("")

L += ["## Notes", "",
      "- Prompt tokens are near-constant (~4,771/page): the spec prompt is fixed and",
      "  every render is the same pixel count, so image tokens do not vary.",
      "- Non-table pages cost ~1 s; the model exits early rather than inventing rows.",
      "- Throughput is flat at ~198 tok/s on table pages regardless of layout, so the",
      "  scanned document is no slower than the vector-text one. Output volume, not",
      "  page difficulty, drives runtime.",
      "- Sequential, one request per page. `--max-num-seqs 4` was set but never",
      "  exercised; batching pages concurrently is untested headroom.",
      ""]
(REPO / "docs" / "METRICS.md").write_text("\n".join(L))
print(f"wrote docs/METRICS.md ({len(L)} lines)")
