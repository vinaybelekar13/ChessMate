"""MinerU adapter — primary PDF parser (spec §7A, §45).

UNTESTED: could not be installed in the build sandbox (no package-allowlist
access). Written against MinerU's documented CLI/output format as of the
spec's reference (https://github.com/opendatalab/MinerU) — verify the exact
output schema against whatever version you actually install, it has changed
across releases.

Responsibility: turn one PDF into an ordered list of RawBlock objects with
page number, bounding box, block type, and text/image ref. Nothing here
decides chapters/sections — that's structure_detector.py.
"""
from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawBlock:
    page_number: int
    block_type: str  # "paragraph" | "heading" | "caption" | "diagram" | "table"
    text: str | None
    image_ref: str | None
    order_index: int
    font_size_hint: float | None = None  # used by structure_detector for heading levels


class MinerUError(RuntimeError):
    pass


def parse(pdf_path: str, output_dir: str) -> list[RawBlock]:
    """Run MinerU over `pdf_path`, return ordered RawBlocks.

    Real implementation sketch (MinerU CLI mode):

        magic-pdf -p {pdf_path} -o {output_dir} -m auto

    MinerU writes a `*_content_list.json` (block-level, reading-order) and a
    `*_middle.json` (layout with bboxes/font info) into `output_dir`. Parse
    the content-list for text/type/page, and cross-reference `middle.json`
    for font-size hints. This function currently raises so it's never
    silently treated as working — replace with the real subprocess call once
    MinerU is actually installed and you've inspected its output on a real
    PDF from your target book(s).
    """
    from app.config import settings  # imported lazily so RawBlock stays usable
    # standalone (e.g. in tests) without pulling in pydantic-settings.

    if settings.mineru_mode == "cli":
        raise MinerUError(
            "MinerU CLI not wired up — install MinerU, run it once by hand on "
            "a sample PDF, inspect the *_content_list.json it produces, then "
            "fill in the subprocess call + JSON mapping here."
        )
    raise MinerUError(f"Unsupported MINERU_MODE={settings.mineru_mode!r}")


def _example_of_expected_shape() -> list[RawBlock]:
    """Not called anywhere — documents the shape structure_detector.py expects."""
    return [
        RawBlock(page_number=1, block_type="heading", text="Chapter 1: Weak Squares",
                  image_ref=None, order_index=0, font_size_hint=24.0),
        RawBlock(page_number=1, block_type="paragraph", text="A weak square is one that...",
                  image_ref=None, order_index=1, font_size_hint=11.0),
        RawBlock(page_number=3, block_type="diagram", text="Diagram 1.1",
                  image_ref="pages/p3_img0.png", order_index=0, font_size_hint=None),
    ]
