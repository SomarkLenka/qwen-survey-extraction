#!/usr/bin/env python3
"""Render a PDF's pages to PNG for the extraction harness.

usage: python3 render.py <pdf> <outdir> [prefix] [dpi]
  python3 render.py ../RRCOT_COVER_SHEET.pdf pages     p 200
  python3 render.py ../SUR.pdf               pages_sur s 200
"""
import sys, os, pathlib
import pymupdf

def main():
    if len(sys.argv) < 3:
        print(__doc__); return 1
    pdf, outdir = sys.argv[1], sys.argv[2]
    prefix = sys.argv[3] if len(sys.argv) > 3 else "p"
    dpi = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    os.makedirs(outdir, exist_ok=True)
    doc = pymupdf.open(pdf)
    for i, page in enumerate(doc):
        fn = pathlib.Path(outdir) / f"{prefix}{i+1:02d}.png"
        pix = page.get_pixmap(dpi=dpi)
        pix.save(fn)
        txt = len(page.get_text().strip())
        print(f"{fn}  {pix.width}x{pix.height}  {os.path.getsize(fn)//1024}KB  textlayer_chars={txt}")
    print(f"\n{doc.page_count} pages -> {outdir}/ at {dpi} dpi")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
