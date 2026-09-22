"""LOCAL GROUNDED MODE: produces coach narration without any LLM call, for
when ANTHROPIC_API_KEY isn't set (spec follow-up §15 — the app must work
without API keys, and must never fabricate a fake Claude response).

This is deliberately unglamorous: it does not paraphrase, invent
transitions, or "understand" the text — it assembles the actual extracted
source text with minimal, fixed connective phrasing, and says so. That's
the honest trade-off of not calling an LLM: less storytelling polish, zero
invented content. When Claude mode is available (see book_coach.py), that
one *is* expected to add real narrative quality, subject to the
groundedness rules in coach/prompts.py.

Every function here is pure (text in, text out) and is exercised for real
in tests/test_local_coach.py.
"""
from __future__ import annotations


def teach_section_locally(section_title: str, source_texts: list[str], depth: str = "normal") -> str:
    if not source_texts:
        return (
            f"[LOCAL GROUNDED MODE] No extracted source text is available yet for "
            f"\"{section_title}\" — ingestion may still be running, or this section "
            f"had no recognizable paragraph/heading content."
        )

    if depth == "quick":
        source_texts = source_texts[:1]

    body = "\n\n".join(source_texts)
    return (
        f"[LOCAL GROUNDED MODE] Section: {section_title}\n\n"
        f"{body}\n\n"
        "(This is the book's own text, assembled without an LLM — connect an "
        "Anthropic API key for narrated, conversational teaching.)"
    )


def explain_concept_locally(concept_name: str, retrieved_texts: list[str]) -> str:
    if not retrieved_texts:
        return (
            f"[LOCAL GROUNDED MODE] Nothing in this book's indexed text matched "
            f"\"{concept_name}\" closely enough to quote from."
        )
    joined = "\n\n".join(f"- {t}" for t in retrieved_texts[:5])
    return f"[LOCAL GROUNDED MODE] Passages related to \"{concept_name}\":\n\n{joined}"


def ask_book_locally(question: str, retrieved_texts: list[str]) -> str:
    if not retrieved_texts:
        return (
            f"[LOCAL GROUNDED MODE] The book's local search index didn't return "
            f"anything for \"{question}\" — it may not cover this, or try "
            "different wording."
        )
    joined = "\n\n".join(f"- {t}" for t in retrieved_texts[:5])
    return (
        f"[LOCAL GROUNDED MODE] Passages the local search found for "
        f"\"{question}\":\n\n{joined}\n\n"
        "(Raw retrieved text, not a synthesized answer — connect an Anthropic "
        "API key for a narrated answer.)"
    )


def explain_mistake_locally(attempted_move: str, author_explanation: str | None) -> dict:
    """Wrong-answer feedback without an LLM: honest about what it can't do
    (it can't explain *why* a specific move is wrong without either an
    engine or an LLM reasoning over the position), but still uses the book's
    own explanation text when available rather than inventing one.
    """
    if author_explanation:
        return {
            "mode": "local_grounded",
            "message": (
                f"[LOCAL GROUNDED MODE] {attempted_move} wasn't the book's move here. "
                f"The book's own explanation for the actual solution: {author_explanation}"
            ),
        }
    return {
        "mode": "local_grounded",
        "message": (
            f"[LOCAL GROUNDED MODE] {attempted_move} wasn't the book's move here. "
            "This book doesn't have extracted explanation text for this puzzle, and "
            "local mode can't reason about *why* without an LLM or engine connected — "
            "try \"Show solution\" to see the book's actual line."
        ),
    }
