#!/usr/bin/env python3
"""Render a plain-text/markdown cover letter to a one-page PDF in the house style.

  uv run skills/apply-to-jobs/scripts/render_cover_letter.py --in letter.md --out letter.pdf [--png]

Input format (blank line between blocks):
  block 1  name + contact lines (one per line)   -> bold name, grey contact line
  block 2  date
  block 3  recipient / salutation and body paragraphs ...
  last     "Sincerely," + name
Exits 1 if the letter does not fit on one page.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def fonts() -> tuple[str, str]:
    return "Helvetica", "Helvetica-Bold"


def blocks(text: str) -> list[list[str]]:
    result, current = [], []
    for line in text.splitlines():
        line = line.rstrip()
        if line.strip():
            current.append(line.strip())
        elif current:
            result.append(current)
            current = []
    if current:
        result.append(current)
    return result


def render(src: Path, out: Path) -> None:
    regular, bold = fonts()
    body = ParagraphStyle("body", fontName=regular, fontSize=10.3, leading=14.2, spaceAfter=9)
    name = ParagraphStyle("name", parent=body, fontName=bold, fontSize=15, leading=18, spaceAfter=2)
    contact = ParagraphStyle("contact", parent=body, fontSize=9.2, leading=12, textColor="#333333", spaceAfter=12)

    parts = blocks(src.read_text())
    if len(parts) < 4:
        sys.exit("error: expected at least header, date, salutation/body, and closing blocks")
    header, rest = parts[0], parts[1:]
    story = [Paragraph(escape(header[0]), name),
             Paragraph(escape(" | ".join(header[1:])), contact)]
    for i, block in enumerate(rest):
        story.append(Paragraph("<br/>".join(escape(line) for line in block), body))
        if i == 0:
            story.append(Spacer(1, 2))
    doc = SimpleDocTemplate(str(out), pagesize=LETTER, leftMargin=0.78 * inch, rightMargin=0.78 * inch,
                            topMargin=0.62 * inch, bottomMargin=0.62 * inch,
                            title=out.stem.replace("_", " "), author=header[0])
    doc.build(story)


def page_count(pdf: Path) -> int:
    import pypdfium2 as pdfium
    return len(pdfium.PdfDocument(str(pdf)))


def to_png(pdf: Path) -> Path:
    import pypdfium2 as pdfium
    png = pdf.with_suffix(".png")
    pdfium.PdfDocument(str(pdf))[0].render(scale=1.4).to_pil().save(png)
    return png


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="src", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--png", action="store_true", help="also write a preview PNG next to the PDF")
    a = p.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    render(a.src, a.out)
    pages = page_count(a.out)
    if a.png:
        print(f"preview: {to_png(a.out)}")
    if pages != 1:
        sys.exit(f"error: {a.out} has {pages} pages; shorten the letter to fit one page")
    print(f"ok: {a.out} (1 page)")


if __name__ == "__main__":
    main()
