"""Generates tests/fixtures/sample_book.pdf — a small, synthetic PDF that
looks structurally like a chess book: a title, two chapters each with two
sections, some prose, one puzzle prompt, and one line of PGN-style move
text. Used by test_local_pdf_adapter.py and the end-to-end smoke test to
actually exercise the ingestion pipeline against a real PDF file, per the
brief's requirement not to just claim things work.

Run directly to (re)generate the fixture:
    python3 tests/fixtures/generate_test_pdf.py
"""
import os
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

OUT_PATH = os.path.join(os.path.dirname(__file__), "sample_book.pdf")


def build(path: str = OUT_PATH) -> str:
    c = canvas.Canvas(path, pagesize=LETTER)
    width, height = LETTER

    def line(text, size, y, font="Helvetica"):
        c.setFont(font, size)
        c.drawString(72, y, text)

    # Page 1: title + chapter 1 heading
    line("The Synthetic Chess Primer", 24, height - 100)
    line("Chapter 1: Weak Squares", 20, height - 160)
    line("1.1 Understanding weak squares", 14, height - 200)
    line("A weak square is a square that can no longer be defended by a pawn.", 11, height - 230)
    line("Once such a square exists, a piece that occupies it is very hard to remove.", 11, height - 250)
    c.showPage()

    # Page 2: section 1.2 + puzzle
    line("1.2 Exploiting weak squares", 14, height - 100)
    line("The knight is the ideal piece to occupy a weak square, since it cannot", 11, height - 130)
    line("be challenged by an enemy pawn once it lands there.", 11, height - 150)
    line("White to move. Find the best move.", 12, height - 190)
    line("Diagram 1.1", 10, height - 210)
    c.showPage()

    # Page 3: Chapter 2 heading + a model game
    line("Chapter 2: Outposts", 20, height - 100)
    line("2.1 The model game", 14, height - 140)
    line("The following game shows the outpost idea in a full practical example.", 11, height - 170)
    line("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7", 11, height - 200)
    line("2.2 Exercises", 14, height - 240)
    line("Exercise 1: Black to move. Find the continuation.", 12, height - 270)
    c.showPage()

    c.save()
    return path


if __name__ == "__main__":
    p = build()
    print(f"Wrote {p}")
