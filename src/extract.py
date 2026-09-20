#!/usr/bin/env python3
"""Run Qwen3-VL over rendered PDF pages, one request per page.

The prompt is prompts/INSTRUCTIONS.md (the extraction spec) plus a per-page
envelope that pins the output schema.

usage:
  python3 src/extract.py --pages pages     --prefix p --out results/rrcot
  python3 src/extract.py --pages pages_sur --prefix s --out results/sur --only 2,3
"""
import argparse, base64, json, pathlib, re, sys, time, urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_API = "http://127.0.0.1:8000/v1/chat/completions"
DEFAULT_MODEL = "Qwen/Qwen3-VL-30B-A3B-Instruct"

ENVELOPE = """You are extracting from ONE page of a multi-page RRC directional survey filing.

{spec}

This request contains page {pg} of {total}. Return JSON only, no prose, no code fences:
{{
  "page": {pg},
  "page_type": "header" | "station_table" | "plat" | "certification" | "other",
  "api": string|null, "well_name": string|null, "operator": string|null,
  "north_ref": string|null, "tool": string|null,
  "kb_elevation": string|null, "datum_zone": string|null,
  "report_date": string|null,
  "md_range": [number|null, number|null],
  "columns": [string],
  "stations": [
    {{"md": num|null, "inc": num|null, "azm": num|null, "tvd": num|null,
      "ns_ft": num|null, "ew_ft": num|null, "flags": [string]}}
  ]
}}
Transcribe EVERY station row on this page in printed order. Preserve minus signs
exactly. Do not convert units. If a digit is illegible use null and add a flag.
If the page has no station table, return "stations": []."""


def load_spec(path: pathlib.Path) -> str:
    return path.read_text().strip()


def build_prompt(spec, pg, total):
    return ENVELOPE.format(spec=spec, pg=pg, total=total)


def call(api, model, img: pathlib.Path, prompt, timeout=900, retries=2):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(img.read_bytes()).decode()}},
        ]}],
        "temperature": 0,
        "max_tokens": 16384,
    }
    data = json.dumps(body).encode()
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(api, data=data,
                                         headers={"Content-Type": "application/json"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.load(r)
            return (resp["choices"][0]["message"]["content"],
                    time.time() - t0, resp.get("usage", {}))
        except Exception as e:                       # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(5)
    raise last


def parse(txt):
    """Model is asked for bare JSON; tolerate code fences and leading prose."""
    t = re.sub(r"\s*```$", "", re.sub(r"^```(?:json)?\s*", "", txt.strip()))
    try:
        return json.loads(t), None
    except json.JSONDecodeError as e:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0)), "recovered-by-brace-scan"
            except json.JSONDecodeError as e2:
                return None, f"unparseable: {e2}"
        return None, f"unparseable: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True, help="directory of rendered PNGs")
    ap.add_argument("--prefix", default="p", help="filename prefix, e.g. p or s")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--only", help="comma-separated page numbers")
    ap.add_argument("--spec", default=str(REPO / "prompts" / "INSTRUCTIONS.md"))
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    a = ap.parse_args()

    spec = load_spec(pathlib.Path(a.spec))
    pages = sorted(pathlib.Path(a.pages).glob(f"{a.prefix}*.png"))
    if not pages:
        sys.exit(f"no {a.prefix}*.png under {a.pages}")
    total = len(pages)
    if a.only:
        want = {int(x) for x in a.only.split(",")}
        pages = [p for p in pages if int(p.stem[len(a.prefix):]) in want]

    outdir = pathlib.Path(a.out)
    (outdir / "raw").mkdir(parents=True, exist_ok=True)

    out = []
    for p in pages:
        pg = int(p.stem[len(a.prefix):])
        try:
            txt, dt, usage = call(a.api, a.model, p, build_prompt(spec, pg, total))
        except Exception as e:                       # noqa: BLE001
            print(f"{p.stem} REQUEST FAILED: {e}", flush=True)
            out.append({"page": pg, "_error": str(e)})
            continue
        obj, err = parse(txt)
        (outdir / "raw" / f"{p.stem}.txt").write_text(txt)
        print(f"{p.stem} {dt:6.1f}s in={usage.get('prompt_tokens','?')} "
              f"out={usage.get('completion_tokens','?')} "
              f"stations={len(obj.get('stations', [])) if obj else 0} "
              f"type={obj.get('page_type') if obj else 'PARSE_FAIL'} {err or ''}", flush=True)
        rec = obj or {"page": pg, "_parse_error": err, "_raw": txt}
        rec["_secs"], rec["_usage"] = round(dt, 1), usage
        out.append(rec)

    dest = outdir / "per_page.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {dest} ({len(out)} pages)")


if __name__ == "__main__":
    main()
