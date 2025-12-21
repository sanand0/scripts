---
name: pdf
description: How to read, manipulate, and generate PDFs using CLI tools and Python libraries.
---

## Read PDFs as images

```bash
# Convert PDF pages to PNGs for visual inspection
pdftoppm -r 200 -png -f 1 -l 3 input.pdf output
# Writes: output-1.png, output-2.png, ...
```

- `pdfplumber` helps text/table extraction, but retain visual inspection to avoid layout issues.
- Re-render after each meaningful layout/content change

## Manipulate with pdfcpu / qpdf

```bash
# In sandboxed envs:
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$PWD/.xdg}"

pdfcpu validate -- input.pdf
pdfcpu merge -- merged.pdf a.pdf b.pdf
pdfcpu trim -pages "1-3" -- input.pdf first3.pdf
pdfcpu rotate -pages "1" -- input.pdf 90 rotated.pdf
pdfcpu resize -- "form:A4, enforce:true" input.pdf output.pdf
pdfcpu pagelayout set input.pdf output.pdf TwoPageLeft
pdfcpu optimize -- input.pdf optimized.pdf
pdfcpu zoom -- "pages:1-5, factor:1.5" input.pdf output.pdf
pdfcpu properties add input.pdf output.pdf "Author:John Doe" "Custom:Value"
pdfcpu extract -mode font input.pdf output_dir
pdfcpu extract -mode image input.pdf output_dir
pdfcpu import output.pdf image1.jpg image2.png
pdfcpu import -- "formsize:A4, pos:c" output.pdf image1.jpg
pdfcpu split -mode span input.pdf output_dir 5
pdfcpu split -mode page input.pdf output_dir 3 7 12
pdfcpu collect -pages "1,3,2,5-10,4" input.pdf output.pdf

pdfcpu form list input.pdf
pdfcpu form fill input.pdf data.json output.pdf
pdfcpu form lock input.pdf output.pdf fieldID1 fieldID2
pdfcpu form export input.pdf output.json

pdfcpu stamp add -mode text -- "CONFIDENTIAL" "rot:45, opacity:0.5" input.pdf output.pdf
pdfcpu watermark add -mode image -- "logo.png" "pos:tl, offset:10 10" input.pdf output.pdf
pdfcpu stamp update -pages 1-10 -mode text -- "REVISED" "" input.pdf output.pdf
pdfcpu bookmarks import input.pdf bookmarks.json output.pdf

# Split pages into n equal parts (e.g., 2x2 grid)
pdfcpu ndown -pages 1-10 -- "n:2" input.pdf output_dir
# Arrange pages into grid layout for browsing
pdfcpu grid -- "rows:3, cols:3" input.pdf output.pdf
# Create booklet format for physical printing
pdfcpu booklet -- "formsize:A4" input.pdf output.pdf
# Cut pages with custom positioning
pdfcpu cut -- "hor:0.5, vert:0.3" input.pdf output_dir

qpdf input.pdf --pages . 2-4 -- pages-2-4.pdf
# Rotate page 1 by 90 degrees clockwise
qpdf input.pdf output.pdf --rotate=+90:1
qpdf --empty --pages a.pdf b.pdf -- merged.pdf
qpdf --linearize input.pdf linearized.pdf
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf
qpdf --password=mypassword --decrypt encrypted.pdf decrypted.pdf
```

## Python: generate, extract, stamp

```py
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pdfplumber>=0.11", "pypdf>=5", "reportlab>=4"]
# ///

import csv
from io import BytesIO
from pathlib import Path

import pdfplumber
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import PageBreak, SimpleDocTemplate, Table, TableStyle
from reportlab.pdfgen import canvas


def make_input_pdf(path: Path) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    data = [["Item", "Qty"], ["Apples", "2"], ["Bananas", "3"]]

    def make_table() -> Table:
        table = Table(data)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ]
            )
        )
        return table

    story = [make_table(), PageBreak(), make_table(), PageBreak(), make_table()]
    doc.build(story)


def extract_first_table_to_csv(pdf_path: Path, csv_path: Path) -> None:
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "intersection_tolerance": 3,
    }
    with pdfplumber.open(str(pdf_path)) as pdf:
        table = pdf.pages[0].extract_table(table_settings=table_settings)
    if not table:
        raise RuntimeError("No table found; tune table_settings or fall back to extract_words().")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(table)


def make_text_watermark_pdf(text: str) -> BytesIO:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFillAlpha(0.15)
    c.setFont("Helvetica", 48)
    c.saveState()
    c.translate(72, 72)
    c.rotate(30)
    c.drawString(0, 0, text)  # Use ASCII hyphens; some PDFs render Unicode dashes poorly.
    c.restoreState()
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def stamp_all_pages(in_pdf: Path, out_pdf: Path, watermark_pdf_bytes: BytesIO) -> None:
    watermark_page = PdfReader(watermark_pdf_bytes).pages[0]
    reader = PdfReader(str(in_pdf))
    writer = PdfWriter()
    for page in reader.pages:
        page.merge_page(watermark_page)
        writer.add_page(page)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    with out_pdf.open("wb") as f:
        writer.write(f)


def main() -> None:
    make_input_pdf(Path("input.pdf"))
    extract_first_table_to_csv(Path("input.pdf"), Path("table.csv"))
    stamp_all_pages(Path("input.pdf"), Path("watermarked.pdf"), make_text_watermark_pdf("DRAFT"))


if __name__ == "__main__":
    main()
```

## Python: create multi-page document

```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table
from reportlab.lib.styles import getSampleStyleSheet

doc = SimpleDocTemplate("report.pdf", pagesize=letter)
styles = getSampleStyleSheet()
story = []

story.append(Paragraph("Report Title", styles['Title']))
story.append(Spacer(1, 12))
story.append(Paragraph("Body content...", styles['Normal']))
story.append(PageBreak())

data = [['Name', 'Age'], ['Alice', '30'], ['Bob', '25']]
story.append(Table(data))

doc.build(story)
```
