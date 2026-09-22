"""Tests the local (pdfplumber) PDF fallback against a real PDF file — this
actually opens and parses a file on disk, unlike the MinerU/Docling adapter
tests (which can't run at all without those packages installed).

Also locks in two structure_detector bugs found by running this for real:
1. A one-off larger heading (a book/part title) being misclassified as the
   sole "chapter" level, with the real chapters demoted to "sections".
2. A section/chapter's end_page going below its own start_page when two
   headings of the same level land on the same page.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ingestion import local_pdf_adapter, structure_detector, chess_extractor

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_book.pdf")


def test_local_pdf_adapter_extracts_real_text_and_headings():
    blocks = local_pdf_adapter.parse(FIXTURE)
    assert len(blocks) > 5
    headings = [b for b in blocks if b.block_type == "heading"]
    assert any("Chapter 1" in (b.text or "") for b in headings)
    assert any("Chapter 2" in (b.text or "") for b in headings)
    # body prose should NOT be classified as a heading
    prose = [b for b in blocks if b.block_type == "paragraph"]
    assert any("weak square" in (b.text or "").lower() for b in prose)


def test_structure_detector_does_not_confuse_book_title_with_a_chapter():
    blocks = local_pdf_adapter.parse(FIXTURE)
    hierarchy = structure_detector.build_hierarchy(blocks)
    titles = [c.title for c in hierarchy]
    assert "Chapter 1: Weak Squares" in titles
    assert "Chapter 2: Outposts" in titles
    # the book title itself must not appear as a chapter
    assert not any("Synthetic Chess Primer" in t for t in titles)


def test_structure_detector_sections_nest_correctly_and_pages_stay_sane():
    blocks = local_pdf_adapter.parse(FIXTURE)
    hierarchy = structure_detector.build_hierarchy(blocks)
    chapter1 = next(c for c in hierarchy if c.title.startswith("Chapter 1"))
    section_titles = [s.title for s in chapter1.children]
    assert "1.1 Understanding weak squares" in section_titles
    assert "1.2 Exploiting weak squares" in section_titles
    for s in chapter1.children:
        assert s.end_page >= s.start_page  # regression: used to go negative-relative


def test_end_to_end_puzzle_and_move_detection_on_real_pdf():
    blocks = local_pdf_adapter.parse(FIXTURE)
    puzzles = chess_extractor.find_puzzle_candidates(blocks)
    assert len(puzzles) == 2  # "White to move." and "Exercise 1: Black to move."
    move_blocks = chess_extractor.find_move_text_blocks(blocks)
    assert len(move_blocks) == 1
    assert "Nf3" in move_blocks[0].text
