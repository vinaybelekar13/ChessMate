import json

import chess
import pytest

from src.coach import llm as L
from src.coach.evidence import generate_coach_evidence
from src.coach.knowledge import LocalKnowledgeBase, _validate
from src.coach.services import Services
from src.engine.stockfish import engine_available
from src.history.database import DEFAULT_DB

NEEDS = pytest.mark.skipif(not (engine_available() and DEFAULT_DB.exists()), reason="needs Stockfish + database")
NXE5 = ("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", "Nxe5")
MATE = ("6k1/5ppp/8/8/8/8/5PPP/R3K3 w - - 0 1", "Kd2")
GOOD = ("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", "d3")


# ---------------------------------------------------------------- knowledge (no engine needed)
def test_seed_knowledge_loads_and_every_item_has_provenance():
    kb = LocalKnowledgeBase()
    assert len(kb.items) >= 15
    for it in kb.items.values():
        assert it.provenance["type"] and it.provenance["author"] and it.text


def test_items_without_provenance_are_rejected(tmp_path):
    good = {"id": "x", "topic": "tactic", "title": "t", "text": "t", "tags": ["a"], "provenance": {"type": "authored"}}
    assert _validate(good, "t").id == "x"
    for bad in ({**good, "provenance": None}, {**good, "provenance": {}}, {k: v for k, v in good.items() if k != "provenance"},
                {**good, "topic": "gossip"}, {**good, "text": ""}):
        with pytest.raises(ValueError):
            _validate(bad, "t")
    (tmp_path / "a.json").write_text(json.dumps({"items": [good, good]}))
    with pytest.raises(ValueError):
        LocalKnowledgeBase(tmp_path)


def test_search_is_deterministic_and_concept_mapping():
    kb = LocalKnowledgeBase()
    assert [i.id for i in kb.search("pin king")] == [i.id for i in kb.search("pin king")]
    assert kb.for_concept("hanging_piece")[0].id == "hanging_piece"
    assert kb.for_concept("missed_back_rank_mate")[0].id == "back_rank"
    assert kb.for_concept("opening")[0].topic == "opening" and kb.for_concept(None) == [] and kb.for_concept("zzz") == []


# ---------------------------------------------------------------- grounding verifier (synthetic evidence)
def fake_ev(with_history=True):
    b = chess.Board()
    ev = {"position": {"fen": b.fen(), "legal_moves_uci": []},
          "comparison": {"engine": {"evaluation_delta_cp": -120, "evaluation_before": {"value_cp": 30, "mate": None},
                                    "evaluation_after_user_move": {"value_cp": -90, "mate": None},
                                    "top_lines": [{"move_san": "e4", "pv_san": ["e4", "e5", "Nf3"], "score": {"value_cp": 30, "mate": None}}],
                                    "best_move": {"san": "e4", "uci": "e2e4"}, "principal_variation_after_user_move_san": ["e5"],
                                    "opponent_best_reply": None},
                       "historical": {"examples": [{"surrounding_moves": [{"san": "d4"}], "historical_move": {"san": "d4"}}] if with_history else []}}}
    return ev


def test_verifier_accepts_supported_text_and_flags_each_kind_of_hallucination():
    ev = fake_ev()
    ok = "You should play e4 or Nf3; the engine says 30 centipawns before and -90 centipawns after. Magnus played d4 here."
    assert L.verify_grounding(ok, ev)["grounded"]
    assert L.verify_grounding("Try Qh5 next.", ev)["unsupported_moves"] == ["Qh5"]
    assert L.verify_grounding("The engine gives +250 centipawns.", ev)["unsupported_numbers"] == [250]
    assert L.verify_grounding("There is mate in 4.", ev)["unsupported_mates"] == [4]
    r = L.verify_grounding("Magnus played d4 in a famous game.", fake_ev(with_history=False))
    assert r["magnus_claim_without_evidence"] and not r["grounded"]
    assert L.verify_grounding("Nobody can stop O-O-O", ev)["unsupported_moves"] == ["O-O-O"]      # castling checked too
    assert L.verify_grounding("You could play h5 here", ev)["unsupported_moves"] == ["h5"]       # bare pawn push after a move verb
    assert L.verify_grounding("the piece on h5 is loose", ev)["grounded"]                        # a bare square is not a move


# ---------------------------------------------------------------- providers / CoachLLM
class Bad(L.LLMProvider):
    name = "bad"
    def generate(self, system, payload):
        return "Just play Qh8 and win 900 centipawns with mate in 9. Magnus never lost."


class Boom(L.LLMProvider):
    name = "boom"
    def generate(self, system, payload):
        raise RuntimeError("network down")


@NEEDS
class TestWithRealEvidence:
    @pytest.fixture(scope="class")
    def evs(self):
        s = Services(engine_depth=8)
        out = [generate_coach_evidence(*NXE5, s), generate_coach_evidence(*MATE, s), generate_coach_evidence(*GOOD, s)]
        yield out
        s.close()

    def test_template_output_passes_its_own_verifier_for_every_evidence(self, evs):
        kb = LocalKnowledgeBase()
        for ev in evs:
            for mode in ("analysis", "why_wrong", "why_good", "socratic"):
                r = L.CoachLLM().explain(ev, mode, knowledge=kb.for_concept(ev["concept_key"]))
                assert r["grounding"]["grounded"], (mode, r["grounding"], r["text"])
                assert r["provider"] == "template" and r["is_llm"] is False and not r["fallback_used"]

    def test_hallucinating_provider_is_rejected_and_replaced(self, evs):
        r = L.CoachLLM(Bad()).explain(evs[0])
        assert r["fallback_used"] and r["provider"] == "template" and r["grounding"]["grounded"]
        rej = r["rejected_output_grounding"]
        assert "Qh8" in rej["unsupported_moves"] and rej["unsupported_numbers"] == [900] and rej["unsupported_mates"] == [9]
        assert "Qh8" not in r["text"]

    def test_provider_failure_falls_back_with_error_recorded(self, evs):
        r = L.CoachLLM(Boom()).explain(evs[0])
        assert r["fallback_used"] and "network down" in r["provider_error"] and r["grounding"]["grounded"]

    def test_anthropic_provider_without_key_falls_back(self, evs, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = L.CoachLLM(L.AnthropicProvider()).explain(evs[0])
        assert r["fallback_used"] and "ANTHROPIC_API_KEY" in r["provider_error"]

    def test_good_custom_provider_output_is_accepted(self, evs):
        ev = evs[0]
        best = ev["comparison"]["engine"]["best_move"]["san"]

        class Ok(L.LLMProvider):
            name = "ok"
            def generate(self, system, payload):
                return f"The engine prefers {best}; think about which of your pieces is left undefended."
        r = L.CoachLLM(Ok()).explain(ev)
        assert not r["fallback_used"] and r["provider"] == "ok" and r["grounding"]["grounded"]

    def test_payload_contains_only_evidence_and_is_json(self, evs):
        p = L.build_llm_payload(evs[0], [{"concept": "hanging_piece", "count": 2}], "analysis")
        json.dumps(p)
        assert set(p) == {"mode", "position", "user_move", "classification", "engine_truth", "magnus_model", "historical_evidence",
                          "tactical_findings", "consequence_chain", "player_weaknesses", "knowledge"}
        assert "private thoughts" in L.SYSTEM_PROMPT and "evaluation as something Magnus thought" in L.SYSTEM_PROMPT

    def test_template_keeps_sources_separate_and_admits_no_history(self, evs):
        r = L.CoachLLM().explain(evs[1])
        assert "MAGNUS MODEL (imitation of historical choices, not move quality)" in r["text"]
        assert "HISTORICAL MAGNUS EVIDENCE" in r["text"] and "STRONGER ALTERNATIVE (engine)" in r["text"]
