#!/usr/bin/env python3
"""Cell-level diff of one extracted page against a hand-transcribed CSV.

Two ground-truth shapes are supported:
  signed  : md,inc,azm,tvd,ns_ft,ew_ft           (COMPASS -- signed offsets)
  labelled: md,inc,azm,tvd,ns_val,ns_lab,ew_val,ew_lab  (PathFinder -- N/S/E/W labels)

usage:
  python3 src/score.py results/rrcot/per_page.json 9 data/ground_truth/rrcot_p09.csv
"""
import csv, json, pathlib, sys


def main():
    if len(sys.argv) != 4 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        return 0
    per_page, page, gtfile = pathlib.Path(sys.argv[1]), int(sys.argv[2]), pathlib.Path(sys.argv[3])
    res = json.loads(per_page.read_text())
    got = next(r for r in res if r.get("page") == page)["stations"]
    gt = list(csv.DictReader(gtfile.open()))
    labelled = "ns_lab" in gt[0]

    print(f"page {page}: truth rows={len(gt)}  model rows={len(got)}")
    if len(gt) != len(got):
        print("  !! ROW COUNT MISMATCH")

    bad = cells = 0
    for i, (g, m) in enumerate(zip(gt, got), 1):
        for c in ("md", "inc", "azm", "tvd"):
            cells += 1
            mv = m.get(c)
            if mv is None or abs(float(mv) - float(g[c])) > 1e-9:
                bad += 1
                print(f"  row{i} {c}: truth={g[c]} model={mv}")
        pairs = ([("ns_val", "ns_lab", "ns_ft"), ("ew_val", "ew_lab", "ew_ft")] if labelled
                 else [("ns_ft", None, "ns_ft"), ("ew_ft", None, "ew_ft")])
        for val, lab, key in pairs:
            cells += 1
            mv = m.get(key)
            if mv is None:
                bad += 1
                print(f"  row{i} {key}: truth={g[val]} model=None")
                continue
            truth = abs(float(g[val])) if labelled else float(g[val])
            cmpv = abs(float(mv)) if labelled else float(mv)
            if abs(cmpv - truth) > 1e-9:
                bad += 1
                suffix = g[lab] if lab else ""
                print(f"  row{i} {key}: truth={g[val]}{suffix} model={mv}")

    print(f"\ncells={cells} mismatches={bad} accuracy={100*(cells-bad)/cells:.2f}%")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
