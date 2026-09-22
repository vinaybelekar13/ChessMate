"""Local PDF extraction fallback (spec §8/§9 of the follow-up brief).

Used when neither MinerU nor Docling is installed/available. Unlike those
two, this one has actually been run in the build sandbox against a real
(synthetic) PDF — see tests/test_local_pdf_adapter.py — because pdfplumber
is present here and MinerU/Docling are not.

Heading detection: pdfplumber exposes per-character font size
(`char["size"]`). We take the modal (most common) size across the whole
document as "body text" and treat any line whose average char size is
meaningfully larger as a heading candidate. This is coarser than MinerU's
layout model but is real, not fabricated — it will over/under-detect on
unusual book layouts and should be tuned per book family, same as
structure_detector's font-size fallback path that consumes its output.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass

from app.ingestion.mineru_adapter import RawBlock


class LocalPdfError(RuntimeError):
    pass


@dataclass
class _Line:
    page_number: int
    text: str
    avg_size: float


def _extract_lines(pdf) -> list[_Line]:
    lines: list[_Line] = []
    for page in pdf.pages:
        chars = page.chars
        if not chars:
            continue
        # group chars into lines by rounded 'top' position
        by_top: dict[int, list] = {}
        for c in chars:
            key = round(c["top"])
            by_top.setdefault(key, []).append(c)
        for top in sorted(by_top.keys()):
            row = by_top[top]
            row.sort(key=lambda c: c["x0"])
            text = "".join(c["text"] for c in row).strip()
            if not text:
                continue
            avg_size = sum(c["size"] for c in row) / len(row)
            lines.append(_Line(page_number=page.page_number, text=text, avg_size=avg_size))
    return lines


def parse(pdf_path: str) -> list[RawBlock]:
    try:
        import pdfplumber
    except ImportError as e:
        raise LocalPdfError(
            "pdfplumber is not installed. Local PDF fallback needs at least "
            "one working PDF text extractor — run `pip install pdfplumber`."
        ) from e

    try:
        with pdfplumber.open(pdf_path) as pdf:
            lines = _extract_lines(pdf)
    except Exception as e:  # pdfplumber raises assorted exceptions on malformed PDFs
        raise LocalPdfError(f"pdfplumber failed to open/parse {pdf_path!r}: {e}") from e

    if not lines:
        raise LocalPdfError(
            f"No extractable text found in {pdf_path!r} — it may be a scanned/"
            "image-only PDF, which this fallback (no OCR) cannot read. "
            "MinerU (with OCR) is the right tool for scanned books."
        )

    size_counts = Counter(round(l.avg_size) for l in lines)
    body_size = size_counts.most_common(1)[0][0]
    heading_threshold = body_size + 2  # anything >2pt above body text is a heading candidate

    blocks: list[RawBlock] = []
    order_index_by_page: dict[int, int] = {}
    for line in lines:
        idx = order_index_by_page.get(line.page_number, 0)
        order_index_by_page[line.page_number] = idx + 1
        is_heading = round(line.avg_size) >= heading_threshold
        blocks.append(
            RawBlock(
                page_number=line.page_number,
                block_type="heading" if is_heading else "paragraph",
                text=line.text,
                image_ref=None,
                order_index=idx,
                font_size_hint=round(line.avg_size, 1),
            )
        )
    return blocks
