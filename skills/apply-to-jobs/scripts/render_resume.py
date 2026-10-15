#!/usr/bin/env python3
"""Not used for cv_job resumes. Those are TeX files rendered by scripts/render_tex.py.

Render a constrained-markdown resume to a one-page PDF (layout of private/documents/Resume.pdf).

  uv run skills/apply-to-jobs/scripts/render_resume.py --in resume.md --out resume.pdf [--png]

Input grammar:
  # Name
  contact line (markdown links allowed)
  ## Section
  ### Entry heading :: right-aligned date        (heading may contain [links](url))
  **Bold line** :: **right text**                 (plain line under an entry)
  - bullet
Exits 1 if the result is not exactly one page.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BLUE = "#1155CC"


def fonts() -> tuple[str, str]:
    return "Helvetica", "Helvetica-Bold"


def inline(md: str) -> str:
    """Escape text, then convert [text](url) and **bold** to reportlab markup."""
    parts = re.split(r"(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*)", md)
    out = []
    for part in parts:
        m = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", part)
        if m:
            out.append(f'<link href="{escape(m.group(2))}" color="{BLUE}"><u>{escape(m.group(1))}</u></link>')
            continue
        m = re.fullmatch(r"\*\*([^*]+)\*\*", part)
        if m:
            out.append(f"<b>{escape(m.group(1))}</b>")
            continue
        out.append(escape(part))
    return "".join(out)


def two_col(left: str, right: str, style_l: ParagraphStyle, style_r: ParagraphStyle, width: float):
    t = Table([[Paragraph(left, style_l), Paragraph(right, style_r)]], colWidths=[width * 0.78, width * 0.22], hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    return t


def build(src: Path, out: Path) -> None:
    regular, bold = fonts()
    margin_x, margin_top, margin_bottom = 0.6 * inch, 0.45 * inch, 0.4 * inch
    width = LETTER[0] - 2 * margin_x - 12  # frame padding is 6pt each side
    name_s = ParagraphStyle("name", fontName=bold, fontSize=15, leading=18, alignment=1, spaceAfter=1)
    contact_s = ParagraphStyle("contact", fontName=regular, fontSize=8.5, leading=11, alignment=1, spaceAfter=2)
    section_s = ParagraphStyle("section", fontName=bold, fontSize=13, leading=14, spaceBefore=0, spaceAfter=0)
    entry_s = ParagraphStyle("entry", fontName=bold, fontSize=10, leading=12, textColor=BLUE)
    date_s = ParagraphStyle("date", fontName=regular, fontSize=10, leading=12, textColor=BLUE, alignment=2)
    plain_s = ParagraphStyle("plain", fontName=regular, fontSize=10, leading=12)
    plain_r = ParagraphStyle("plainr", parent=plain_s, alignment=2)
    bullet_s = ParagraphStyle("bullet", fontName=regular, fontSize=10, leading=11.8)

    story = []
    first_section = True
    for raw in src.read_text().splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), name_s))
        elif line.startswith("## "):
            if not first_section:
                story.append(Spacer(1, 3))
            first_section = False
            story.append(Paragraph(inline(line[3:]), section_s))
            story.append(HRFlowable(width="100%", thickness=0.8, color="#000000", spaceBefore=0, spaceAfter=1))
        elif line.startswith("### "):
            left, _, right = line[4:].partition(" :: ")
            story.append(two_col(inline(left), inline(right), entry_s, date_s, width))
        elif line.startswith("- "):
            story.append(Paragraph("• " + inline(line[2:]), bullet_s))
        else:
            left, _, right = line.partition(" :: ")
            if right:
                story.append(two_col(inline(left), inline(right), plain_s, plain_r, width))
            else:
                story.append(Paragraph(inline(left), plain_s if story else contact_s))
    # the contact line is the first non-heading plain line; restyle it
    for i, f in enumerate(story):
        if isinstance(f, Paragraph) and f.style is plain_s:
            story[i] = Paragraph(f.text, contact_s)
            break
    doc = SimpleDocTemplate(str(out), pagesize=LETTER, leftMargin=margin_x, rightMargin=margin_x,
                            topMargin=margin_top, bottomMargin=margin_bottom, title=out.stem.replace("_", " "))
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
    p.add_argument("--png", action="store_true")
    a = p.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    build(a.src, a.out)
    pages = page_count(a.out)
    if a.png:
        print(f"preview: {to_png(a.out)}")
    if pages != 1:
        sys.exit(f"error: {a.out} has {pages} pages; trim bullets to fit one page")
    print(f"ok: {a.out} (1 page)")


if __name__ == "__main__":
    main()
