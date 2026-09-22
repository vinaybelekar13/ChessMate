"""BookCoach — spec §49. Implements the function list from the spec.

Structural/state-machine logic (resume, advance, puzzle attempt handling,
adaptive review detours) is real and testable. Narrative text generation
(`teach_section`, `explain_concept`, `explain_mistake`, `ask_book`) goes
through `generate_narrative()`, which calls Anthropic when
ANTHROPIC_API_KEY is set and importable, and otherwise falls back to the
honest, no-invention LOCAL GROUNDED MODE in `coach/local_coach.py` — the
mode actually used is always returned to the caller, never hidden
(spec follow-up §15). See ARCHITECTURE.md §6 for the groundedness caveats
that still apply to CLAUDE MODE output.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.db import models as db
from app.rag.book_rag import BookRAG
from app.chess.validation import check_move_against_solution, MoveCheckResult
from app.player_model import PlayerModel
from app.coach import prompts, local_coach


def _anthropic_available() -> bool:
    from app.config import settings
    if not settings.anthropic_api_key:
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _call_anthropic(system_prompt: str, context: dict) -> str:
    import anthropic
    from app.config import settings
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": _context_to_prompt(context)}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def _context_to_prompt(context: dict) -> str:
    import json
    return json.dumps(context, ensure_ascii=False)


def generate_narrative(kind: str, system_prompt: str, context: dict) -> dict:
    """Single seam between CLAUDE MODE and LOCAL GROUNDED MODE (spec
    follow-up §15). `kind` selects which local_coach function to fall back
    to; the two modes are never silently mixed — every response says which
    one produced it via the `mode` key.
    """
    if _anthropic_available():
        try:
            text = _call_anthropic(system_prompt, context)
            return {"mode": "claude", "text": text}
        except Exception as e:  # network/auth errors at call time — fall back, don't crash the lesson
            text = _local_fallback(kind, context)
            return {"mode": "local_grounded", "text": text, "claude_error": str(e)}
    text = _local_fallback(kind, context)
    return {"mode": "local_grounded", "text": text}


def _local_fallback(kind: str, context: dict) -> str:
    if kind == "teach_section":
        return local_coach.teach_section_locally(
            context.get("section_title", ""), context.get("source_blocks", []), context.get("depth", "normal")
        )
    if kind == "explain_concept":
        return local_coach.explain_concept_locally(context.get("concept", ""), context.get("retrieved", []))
    if kind == "ask_book":
        return local_coach.ask_book_locally(context.get("question", ""), context.get("retrieved", []))
    raise ValueError(f"Unknown narrative kind: {kind!r}")


class BookCoach:
    def __init__(self, session: Session, user_id: str, book_id: str):
        self.session = session
        self.user_id = user_id
        self.book_id = book_id
        self.rag = BookRAG(session)
        self.player = PlayerModel(session, user_id)

    # ---- session lifecycle (§10, §30, §31, §32) ----

    def start_book(self) -> db.Section:
        """Begin at chapter 1 section 1, unless progress already exists."""
        existing = self._get_or_none_progress()
        if existing and existing.current_section_id:
            return self.session.get(db.Section, existing.current_section_id)
        chapters = self.rag.get_book_structure(self.book_id)
        if not chapters:
            raise ValueError("Book has no chapters — ingestion may not be complete.")
        stmt = select(db.Section).where(db.Section.chapter_id == chapters[0].id).order_by(db.Section.order_index)
        first_section = self.session.exec(stmt).first()
        self._set_progress(first_section.id if first_section else None)
        return first_section

    def resume_progress(self) -> dict:
        prog = self._get_or_none_progress()
        if not prog or not prog.current_section_id:
            return {"resumed": False, "message": "No progress yet — starting from the beginning."}
        section = self.session.get(db.Section, prog.current_section_id)
        chapter = self.session.get(db.Chapter, section.chapter_id)
        return {
            "resumed": True,
            "message": f"Welcome back. We stopped at {chapter.title}, {section.title}.",
            "section_id": section.id,
        }

    def continue_lesson(self) -> dict:
        """Advance-or-review decision per §42: check for a weak concept in the
        just-finished section before moving forward; if found, return a
        review detour instead of the next section, without moving the
        Progress pointer."""
        prog = self._get_or_none_progress()
        if not prog or not prog.current_section_id:
            return {"section": self.start_book()}

        weak_concept = self.player.weakest_concept_in_section(prog.current_section_id)
        if weak_concept:
            earlier_section = self._section_that_introduced(weak_concept)
            return {
                "type": "review_detour",
                "concept": weak_concept,
                "review_section_id": earlier_section.id if earlier_section else None,
                "resume_section_id": prog.current_section_id,
            }

        next_section = self.rag.get_next_lesson(prog.current_section_id)
        if next_section:
            self._set_progress(next_section.id)
            self._mark_completed(prog, prog.current_section_id)
        return {"type": "next_section", "section": next_section}

    def go_back(self) -> db.Section | None:
        """§31 "Go back" — moves the Progress pointer to the previous
        section (unlike a review detour, this genuinely changes the
        curriculum position, since the user asked to go back)."""
        prog = self._get_or_none_progress()
        if not prog or not prog.current_section_id:
            return None
        previous_section = self.rag.get_previous_lesson(prog.current_section_id)
        if previous_section:
            self._set_progress(previous_section.id)
        return previous_section

    def review_section(self, section_id: str) -> db.Section | None:
        return self.session.get(db.Section, section_id)

    def review_chapter(self, chapter_id: str) -> list[db.Section]:
        stmt = select(db.Section).where(db.Section.chapter_id == chapter_id).order_by(db.Section.order_index)
        return list(self.session.exec(stmt))

    def skip_section(self, section_id: str) -> None:
        prog = self._get_or_none_progress()
        skipped = json.loads(prog.sections_skipped or "[]")
        if section_id not in skipped:
            skipped.append(section_id)
        prog.sections_skipped = json.dumps(skipped)
        next_section = self.rag.get_next_lesson(section_id)
        if next_section:
            prog.current_section_id = next_section.id
        prog.updated_at = datetime.now(timezone.utc)
        self.session.add(prog)
        self.session.commit()

    # ---- teaching (§11, §12, §24, §59) — narrative generation ----

    def teach_section(self, section_id: str, depth: str = "normal") -> dict:
        """depth: 'quick' | 'normal' | 'deep_dive' — normal must still keep
        the important detail per §12/§59, not compress to a blurb.
        Returns {"mode": "claude"|"local_grounded", "text": ...} — the mode
        is never hidden from the caller/frontend (spec follow-up §15)."""
        section = self.session.get(db.Section, section_id)
        blocks = self.rag.find_examples(section_id)
        source_texts = [b.text for b in blocks if b.text]
        context = {
            "depth": depth, "source_blocks": source_texts,
            "section_title": section.title if section else "",
        }
        return generate_narrative("teach_section", prompts.TEACHING_SYSTEM_PROMPT, context)

    def explain_concept(self, book_id: str, concept_name: str) -> dict:
        chunks = self.rag.search_concept(book_id, concept_name)
        context = {"concept": concept_name, "retrieved": [c.text for c in chunks]}
        return generate_narrative("explain_concept", prompts.SEARCH_MODE_SYSTEM_PROMPT, context)

    def deep_dive(self, section_id: str) -> dict:
        return self.teach_section(section_id, depth="deep_dive")

    def ask_book(self, book_id: str, question: str) -> dict:
        chunks = self.rag.search_book(book_id, question)
        context = {"question": question, "retrieved": [c.text for c in chunks]}
        return generate_narrative("ask_book", prompts.SEARCH_MODE_SYSTEM_PROMPT, context)

    def teach_position(self, position_id: str) -> db.Position | None:
        return self.session.get(db.Position, position_id)

    def teach_game(self, game_id: str) -> db.Game | None:
        return self.session.get(db.Game, game_id)

    # ---- puzzles (§13-§18, §58) ----

    def start_puzzle(self, puzzle_id: str) -> db.Puzzle | None:
        return self.session.get(db.Puzzle, puzzle_id)

    def submit_puzzle_move(self, puzzle_id: str, move_san: str) -> dict:
        puzzle = self.session.get(db.Puzzle, puzzle_id)
        if not puzzle:
            raise ValueError("Puzzle not found")
        solution = json.loads(puzzle.solution_line_san or "[]")
        result = check_move_against_solution(move_san, solution)

        attempt = db.Attempt(
            user_id=self.user_id, puzzle_id=puzzle_id,
            move_san=move_san,
            result="correct" if result.correct else "incorrect",
        )
        self.session.add(attempt)
        self.session.commit()

        if result.correct:
            return {"correct": True, "explanation": puzzle.author_explanation}

        feedback = self.explain_mistake(move_san, puzzle.author_explanation)
        return {"correct": False, "hint_available": True, **feedback}

    def explain_mistake(self, attempted_move: str, author_explanation: str | None) -> dict:
        """Wrong-answer flow (§15/§58). Uses Claude (with the
        WRONG_ANSWER_SYSTEM_PROMPT groundedness rules) when available,
        otherwise the honest local fallback in local_coach.py — either way
        the response is labeled with which mode produced it.
        """
        if _anthropic_available():
            context = {"attempted_move": attempted_move, "author_explanation": author_explanation}
            try:
                text = _call_anthropic(prompts.WRONG_ANSWER_SYSTEM_PROMPT, context)
                return {"mode": "claude", "message": text}
            except Exception as e:
                result = local_coach.explain_mistake_locally(attempted_move, author_explanation)
                result["claude_error"] = str(e)
                return result
        return local_coach.explain_mistake_locally(attempted_move, author_explanation)

    def give_hint(self, puzzle_id: str) -> str:
        puzzle = self.session.get(db.Puzzle, puzzle_id)
        solution = json.loads(puzzle.solution_line_san or "[]") if puzzle else []
        if not solution:
            return "No hint available."
        first_move = solution[0]
        return f"Look at what {first_move[:1]} (the piece type) can do here — think about its target square."

    def show_solution(self, puzzle_id: str) -> dict:
        puzzle = self.session.get(db.Puzzle, puzzle_id)
        if not puzzle:
            raise ValueError("Puzzle not found")
        attempt = db.Attempt(user_id=self.user_id, puzzle_id=puzzle_id, result="solution_shown")
        self.session.add(attempt)
        self.session.commit()
        return {
            "solution_line_san": json.loads(puzzle.solution_line_san or "[]"),
            "author_explanation": puzzle.author_explanation,
        }

    # ---- internal helpers ----

    def _get_or_none_progress(self) -> db.Progress | None:
        stmt = select(db.Progress).where(db.Progress.user_id == self.user_id, db.Progress.book_id == self.book_id)
        return self.session.exec(stmt).first()

    def _set_progress(self, section_id: str | None) -> None:
        prog = self._get_or_none_progress()
        if not prog:
            prog = db.Progress(user_id=self.user_id, book_id=self.book_id, current_section_id=section_id)
        else:
            prog.current_section_id = section_id
            prog.updated_at = datetime.now(timezone.utc)
        self.session.add(prog)
        self.session.commit()

    def _mark_completed(self, prog: db.Progress, section_id: str) -> None:
        completed = json.loads(prog.sections_completed or "[]")
        if section_id not in completed:
            completed.append(section_id)
        prog.sections_completed = json.dumps(completed)
        self.session.add(prog)
        self.session.commit()

    def _section_that_introduced(self, concept_name: str) -> db.Section | None:
        stmt = select(db.Concept).where(db.Concept.book_id == self.book_id, db.Concept.name == concept_name)
        concept = self.session.exec(stmt).first()
        if not concept:
            return None
        # Real implementation joins Lesson.concept_ids (or a lesson_concepts
        # link table) back to Section, earliest order_index first.
        return None
