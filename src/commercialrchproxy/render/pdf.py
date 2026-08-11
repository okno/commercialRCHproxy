"""Narrow-roll proxy rendering, distinct from any RCH-signed original PDF."""

from __future__ import annotations

import textwrap
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from commercialrchproxy.render.document_model import DocumentLine, DocumentModel

PROVISIONAL_PAPER_WIDTH_MM = 79.5
PROVISIONAL_CHARACTERS_PER_LINE = 48
MARGIN_MM = 4.0
MAX_PAGE_HEIGHT_MM = 1000.0


def _wrapped(lines: list[DocumentLine], characters_per_line: int) -> list[DocumentLine]:
    result: list[DocumentLine] = []
    for line in lines:
        wrap_width = max(1, characters_per_line // 2) if line.double_width else characters_per_line
        parts = textwrap.wrap(
            line.text,
            width=wrap_width,
            replace_whitespace=False,
            drop_whitespace=True,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]
        result.extend(
            DocumentLine(part, line.trace, line.align, line.bold, line.double_width, line.double_height)
            for part in parts
        )
    return result


def render_pdf(
    model: DocumentModel,
    path: Path,
    *,
    paper_width_mm: float = PROVISIONAL_PAPER_WIDTH_MM,
    characters_per_line: int = PROVISIONAL_CHARACTERS_PER_LINE,
) -> None:
    """Render a provisional proxy copy, never an RCH-original fiscal PDF."""
    lines = _wrapped([*model.header, *model.lines, *model.footer], characters_per_line)
    line_height = 3.6 * mm
    page_width = paper_width_mm * mm
    usable_width = page_width - 2 * MARGIN_MM * mm
    nominal_line_width = stringWidth("M" * characters_per_line, "Courier", 1.0)
    base_font_size = min(8.0, usable_width / nominal_line_width)
    max_line_units = max(1.0, (MAX_PAGE_HEIGHT_MM - 2 * MARGIN_MM) / 3.6)
    pages: list[list[DocumentLine]] = []
    current_page: list[DocumentLine] = []
    current_units = 0.0
    for line in lines:
        line_units = 1.9 if line.double_height else 1.0
        if current_page and current_units + line_units > max_line_units:
            pages.append(current_page)
            current_page = []
            current_units = 0.0
        current_page.append(line)
        current_units += line_units
    if current_page or not pages:
        pages.append(current_page)

    def page_height(page_lines: list[DocumentLine]) -> float:
        units = sum(1.9 if line.double_height else 1.0 for line in page_lines)
        return max(30 * mm, min(MAX_PAGE_HEIGHT_MM * mm, (units + 4) * line_height))

    first_height = page_height(pages[0])
    canvas = Canvas(str(path), pagesize=(page_width, first_height), pageCompression=1)
    canvas.setTitle("commercialRCHproxy rendered document")
    canvas.setSubject("PDF_PROXY_RENDERED - not an original RCH signed digital document")
    for page_lines in pages:
        height = page_height(page_lines)
        canvas.setPageSize((page_width, height))
        y = height - MARGIN_MM * mm
        for line in page_lines:
            size = base_font_size
            font = "Courier-Bold" if line.bold else "Courier"
            canvas.setFont(font, size)
            text = line.text
            horizontal_scale = 2.0 if line.double_width else 1.0
            vertical_scale = 2.0 if line.double_height else 1.0
            rendered_width = stringWidth(text, font, size) * horizontal_scale
            if line.align == "center":
                x = (page_width - rendered_width) / 2
            elif line.align == "right":
                x = page_width - MARGIN_MM * mm - rendered_width
            else:
                x = MARGIN_MM * mm
            canvas.saveState()
            canvas.translate(max(MARGIN_MM * mm, x), y)
            canvas.scale(horizontal_scale, vertical_scale)
            canvas.drawString(0, 0, text)
            canvas.restoreState()
            y -= line_height * (1.9 if line.double_height else 1.0)
        canvas.showPage()
    canvas.save()
