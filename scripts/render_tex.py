"""Render a TeX resume with tectonic or pdflatex and reject more than two pages.

  uv run scripts/render_tex.py --in sample/cv_bases/example.tex --out /tmp/resume.pdf
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pypdfium2 as pdfium


def engine() -> tuple[str, str]:
    tectonic = shutil.which("tectonic")
    if tectonic:
        return "tectonic", tectonic
    pdflatex = shutil.which("pdflatex")
    if pdflatex:
        return "pdflatex", pdflatex
    sys.exit("error: neither tectonic nor pdflatex is on PATH")


def render(src: Path, out: Path) -> None:
    kind, binary = engine()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        if kind == "tectonic":
            cmd = [binary, "--outdir", str(work), str(src)]
        else:
            cmd = [binary, "-interaction=nonstopmode", f"-output-directory={work}", str(src)]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        pdfs = list(work.glob("*.pdf"))
        if proc.returncode != 0 or not pdfs:
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            sys.exit(f"error: {kind} failed for {src}")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdfs[0], out)


def page_count(path: Path) -> int:
    doc = pdfium.PdfDocument(str(path))
    try:
        return len(doc)
    finally:
        doc.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="src", type=Path, required=True)
    parser.add_argument("--out", dest="out", type=Path, required=True)
    args = parser.parse_args()
    render(args.src, args.out)
    pages = page_count(args.out)
    print(f"{pages} page(s) {args.out}")
    if pages < 1 or pages > 2:
        sys.exit(f"error: {args.out} is {pages} pages; expected 1 or 2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
