"""Pure-Python tests for structure_detector.py — no DB, no external service.
Run with: pytest tests/test_curriculum_ordering.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ingestion.mineru_adapter import RawBlock
from app.ingestion.structure_detector import build_hierarchy, find_toc


def _toc_blocks():
    return [
        RawBlock(1, "heading", "Table of Contents", None, 0, 20.0),
        RawBlock(1, "paragraph", "Chapter 1: Weak Squares ..... 5", None, 1, 11.0),
        RawBlock(1, "paragraph", "Chapter 2: Outposts ..... 40", None, 2, 11.0),
        RawBlock(5, "heading", "Chapter 1: Weak Squares", None, 0, 24.0),
        RawBlock(40, "heading", "Chapter 2: Outposts", None, 0, 24.0),
    ]


def test_find_toc_parses_title_page_pairs():
    toc = find_toc(_toc_blocks())
    assert toc == [("Chapter 1: Weak Squares", 5), ("Chapter 2: Outposts", 40)]


def test_build_hierarchy_from_toc_orders_chapters_and_bounds_pages():
    chapters = build_hierarchy(_toc_blocks())
    assert [c.title for c in chapters] == ["Chapter 1: Weak Squares", "Chapter 2: Outposts"]
    assert chapters[0].start_page == 5
    assert chapters[0].end_page == 39  # bounded by the next chapter's start
    assert chapters[1].start_page == 40


def test_build_hierarchy_falls_back_to_font_sizes_without_toc():
    blocks = [
        RawBlock(1, "heading", "Chapter 1", None, 0, 24.0),
        RawBlock(1, "heading", "1.1 Introduction", None, 1, 16.0),
        RawBlock(2, "paragraph", "Some prose.", None, 0, 11.0),
        RawBlock(5, "heading", "1.2 Deeper", None, 0, 16.0),
        RawBlock(10, "heading", "Chapter 2", None, 0, 24.0),
    ]
    chapters = build_hierarchy(blocks)
    assert [c.title for c in chapters] == ["Chapter 1", "Chapter 2"]
    assert [s.title for s in chapters[0].children] == ["1.1 Introduction", "1.2 Deeper"]
    # curriculum order must never be reordered by anything semantic —
    # this just re-asserts the source order is preserved untouched.
    assert [s.order_index for s in chapters[0].children] == [0, 1]
