"""Reusable exports; audit events are created by the permission-checked views."""
import csv
from io import BytesIO, StringIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone
import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image


font_path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
pdfmetrics.registerFont(TTFont("Nasil", str(font_path)))


def safe_cell(value):
    text = str(value if value is not None else "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def export_csv(*, title, columns, rows, reference, generated_at=None, metadata=()):
    generated_at = generated_at or timezone.now()
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["NASIL Supply & Logistics", title])
    writer.writerow(["Generated at", timezone.localtime(generated_at).isoformat(timespec="seconds")])
    writer.writerow(["Export audit reference", str(reference)])
    for label, value in metadata:
        writer.writerow([safe_cell(label), safe_cell(value)])
    writer.writerow([])
    writer.writerow(columns)
    for row in rows:
        writer.writerow([safe_cell(value) for value in row])
    response = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="nasil-{generated_at:%Y%m%d-%H%M%S}.csv"'
    response["X-Audit-Reference"] = str(reference)
    response["Cache-Control"] = "private, no-store"
    return response


def export_pdf(*, title, columns, rows, reference, generated_at=None, metadata=(), portrait=False, evidence_image=None):
    generated_at = generated_at or timezone.now()
    buffer = BytesIO()
    page_size = A4 if portrait else landscape(A4)
    document = SimpleDocTemplate(buffer, pagesize=page_size, leftMargin=32, rightMargin=32, topMargin=42, bottomMargin=42, title=title, author="NASIL Supply & Logistics")
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("NasilText", parent=styles["Normal"], fontName="Nasil", fontSize=8, leading=12)
    heading = ParagraphStyle("NasilHeading", parent=normal, fontSize=18, leading=24, textColor=colors.HexColor("#9c4700"), spaceAfter=10)
    def paragraph(value):
        return Paragraph(escape(str(value if value is not None else "")), normal)
    story = [Paragraph(escape(title), heading), paragraph("NASIL Supply & Logistics"), paragraph("Generated: " + timezone.localtime(generated_at).isoformat(timespec="seconds")), paragraph("Export audit reference: " + str(reference)), Spacer(1, 12)]
    for label, value in metadata:
        story.extend([paragraph(f"{label}: {value}"), Spacer(1, 4)])
    story.append(Spacer(1, 10))
    table_rows = [[paragraph(value) for value in columns]]
    table_rows.extend([[paragraph(value) for value in row] for row in rows])
    if len(table_rows) == 1:
        table_rows.append([paragraph("No matching records")] + [paragraph("")] * (len(columns) - 1))
    width = page_size[0] - 64
    table = Table(table_rows, colWidths=[width / len(columns)] * len(columns), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fff0df")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#dfe3e8")),
    ]))
    story.append(table)
    if evidence_image:
        picture = Image(BytesIO(evidence_image))
        factor = min((page_size[0] - 64) / picture.imageWidth, 150 / picture.imageHeight, 1)
        picture.drawWidth = picture.imageWidth * factor
        picture.drawHeight = picture.imageHeight * factor
        picture.hAlign = "LEFT"
        story.extend([Spacer(1, 20), paragraph("Signature / signed delivery evidence"), Spacer(1, 8), picture])
    def footer(canvas, doc):
        canvas.setFont("Nasil", 7)
        canvas.setFillColor(colors.HexColor("#637381"))
        canvas.drawString(32, 22, "NASIL | " + str(reference))
        canvas.drawRightString(page_size[0] - 32, 22, f"Page {doc.page}")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="nasil-{generated_at:%Y%m%d-%H%M%S}.pdf"'
    response["X-Audit-Reference"] = str(reference)
    response["Cache-Control"] = "private, no-store"
    return response
