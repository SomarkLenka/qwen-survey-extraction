#!/usr/bin/env python3
"""Production pipeline: ingest a filing by URL or path, extract, validate.

  python3 src/pipeline.py --file /data/filings/well123.pdf
  python3 src/pipeline.py --url  https://webapps.rrc.state.tx.us/dpimages/img/...
  python3 src/pipeline.py --manifest jobs.jsonl        # {"url": ...} or {"file": ...} per line

Per document, writes out/<doc_id>/:
    source.pdf        the fetched or copied input
    pages/            rendered PNGs
    per_page.json     per-page model output incl. _secs and _usage
    raw/              unparsed responses
    extraction.json   merged record in the INSTRUCTIONS.md schema
    report.json       gate results, review flags, timings
    STATUS            OK | REVIEW | FAIL

doc_id defaults to sha256(pdf)[:16], so re-running is idempotent and the same
filing fetched from two URLs resolves to one output directory.

Exit codes: 0 all OK, 2 at least one REVIEW, 1 at least one FAIL.
"""
import argparse, hashlib, json, pathlib, shutil, subprocess, sys, time, urllib.error, urllib.request

REPO = pathlib.Path(__file__).resolve().parent
ROOT = REPO.parent
MAX_BYTES = 200 * 1024 * 1024
UA = "rrc-survey-extractor/1.0"


class PermanentFetchError(Exception):
    """Fetch failure that will not succeed on retry (404, wrong content type)."""

# Vendor layouts that nest N/S and E/W under one spanning header. The model
# collapses these into a single column slot and shifts the offsets one place
# left (see docs/FINDINGS.md), so offsets from these pages are not loadable.
SPANNING_HEADER_MARKERS = ("rectangular offset", "total rectangular", "offsets (ft)")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch(url, dest, retries=3):
    """Download to dest. Verifies it is really a PDF before returning."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                ctype = (r.headers.get("Content-Type") or "").lower()
                clen = int(r.headers.get("Content-Length") or 0)
                if clen > MAX_BYTES:
                    raise ValueError(f"refusing {clen} bytes (cap {MAX_BYTES})")
                data = r.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError(f"body exceeded cap {MAX_BYTES}")
            if not data.startswith(b"%PDF"):
                # Permanent: the URL does not serve a PDF. Do not retry.
                raise PermanentFetchError(
                    f"not a PDF (content-type {ctype!r}, first bytes {data[:8]!r})")
            dest.write_bytes(data)
            return len(data)
        except PermanentFetchError:
            raise
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                raise PermanentFetchError(f"HTTP {e.code} {e.reason}") from e
            last = e
            log(f"  fetch attempt {attempt}/{retries} failed: {e}")
        except Exception as e:                        # noqa: BLE001
            last = e
            log(f"  fetch attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"fetch failed after {retries} attempts: {last}")


def sha256(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed rc={r.returncode}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def review_flags(per_page, doc):
    """Cheap structural checks that catch the known failure modes."""
    flags = []
    tables = [p for p in per_page if p.get("page_type") == "station_table"]
    if not tables:
        flags.append("NO_STATION_TABLE: no page classified as a station table")

    for p in tables:
        cols = " ".join(p.get("columns") or []).lower()
        if any(m in cols for m in SPANNING_HEADER_MARKERS):
            flags.append(
                f"SPANNING_HEADER page {p['page']}: offsets are unreliable on this "
                f"vendor layout; load md/inc/azm/tvd only")
            break

    st = doc.get("stations", [])
    if st:
        gaps = [(a["md"], b["md"]) for a, b in zip(st, st[1:]) if b["md"] - a["md"] > 500]
        if gaps:
            flags.append(f"MD_GAP: {len(gaps)} interval(s) >500 ft, largest "
                         f"{max(b-a for a, b in gaps):,.0f} ft — possible dropped page")
        if doc.get("md_range", [None])[0] and doc["md_range"][0] > 1000:
            flags.append(f"LATE_START: shallowest station is {doc['md_range'][0]:,.0f} ft MD; "
                         f"tie-in/zero row may be missing")
    if not doc.get("api"):
        flags.append("NO_API: well identity missing — cannot match to a well")

    nulls = sum(1 for s in st for k in ("md", "inc", "azm") if s.get(k) is None)
    if nulls:
        flags.append(f"NULL_REQUIRED: {nulls} null md/inc/azm value(s)")
    return flags


def process(src_desc, pdf_path, outroot, force, only=None):
    digest = sha256(pdf_path)
    doc_id = digest[:16]
    out = outroot / doc_id
    status_file = out / "STATUS"
    if status_file.exists() and not force:
        log(f"  {doc_id}: already processed ({status_file.read_text().strip()}), skipping")
        return json.loads((out / "report.json").read_text())

    out.mkdir(parents=True, exist_ok=True)
    if pdf_path.resolve() != (out / "source.pdf").resolve():
        shutil.copy2(pdf_path, out / "source.pdf")

    t0 = time.time()
    log(f"  {doc_id}: rendering")
    run([sys.executable, "src/render.py", str(out / "source.pdf"), str(out / "pages"), "p", "200"])

    log(f"  {doc_id}: extracting")
    cmd = [sys.executable, "src/extract.py", "--pages", str(out / "pages"),
           "--prefix", "p", "--out", str(out)]
    if only:
        cmd += ["--only", only]
    run(cmd)

    log(f"  {doc_id}: merging")
    run([sys.executable, "src/merge.py", "--in", str(out), "--source", src_desc])

    per_page = json.loads((out / "per_page.json").read_text())
    doc = json.loads((out / "extraction.json").read_text())

    gates, gate_ok = {}, True
    st = doc.get("stations", [])
    mono = [i for i in range(1, len(st)) if st[i]["md"] <= st[i - 1]["md"]]
    gates["md_strictly_increasing"] = {"pass": not mono, "violations": len(mono)}
    gate_ok &= not mono
    if not st:
        gates["has_stations"] = {"pass": False}
        gate_ok = False

    flags = review_flags(per_page, doc)
    status = "FAIL" if not gate_ok else ("REVIEW" if flags else "OK")

    report = {
        "doc_id": doc_id,
        "sha256": digest,
        "source": src_desc,
        "status": status,
        "gates": gates,
        "review_flags": flags,
        "api": doc.get("api"),
        "well_name": doc.get("well_name"),
        "stations": len(st),
        "md_range": doc.get("md_range"),
        "pages": len(per_page),
        "elapsed_s": round(time.time() - t0, 1),
        "tokens": {
            "prompt": sum(p.get("_usage", {}).get("prompt_tokens", 0) for p in per_page),
            "completion": sum(p.get("_usage", {}).get("completion_tokens", 0) for p in per_page),
        },
    }
    (out / "report.json").write_text(json.dumps(report, indent=2))
    status_file.write_text(status + "\n")
    log(f"  {doc_id}: {status}  {report['stations']} stations  {report['elapsed_s']}s")
    for f in flags:
        log(f"      flag: {f}")
    return report


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--url")
    g.add_argument("--file")
    g.add_argument("--manifest", help="JSONL, one {\"url\":...} or {\"file\":...} per line")
    ap.add_argument("--out", default="out")
    ap.add_argument("--only", help="page subset, e.g. 1,2 (testing)")
    ap.add_argument("--force", action="store_true", help="reprocess even if STATUS exists")
    a = ap.parse_args()

    jobs = []
    if a.manifest:
        for line in pathlib.Path(a.manifest).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                jobs.append(json.loads(line))
    elif a.url:
        jobs = [{"url": a.url}]
    else:
        jobs = [{"file": a.file}]

    outroot = pathlib.Path(a.out)
    outroot.mkdir(parents=True, exist_ok=True)
    staging = outroot / "_staging"
    staging.mkdir(exist_ok=True)

    reports = []
    for i, job in enumerate(jobs, 1):
        src = job.get("url") or job.get("file")
        log(f"[{i}/{len(jobs)}] {src}")
        try:
            if "url" in job:
                tmp = staging / f"dl_{i}.pdf"
                n = fetch(job["url"], tmp)
                log(f"  fetched {n:,} bytes")
                pdf = tmp
            else:
                pdf = pathlib.Path(job["file"])
                if not pdf.is_file():
                    raise FileNotFoundError(pdf)
                if pdf.read_bytes()[:4] != b"%PDF":
                    raise ValueError(f"{pdf} is not a PDF")
            reports.append(process(src, pdf, outroot, a.force, a.only))
        except Exception as e:                        # noqa: BLE001
            log(f"  ERROR: {e}")
            reports.append({"source": src, "status": "FAIL", "error": str(e)})

    shutil.rmtree(staging, ignore_errors=True)
    summary = outroot / "summary.json"
    summary.write_text(json.dumps(reports, indent=2))

    counts = {}
    for r in reports:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    log(f"done: {counts}  -> {summary}")
    if any(r["status"] == "FAIL" for r in reports):
        return 1
    return 2 if any(r["status"] == "REVIEW" for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
