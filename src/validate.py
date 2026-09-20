#!/usr/bin/env python3
"""Validation gates from INSTRUCTIONS.md: MD monotonicity + TVD integration.

Integrates TVD from inclination (balanced tangential) and compares to the
printed TVD. Residuals stay near zero when the survey is read correctly;
the small non-zero floor is balanced-tangential vs. minimum-curvature.

CAVEAT: these gates only exercise md/inc/tvd. A column-shift confined to the
N/S and E/W offsets passes both cleanly -- see docs/FINDINGS.md.

usage: python3 src/validate.py results/rrcot/extraction.json
"""
import json, math, pathlib, sys


def gates(doc):
    st = doc["stations"]
    ok = True
    print(f"well      : {doc.get('well_name')}  (API {doc.get('api')})")
    print(f"stations  : {len(st)}   MD {st[0]['md']:,.2f} -> {st[-1]['md']:,.2f}")

    viol = [(st[i - 1], st[i]) for i in range(1, len(st)) if st[i]["md"] <= st[i - 1]["md"]]
    print(f"\n[gate] MD strictly increasing : {'PASS' if not viol else f'FAIL ({len(viol)})'}")
    for a, b in viol[:10]:
        print(f"    {a['md']:,.2f} (p{a.get('_page')}) -> {b['md']:,.2f} (p{b.get('_page')})")
    ok &= not viol

    res = []
    for i in range(1, len(st)):
        a, b = st[i - 1], st[i]
        if None in (a.get("tvd"), b.get("tvd"), a.get("inc"), b.get("inc")):
            continue
        pred = a["tvd"] + (b["md"] - a["md"]) * (
            math.cos(math.radians(a["inc"])) + math.cos(math.radians(b["inc"]))) / 2
        res.append((abs(b["tvd"] - pred), b["tvd"] - pred, a["md"], b["md"], b.get("_page")))
    res.sort(reverse=True)
    if res:
        mx, mean = res[0][0], sum(r[0] for r in res) / len(res)
        print(f"\n[gate] TVD integration        : checked={len(res)} "
              f"max={mx:.2f} usft  mean={mean:.3f} usft")
        for r in res[:5]:
            print(f"    MD {r[2]:,.2f} -> {r[3]:,.2f} (p{r[4]}): {r[1]:+.3f}")

    nulls = [(s.get("_page"), s.get("md"), k) for s in st
             for k in ("md", "inc", "azm", "tvd") if s.get(k) is None]
    print(f"\n[info] null required values   : {len(nulls)}")
    flagged = [s for s in st if s.get("offset_labels")]
    print(f"[info] rows with offset labels: {len(flagged)}")
    return ok


if __name__ == "__main__":
    p = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "results/rrcot/extraction.json")
    sys.exit(0 if gates(json.loads(p.read_text())) else 1)
