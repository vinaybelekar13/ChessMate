"""Stub for a post-hoc check that generated coach text is actually grounded
in the source blocks it was given (ARCHITECTURE.md §6, §10).

Not implemented: a real version would run an NLI-style entailment check (or
a second LLM call asking "is every claim in X supported by Y, list any
that aren't") between the generated narration and the source blocks used to
produce it, and either strip/flag unsupported sentences or regenerate.
Prompting alone (see prompts.py) reduces but does not guarantee groundedness.
"""
from __future__ import annotations


def check_grounded(generated_text: str, source_texts: list[str]) -> list[str]:
    """Return a list of sentences in `generated_text` that are NOT supported
    by any of `source_texts`. Empty list = fully grounded (or check skipped).
    """
    raise NotImplementedError(
        "Wire up an entailment/groundedness check before relying on "
        "generated storytelling text in production."
    )
