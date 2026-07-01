"""md_to_pdf — render a Markdown paper to a typeset PDF with reportlab (pure-Python, no
system deps). Handles: #/##/### headings, paragraphs, **bold**/*italic*/`code`/[links],
markdown tables, ![images], fenced code blocks, bullet/numbered lists, and --- rules.
Image paths resolve relative to the Markdown file.

Usage:  .venv/bin/python docs/benchmarks/md_to_pdf.py docs/benchmarks/hibrid_evaluation.md [out.pdf]
"""
import os
import re
import sys

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (Image, ListFlowable, ListItem, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle, HRFlowable)

GREEN = colors.HexColor("#176043")
SLATE = colors.HexColor("#3b5b8c")
RULE = colors.HexColor("#cabfa6")


def styles():
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.5, leading=13.5,
                          alignment=TA_JUSTIFY, spaceAfter=6)
    return {
        "title": ParagraphStyle("title", parent=ss["Title"], fontSize=17, leading=21,
                                textColor=GREEN, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, leading=16,
                             textColor=GREEN, spaceBefore=12, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontSize=11, leading=14,
                             textColor=SLATE, spaceBefore=8, spaceAfter=3),
        "body": body,
        "cell": ParagraphStyle("cell", parent=body, fontSize=8, leading=10, alignment=0, spaceAfter=0),
        "cellh": ParagraphStyle("cellh", parent=body, fontSize=8, leading=10, spaceAfter=0,
                                textColor=colors.white),
        "cap": ParagraphStyle("cap", parent=body, fontSize=8, leading=11, textColor=colors.grey),
        "code": ParagraphStyle("code", parent=ss["Code"], fontSize=8, leading=11,
                               backColor=colors.HexColor("#f4efe3")),
        "li": ParagraphStyle("li", parent=body, spaceAfter=3),
    }


def inline(t):
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2" color="#3b5b8c">\1</link>', t)
    return t


def render(md_path, out_path):
    base = os.path.dirname(os.path.abspath(md_path))
    lines = open(md_path, encoding="utf-8").read().split("\n")
    S = styles()
    flow = []
    i, n = 0, len(lines)
    page_w = A4[0] - 3.6 * cm

    while i < n:
        ln = lines[i]

        # fenced code
        if ln.startswith("```"):
            i += 1; buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            flow.append(Preformatted("\n".join(buf), S["code"])); flow.append(Spacer(1, 6))
            continue

        # image
        m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", ln.strip())
        if m:
            p = os.path.join(base, m.group(2))
            if os.path.exists(p):
                from reportlab.lib.utils import ImageReader
                iw, ih = ImageReader(p).getSize()
                w = min(page_w, 15 * cm); h = w * ih / iw
                flow.append(Image(p, width=w, height=h)); flow.append(Spacer(1, 3))
            i += 1
            continue

        # table block
        if ln.strip().startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            header, data = rows[0], rows[2:]  # rows[1] is the --- separator
            tbl = [[Paragraph(inline(c), S["cellh"]) for c in header]]
            tbl += [[Paragraph(inline(c), S["cell"]) for c in r] for r in data]
            ncols = len(header)
            t = Table(tbl, colWidths=[page_w / ncols] * ncols, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                ("GRID", (0, 0), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#faf7ef")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            flow.append(t); flow.append(Spacer(1, 8))
            continue

        # headings
        if ln.startswith("# "):
            flow.append(Paragraph(inline(ln[2:]), S["title"]))
        elif ln.startswith("## "):
            flow.append(Paragraph(inline(ln[3:]), S["h2"]))
        elif ln.startswith("### "):
            flow.append(Paragraph(inline(ln[4:]), S["h3"]))
        elif ln.strip() == "---":
            flow.append(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=6, spaceAfter=6))
        elif re.match(r"^\s*[-*] ", ln):  # bullet list block
            items = []
            while i < n and re.match(r"^\s*[-*] ", lines[i]):
                items.append(ListItem(Paragraph(inline(re.sub(r"^\s*[-*] ", "", lines[i])), S["li"]),
                                      leftIndent=10))
                i += 1
            flow.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=12))
            continue
        elif ln.strip().startswith("*Figure") or ln.strip().startswith("*Table"):
            flow.append(Paragraph(inline(ln.strip().strip("*")), S["cap"])); flow.append(Spacer(1, 6))
        elif ln.strip() == "":
            pass
        else:
            flow.append(Paragraph(inline(ln), S["body"]))
        i += 1

    doc = SimpleDocTemplate(out_path, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            title="hibrid — empirical evaluation")
    doc.build(flow)
    print(f"PDF -> {out_path}  ({os.path.getsize(out_path)//1024} KB)")


if __name__ == "__main__":
    md = sys.argv[1] if len(sys.argv) > 1 else "docs/benchmarks/hibrid_evaluation.md"
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(md)[0] + ".pdf"
    render(md, out)
