"""
Shared reportlab styling for the two Turkish PDFs in this folder
(Proje_Sonuclar_TR.pdf, Metrikler_Aciklama_TR.pdf). Registers DejaVuSans
(regular/bold/oblique/bold-oblique, bundled with matplotlib on this
machine) explicitly -- reportlab's default Helvetica has no glyphs for
Turkish characters (ı, İ, ğ, Ğ, ş, Ş, ç, Ç, ö, Ö, ü, Ü) and silently drops
or mis-renders them.
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, Image, ListFlowable, ListItem,
    PageBreak, HRFlowable, KeepTogether,
)

FONT_DIR = "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf"
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_ITALIC = os.path.join(FONT_DIR, "DejaVuSans-Oblique.ttf")
FONT_BOLDITALIC = os.path.join(FONT_DIR, "DejaVuSans-BoldOblique.ttf")

for path in (FONT_REGULAR, FONT_BOLD, FONT_ITALIC, FONT_BOLDITALIC):
    assert os.path.isfile(path), f"missing font file: {path}"

pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_REGULAR))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", FONT_BOLD))
pdfmetrics.registerFont(TTFont("DejaVuSans-Oblique", FONT_ITALIC))
pdfmetrics.registerFont(TTFont("DejaVuSans-BoldOblique", FONT_BOLDITALIC))
pdfmetrics.registerFontFamily(
    "DejaVuSans", normal="DejaVuSans", bold="DejaVuSans-Bold",
    italic="DejaVuSans-Oblique", boldItalic="DejaVuSans-BoldOblique",
)

INK = colors.HexColor("#0b0b0b")
INK2 = colors.HexColor("#52514e")
BLUE = colors.HexColor("#184f95")
RED = colors.HexColor("#b3261e")
GREEN = colors.HexColor("#0d6b0d")
GRID = colors.HexColor("#d8d7d2")
HEADBG = colors.HexColor("#eef2f8")

PAGE_SIZE = A4
MARGINS = dict(leftMargin=2.1 * cm, rightMargin=2.1 * cm, topMargin=2.0 * cm, bottomMargin=2.0 * cm)

TITLE = ParagraphStyle("TitleTR", fontName="DejaVuSans-Bold", fontSize=20, leading=25,
                       textColor=INK, spaceAfter=4)
SUBTITLE = ParagraphStyle("SubtitleTR", fontName="DejaVuSans-Oblique", fontSize=11.5, leading=15,
                          textColor=INK2, spaceAfter=14)
H1 = ParagraphStyle("H1TR", fontName="DejaVuSans-Bold", fontSize=15.5, leading=19,
                    textColor=BLUE, spaceBefore=18, spaceAfter=8)
H2 = ParagraphStyle("H2TR", fontName="DejaVuSans-Bold", fontSize=12.5, leading=16,
                    textColor=INK, spaceBefore=12, spaceAfter=6)
H3 = ParagraphStyle("H3TR", fontName="DejaVuSans-Bold", fontSize=11, leading=14,
                    textColor=INK, spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("BodyTR", fontName="DejaVuSans", fontSize=10, leading=14.5,
                      textColor=INK, spaceAfter=7, alignment=4)  # justify
NOTE = ParagraphStyle("NoteTR", fontName="DejaVuSans-Oblique", fontSize=9, leading=12.5,
                      textColor=INK2, spaceAfter=7)
CAPTION = ParagraphStyle("CaptionTR", fontName="DejaVuSans-Oblique", fontSize=8.7, leading=11.5,
                         textColor=INK2, spaceAfter=12, alignment=1)  # center
SOURCE = ParagraphStyle("SourceTR", fontName="DejaVuSans-Oblique", fontSize=8.3, leading=11,
                        textColor=INK2, spaceAfter=8)
BULLET = ParagraphStyle("BulletTR", fontName="DejaVuSans", fontSize=10, leading=14.5,
                        textColor=INK, spaceAfter=4)
CELL = ParagraphStyle("CellTR", fontName="DejaVuSans", fontSize=8.6, leading=11, textColor=INK)
CELL_HEAD = ParagraphStyle("CellHeadTR", fontName="DejaVuSans-Bold", fontSize=8.6, leading=11, textColor=INK)
CELL_HL = ParagraphStyle("CellHLTR", fontName="DejaVuSans-Bold", fontSize=8.6, leading=11, textColor=RED)


def p(text, style=BODY):
    return Paragraph(text, style)


def h1(text):
    return Paragraph(text, H1)


def h2(text):
    return Paragraph(text, H2)


def h3(text):
    return Paragraph(text, H3)


def bullets(items, style=BULLET):
    return ListFlowable(
        [ListItem(Paragraph(t, style), leftIndent=6, bulletColor=INK2) for t in items],
        bulletType="bullet", start="•", leftIndent=14, spaceBefore=2, spaceAfter=8,
    )


def hr():
    return HRFlowable(width="100%", thickness=0.6, color=GRID, spaceBefore=10, spaceAfter=10)


def source_note(text):
    return Paragraph(f"<i>(kaynak: {text})</i>", SOURCE)


def make_table(header, rows, col_widths=None, highlight_col=None):
    """header: list[str]; rows: list[list[str]]. Wraps every cell in a
    Paragraph so long Turkish text wraps instead of overflowing."""
    data = [[Paragraph(h, CELL_HEAD) for h in header]]
    for r in rows:
        row_cells = []
        for i, val in enumerate(r):
            style = CELL_HL if (highlight_col is not None and i == highlight_col) else CELL
            row_cells.append(Paragraph(str(val), style))
        data.append(row_cells)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADBG),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafaf9")]),
    ]))
    return t


def figure(path, caption, width=15.5 * cm):
    from PIL import Image as PILImage
    with PILImage.open(path) as im:
        iw, ih = im.size
    height = width * ih / iw
    max_h = 18 * cm
    if height > max_h:
        height = max_h
        width = height * iw / ih
    img = Image(path, width=width, height=height)
    return KeepTogether([img, Spacer(1, 4), Paragraph(caption, CAPTION)])
