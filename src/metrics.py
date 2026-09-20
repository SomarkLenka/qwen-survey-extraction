#!/usr/bin/env python3
"""Performance metrics from recorded per-page timings and token usage.

Every extract.py request records wall-clock (`_secs`) and the server's usage
block (`_usage`), so these are measured, not estimated.

NOTE: requests are non-streaming, so time-to-first-token was not captured.
`output_tok_per_s` is therefore end-to-end (prefill + image encode + decode),
which understates pure decode throughput.

usage: python3 src/metrics.py                    # writes results/metrics.json
       python3 src/metrics.py --print            # stdout only
"""
import argparse, json, pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
DOCS = [("RRCOT_COVER_SHEET.pdf", "results/rrcot"),
        ("SUR.pdf", "results/sur")]


def doc_metrics(name, d):
    res = json.loads((REPO / d / "per_page.json").read_text())
    tbl = [r for r in res if r.get("page_type") == "station_table"]
    pin = sum(r.get("_usage", {}).get("prompt_tokens", 0) for r in res)
    pout = sum(r.get("_usage", {}).get("completion_tokens", 0) for r in res)
    secs = sum(r.get("_secs", 0) for r in res)
    tsec = sum(r["_secs"] for r in tbl)
    tout = sum(r["_usage"]["completion_tokens"] for r in tbl)
    st = sum(len(r["stations"]) for r in tbl)
    return {
        "document": name,
        "pages": len(res),
        "station_table_pages": len(tbl),
        "stations_extracted": st,
        "wall_clock_s": round(secs, 1),
        "wall_clock_s_per_page": round(secs / len(res), 2),
        "prompt_tokens": pin,
        "prompt_tokens_per_page": round(pin / len(res)),
        "completion_tokens": pout,
        "completion_tokens_per_page": round(pout / len(res)),
        "total_tokens": pin + pout,
        "output_tok_per_s_end_to_end": round(pout / secs, 1),
        "table_pages_only": {
            "wall_clock_s": round(tsec, 1),
            "completion_tokens": tout,
            "output_tok_per_s": round(tout / tsec, 1),
            "ms_per_station": round(tsec / st * 1000),
            "output_tokens_per_station": round(tout / st),
        },
        "per_page": [
            {"page": r.get("page"), "page_type": r.get("page_type"),
             "stations": len(r.get("stations", [])),
             "secs": r.get("_secs"),
             "prompt_tokens": r.get("_usage", {}).get("prompt_tokens"),
             "completion_tokens": r.get("_usage", {}).get("completion_tokens")}
            for r in res
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", dest="show", action="store_true")
    a = ap.parse_args()
    out = {
        "environment": {
            "model": "Qwen/Qwen3-VL-30B-A3B-Instruct",
            "server": "vLLM v0.19.0 (vllm/vllm-openai:v0.19.0)",
            "gpu": "1x NVIDIA H200 141GB",
            "dtype": "bfloat16",
            "max_model_len": 65536,
            "max_num_seqs": 4,
            "gpu_memory_utilization": 0.90,
            "render_dpi": 200,
            "temperature": 0,
            "requests": "non-streaming, one per page, sequential",
            "model_load_time_s": 360,
            "ttft_measured": False,
        },
        "documents": [doc_metrics(n, d) for n, d in DOCS],
    }
    dest = REPO / "results" / "metrics.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"wrote {dest}")
    for m in out["documents"]:
        print(f"\n=== {m['document']} ===")
        for k in ("pages", "stations_extracted", "wall_clock_s", "prompt_tokens",
                  "completion_tokens", "total_tokens", "output_tok_per_s_end_to_end"):
            print(f"  {k:32s}: {m[k]:,}" if isinstance(m[k], int) else f"  {k:32s}: {m[k]}")
        t = m["table_pages_only"]
        print(f"  {'table pages: tok/s':32s}: {t['output_tok_per_s']}")
        print(f"  {'table pages: ms/station':32s}: {t['ms_per_station']}")


if __name__ == "__main__":
    main()
