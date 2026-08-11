"""Render only human-visible model lines; never emit protocol labels."""

from __future__ import annotations

from commercialrchproxy.render.document_model import DocumentModel


def render_clean_text(model: DocumentModel) -> str:
    visible_lines = [*model.header, *model.lines, *model.footer]
    if not visible_lines:
        return ""
    return "\n".join(line.text for line in visible_lines) + "\n"
