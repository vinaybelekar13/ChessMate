"""Docling fallback adapter (spec §7E, §45).

UNTESTED — same caveat as mineru_adapter.py. Used only when MinerU raises on
a given document (e.g. an unusual layout). Returns the same `RawBlock` shape
so structure_detector.py doesn't need to know which parser produced it.
"""
from __future__ import annotations
from app.ingestion.mineru_adapter import RawBlock


class DoclingError(RuntimeError):
    pass


def parse(pdf_path: str) -> list[RawBlock]:
    from app.config import settings  # lazy import, see mineru_adapter.py

    if not settings.docling_enabled:
        raise DoclingError("Docling fallback disabled in config")
    # Real sketch:
    #   from docling.document_converter import DocumentConverter
    #   doc = DocumentConverter().convert(pdf_path).document
    #   walk doc.iterate_items() -> map to RawBlock, using item.label for block_type
    raise DoclingError(
        "Docling not wired up — install `docling`, run DocumentConverter on a "
        "sample PDF, and map its item labels onto RawBlock.block_type here."
    )
