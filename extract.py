#!/usr/bin/env python3
"""Run Qwen3-VL extraction over rendered PDF pages using INSTRUCTIONS.md as the prompt."""
import base64, json, sys, time, urllib.request, pathlib, re

API   = "http://127.0.0.1:8000/v1/chat/completions"
MODEL = "Qwen/Qwen3-VL-30B-A3B-Instruct"
ROOT  = pathlib.Path("/home/claudeuser")

# INSTRUCTIONS.md is the prompt. Strip the trailing internal note after the '---'
# separator: it is addressed to a colleague, not part of the extraction spec.
spec = (ROOT / "INSTRUCTIONS.md").read_text()
spec = spec.split("\n---\n")[0].strip()

PER_PAGE = """You are extracting from ONE page of a multi-page RRC directional survey filing.

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

def b64(p):
    return base64.b64encode(p.read_bytes()).decode()

def ask(img_path, pg, total, retries=2):
    prompt = PER_PAGE.format(spec=spec, pg=pg, total=total)
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + b64(img_path)}},
        ]}],
        "temperature": 0,
        "max_tokens": 16384,
    }
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(API, data=data,
                                         headers={"Content-Type": "application/json"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=900) as r:
                resp = json.load(r)
            dt = time.time() - t0
            txt = resp["choices"][0]["message"]["content"]
            usage = resp.get("usage", {})
            return txt, dt, usage
        except Exception as e:
            if attempt == retries:
                raise
            time.sleep(5)

def parse(txt):
    t = txt.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t), None
    except Exception as e:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0)), "recovered-by-brace-scan"
            except Exception as e2:
                return None, f"unparseable: {e2}"
        return None, f"unparseable: {e}"

if __name__ == "__main__":
    pages = sorted((ROOT / "pages").glob("p*.png"))
    if len(sys.argv) > 1:
        want = {int(x) for x in sys.argv[1].split(",")}
        pages = [p for p in pages if int(p.stem[1:]) in want]
    total = 14
    out = []
    for p in pages:
        pg = int(p.stem[1:])
        try:
            txt, dt, usage = ask(p, pg, total)
        except Exception as e:
            print(f"p{pg:02d} REQUEST FAILED: {e}", flush=True)
            out.append({"page": pg, "_error": str(e)})
            continue
        obj, err = parse(txt)
        n = len(obj.get("stations", [])) if obj else 0
        print(f"p{pg:02d} {dt:6.1f}s in={usage.get('prompt_tokens','?')} "
              f"out={usage.get('completion_tokens','?')} stations={n} "
              f"type={obj.get('page_type') if obj else 'PARSE_FAIL'} {err or ''}", flush=True)
        rec = obj if obj else {"page": pg, "_parse_error": err, "_raw": txt}
        rec["_secs"] = round(dt, 1)
        rec["_usage"] = usage
        out.append(rec)
        (ROOT / "qwen-test" / f"raw_p{pg:02d}.txt").write_text(txt)
    (ROOT / "qwen-test" / "results.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote qwen-test/results.json ({len(out)} pages)")
