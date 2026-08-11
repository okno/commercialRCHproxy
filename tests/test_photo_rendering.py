"""Redacted rendering references derived from the supplied receipt photo.

The three ``photo_*.expected.PULITO.txt`` files are expected human-readable
output only. Business identifiers and transaction values were transcribed for
analysis and then replaced with obvious synthetic placeholders before these
public fixtures were committed. Structural headings/layout remain
photo-derived. The files are NOT RCH raw-byte captures, protocol frames, XML7
fixtures, printer responses, or proof of fiscal/legal status. These tests
deliberately construct :class:`DocumentModel` lines directly and do not call a
protocol parser or document classifier.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pypdf import PdfReader

from commercialrchproxy.render.clean_text import render_clean_text
from commercialrchproxy.render.document_model import DocumentLine, DocumentModel, SourceTrace
from commercialrchproxy.render.pdf import render_pdf

FIXTURE_DIR = Path(__file__).parent / "fixtures"
PHOTO_OBSERVED = SourceTrace(evidence="OBSERVED_STRUCTURE")
PUBLIC_PLACEHOLDER = SourceTrace(evidence="SYNTHETIC_PLACEHOLDER")


def _compact_management_model() -> DocumentModel:
    return DocumentModel(
        document_type="documento_gestionale",
        observed_variant="compact_table_summary",
        metadata={
            "fixture_origin": "supplied_receipt_photograph_redacted",
            "fixture_kind": "expected_human_output",
            "fixture_redaction": "business_and_transaction_values_replaced",
            "contains_original_identifiers": False,
            "is_rch_protocol_fixture": False,
            "protocol_identifier": None,
            "legal_status": "unverified",
        },
        lines=[
            DocumentLine("HOTEL ESEMPIO", PUBLIC_PLACEHOLDER, align="center", double_height=True),
            DocumentLine("SOCIETA ESEMPIO S.R.L.", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("VIA ESEMPIO N.4", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("00000 CITTA -XX-", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("TELEFONO 0000-0000000", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("C.F. - P.IVA 00000000000", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine(
                "DOCUMENTO GESTIONALE",
                PHOTO_OBSERVED,
                align="center",
                bold=True,
                double_height=True,
            ),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("EURO", PHOTO_OBSERVED, align="right"),
            DocumentLine("Prodotto di esempio                        0,00", PUBLIC_PLACEHOLDER),
            DocumentLine("TOT                                        0,00", PUBLIC_PLACEHOLDER, bold=True),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("Tavolo: 00-X", PUBLIC_PLACEHOLDER, bold=True, double_height=True),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("01-01-2026 12:00", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("DOC.GESTIONALE N. 0001-0003", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("XXXXXXXXXXX", PUBLIC_PLACEHOLDER, align="center"),
        ],
    )


def _commercial_sale_model() -> DocumentModel:
    return DocumentModel(
        document_type="documento_commerciale",
        observed_variant="sale_or_service",
        metadata={
            "fixture_origin": "supplied_receipt_photograph_redacted",
            "fixture_kind": "expected_human_output",
            "fixture_redaction": "business_and_transaction_values_replaced",
            "contains_original_identifiers": False,
            "is_rch_protocol_fixture": False,
            "protocol_identifier": None,
            "legal_status": "unverified",
        },
        lines=[
            DocumentLine("HOTEL ESEMPIO", PUBLIC_PLACEHOLDER, align="center", double_height=True),
            DocumentLine("SOCIETA ESEMPIO S.R.L.", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("VIA ESEMPIO N.4", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("00000 CITTA -XX-", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("TELEFONO 0000-0000000", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("C.F. - P.IVA 00000000000", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine(
                "DOCUMENTO COMMERCIALE",
                PHOTO_OBSERVED,
                align="center",
                bold=True,
                double_height=True,
            ),
            DocumentLine(
                "di vendita o prestazione",
                PHOTO_OBSERVED,
                align="center",
                double_height=True,
            ),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("DESCRIZIONE                     IVA    Prezzo(€)", PHOTO_OBSERVED, bold=True),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("Prodotto di esempio              00%       0,00", PUBLIC_PLACEHOLDER),
            DocumentLine("#", PHOTO_OBSERVED),
            DocumentLine("#Tavolo: 00-X", PUBLIC_PLACEHOLDER),
            DocumentLine("#", PHOTO_OBSERVED),
            DocumentLine("------------------------------------------------", PHOTO_OBSERVED),
            DocumentLine("TOTALE COMPLESSIVO                         0,00", PUBLIC_PLACEHOLDER, bold=True),
            DocumentLine("di cui IVA                                 0,00", PUBLIC_PLACEHOLDER),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("Pagamento contante                         0,00", PUBLIC_PLACEHOLDER),
            DocumentLine("Importo pagato                             0,00", PUBLIC_PLACEHOLDER),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("01-01-2026 12:00", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("DOCUMENTO N. 0001-0001", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("RT XXXXXXXXXXX", PUBLIC_PLACEHOLDER, align="center"),
        ],
    )


def _detailed_management_model() -> DocumentModel:
    return DocumentModel(
        document_type="documento_gestionale",
        observed_variant="payment_vat_detail",
        metadata={
            "fixture_origin": "supplied_receipt_photograph_redacted",
            "fixture_kind": "expected_human_output",
            "fixture_redaction": "business_and_transaction_values_replaced",
            "contains_original_identifiers": False,
            "is_rch_protocol_fixture": False,
            "protocol_identifier": None,
            "legal_status": "unverified",
        },
        lines=[
            DocumentLine("HOTEL ESEMPIO", PUBLIC_PLACEHOLDER, align="center", double_height=True),
            DocumentLine("SOCIETA ESEMPIO S.R.L.", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("VIA ESEMPIO N.4", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("00000 CITTA -XX-", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("TELEFONO 0000-0000000", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("C.F. - P.IVA 00000000000", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine(
                "DOCUMENTO GESTIONALE",
                PHOTO_OBSERVED,
                align="center",
                bold=True,
                double_height=True,
            ),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("EURO", PHOTO_OBSERVED, align="right"),
            DocumentLine("Prodotto di esempio                       0,00 A", PUBLIC_PLACEHOLDER),
            DocumentLine("TOT                                        0,00", PUBLIC_PLACEHOLDER, bold=True),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("Contanti                                   0,00", PUBLIC_PLACEHOLDER),
            DocumentLine("RESTO                                      0,00", PUBLIC_PLACEHOLDER, bold=True),
            DocumentLine("------------------------------------------------", PHOTO_OBSERVED),
            DocumentLine("Aliquota IVA             Imponibile         IVA", PHOTO_OBSERVED),
            DocumentLine("A 00% 00%                      0,00         0,00", PUBLIC_PLACEHOLDER),
            DocumentLine("------------------------------------------------", PHOTO_OBSERVED),
            DocumentLine("TOT                            0,00         0,00", PUBLIC_PLACEHOLDER),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("Tavolo: 00-X", PUBLIC_PLACEHOLDER, bold=True, double_height=True),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("01\\01\\26          12:02             N. 0001-0001", PUBLIC_PLACEHOLDER),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("01-01-2026 12:00", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("DOC.GESTIONALE N. 0001-0004", PUBLIC_PLACEHOLDER, align="center"),
            DocumentLine("", PHOTO_OBSERVED),
            DocumentLine("XXXXXXXXXXX", PUBLIC_PLACEHOLDER, align="center"),
        ],
    )


ModelFactory = Callable[[], DocumentModel]

PHOTO_RENDER_CASES: tuple[tuple[str, ModelFactory, tuple[str, ...]], ...] = (
    (
        "photo_compact_management.expected.PULITO.txt",
        _compact_management_model,
        ("DOCUMENTO GESTIONALE", "0001-0003", "XXXXXXXXXXX"),
    ),
    (
        "photo_commercial_sale.expected.PULITO.txt",
        _commercial_sale_model,
        ("DOCUMENTO COMMERCIALE", "0001-0001", "RT XXXXXXXXXXX"),
    ),
    (
        "photo_detailed_management.expected.PULITO.txt",
        _detailed_management_model,
        ("DOCUMENTO GESTIONALE", "A 00% 00%", "0001-0004"),
    ),
)


@pytest.mark.parametrize(("fixture_name", "model_factory", "pdf_markers"), PHOTO_RENDER_CASES)
def test_photo_derived_clean_text_is_preserved(
    fixture_name: str,
    model_factory: ModelFactory,
    pdf_markers: tuple[str, ...],
) -> None:
    del pdf_markers
    model = model_factory()
    expected = (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")

    assert model.metadata["fixture_kind"] == "expected_human_output"
    assert model.metadata["fixture_redaction"] == "business_and_transaction_values_replaced"
    assert model.metadata["contains_original_identifiers"] is False
    assert model.metadata["is_rch_protocol_fixture"] is False
    assert model.metadata["protocol_identifier"] is None
    assert model.metadata["legal_status"] == "unverified"
    evidence = {line.trace.evidence for line in model.lines}
    assert evidence == {"OBSERVED_STRUCTURE", "SYNTHETIC_PLACEHOLDER"}
    assert all(line.trace.source_offset is None for line in model.lines)
    assert all(line.trace.source_frame is None for line in model.lines)
    assert all(line.trace.source_xml_path is None for line in model.lines)
    assert render_clean_text(model) == expected


@pytest.mark.parametrize(("fixture_name", "model_factory", "pdf_markers"), PHOTO_RENDER_CASES)
def test_photo_derived_pdf_is_readable(
    tmp_path: Path,
    fixture_name: str,
    model_factory: ModelFactory,
    pdf_markers: tuple[str, ...],
) -> None:
    model = model_factory()
    pdf_path = tmp_path / fixture_name.replace(".expected.PULITO.txt", ".pdf")

    render_pdf(model, pdf_path)

    assert pdf_path.read_bytes().startswith(b"%PDF-")
    reader = PdfReader(str(pdf_path))
    assert reader.is_encrypted is False
    assert len(reader.pages) == 1
    assert "PDF_PROXY_RENDERED" in str(reader.metadata.subject)

    extracted = " ".join((reader.pages[0].extract_text() or "").split())
    assert extracted
    for marker in pdf_markers:
        assert marker in extracted
