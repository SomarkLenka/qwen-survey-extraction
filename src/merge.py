#!/usr/bin/env python3
"""Merge per-page output into one record in the INSTRUCTIONS.md schema.

usage: python3 src/merge.py --in results/rrcot --source RRCOT_COVER_SHEET.pdf
"""
import argparse, json, pathlib


def merge(res, source, warning=None):
    ident = {}
    for r in res:
        for k in ("api", "well_name", "operator", "north_ref", "tool",
                  "datum_zone", "kb_elevation", "report_date"):
            if not ident.get(k) and r.get(k):
                ident[k] = r[k]

    stations, pages = [], []
    for r in res:
        if r.get("page_type") != "station_table":
            continue
        pages.append(r["page"])
        for s in r["stations"]:
            row = {k: s.get(k) for k in ("md", "inc", "azm", "tvd", "ns_ft", "ew_ft")}
            if s.get("flags"):
                row["offset_labels"] = s["flags"]
            row["_page"] = r["page"]
            stations.append(row)

    doc = {k: ident.get(k) for k in
           ("api", "well_name", "operator", "north_ref", "tool",
            "datum_zone", "kb_elevation", "report_date")}
    doc["source_url"] = source
    doc["table_pages"] = sorted(set(pages))
    doc["md_range"] = [stations[0]["md"], stations[-1]["md"]] if stations else [None, None]
    doc["station_count"] = len(stations)
    if warning:
        doc["_WARNING"] = warning
    doc["stations"] = stations
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--warning")
    a = ap.parse_args()
    d = pathlib.Path(a.indir)
    res = json.loads((d / "per_page.json").read_text())
    doc = merge(res, a.source, a.warning)
    (d / "extraction.json").write_text(json.dumps(doc, indent=2))
    if doc["station_count"]:
        span = f"MD {doc['md_range'][0]:,.2f} -> {doc['md_range'][1]:,.2f}"
    else:
        span = "no stations found"
    print(f"{d/'extraction.json'}: {doc['station_count']} stations, {span}, "
          f"pages {doc['table_pages']}")


if __name__ == "__main__":
    main()
