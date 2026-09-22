import json
from pathlib import Path

import chess
import pytest
import torch
import torch.nn.functional as F

from src.inference import predict as predict_mod
from src.inference.predict import MagnusPredictor
from src.model import (
    MagnusModel,
    MagnusModelConfig,
    describe,
    load_checkpoint,
    mask_logits,
    save_checkpoint,
    save_config_json,
)
from src.model.encoding import collate, encode_position
from src.model.magnus_model import ILLEGAL_LOGIT
from src.model.move_space import NUM_MOVES, legal_moves_with_indices

# A real, non-trivial middlegame (Two Knights, White to move) and a Black-to-move one.
FEN_WHITE = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
FEN_BLACK = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R b KQkq - 0 5"
STALEMATE = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"

CORPUS = Path(__file__).resolve().parents[1] / "data" / "cleaned" / "magnus_games.jsonl"


@pytest.fixture(scope="module")
def model():
    torch.manual_seed(0)
    return MagnusModel(MagnusModelConfig(d_model=32, n_layers=2, n_heads=4, d_ff=64, policy_dim=16)).eval()


def batch_of(*fens, **kw):
    return collate([encode_position(f, **kw) for f in fens])


# ------------------------------------------------------------------ config
def test_default_config_is_valid_and_cpu_sized():
    cfg = MagnusModelConfig().validate()
    assert cfg.sequence_length == 70 and cfg.num_moves == NUM_MOVES == 4162
    assert MagnusModel(cfg).parameter_count() < 1_000_000


def test_config_rejects_bad_values():
    with pytest.raises(ValueError):
        MagnusModelConfig(d_model=30, n_heads=4).validate()
    with pytest.raises(ValueError):
        MagnusModelConfig(dropout=1.0).validate()
    with pytest.raises(ValueError):
        MagnusModelConfig(n_layers=0).validate()


def test_config_rejects_stale_structural_constants():
    """A config written for a different move space / encoder must not load."""
    with pytest.raises(ValueError):
        MagnusModelConfig.from_dict({**MagnusModelConfig().to_dict(), "num_moves": 1851})
    with pytest.raises(ValueError):
        MagnusModelConfig.from_dict({**MagnusModelConfig().to_dict(), "encoding_version": "other"})


def test_config_json_roundtrip_and_is_self_describing(tmp_path):
    model = MagnusModel(MagnusModelConfig(d_model=32, n_layers=1, n_heads=2, d_ff=32, policy_dim=8))
    path = save_config_json(model.config, tmp_path / "model_config.json", model.parameter_count())
    raw = json.loads(path.read_text())
    assert raw["parameter_count"] == model.parameter_count()
    assert raw["output"]["logits"].endswith(f"[B, {NUM_MOVES}] raw move scores")
    assert "legal_move_masking" in raw and "speed" in raw["input"]["tensors"]
    assert MagnusModelConfig.load(path) == model.config


# ------------------------------------------------------------------ init
def test_initialization_counts_and_determinism():
    cfg = MagnusModelConfig(d_model=32, n_layers=2, n_heads=4, d_ff=64, policy_dim=16)
    torch.manual_seed(5)
    a = MagnusModel(cfg)
    torch.manual_seed(5)
    b = MagnusModel(cfg)
    assert a.parameter_count() == sum(p.numel() for p in a.parameters()) > 0
    for (na, pa), (nb, pb) in zip(a.state_dict().items(), b.state_dict().items()):
        assert na == nb and torch.equal(pa, pb)
    assert all(torch.isfinite(p).all() for p in a.parameters())


def test_underpromotion_bias_prior_applied():
    m = MagnusModel(MagnusModelConfig(d_model=32, n_layers=1, n_heads=2, d_ff=32, policy_dim=8))
    assert torch.allclose(m.underpromo_bias, torch.full((3,), -2.0))


# ------------------------------------------------------------------ forward / shape
@pytest.mark.parametrize("bsize", [1, 3, 16])
def test_forward_output_shape_and_finite(model, bsize):
    batch = batch_of(*([FEN_WHITE, FEN_BLACK, chess.STARTING_FEN] * 6)[:bsize])
    logits = model.forward_batch(batch)
    assert logits.shape == (bsize, NUM_MOVES) and logits.dtype == torch.float32
    assert torch.isfinite(logits).all()


def test_forward_positional_signature_matches_batch_call(model):
    b = batch_of(FEN_WHITE)
    assert torch.equal(model(b["squares"], b["history_from"], b["history_to"], b["speed"], b["ep"], b["numeric"]),
                       model.forward_batch(b))


def test_batch_result_equals_single_results(model):
    fens = [FEN_WHITE, FEN_BLACK, chess.STARTING_FEN]
    together = model.forward_batch(batch_of(*fens))
    for i, f in enumerate(fens):
        assert torch.allclose(together[i], model.forward_batch(batch_of(f))[0], atol=1e-5)


def test_backward_reaches_every_parameter():
    torch.manual_seed(1)
    m = MagnusModel(MagnusModelConfig(d_model=32, n_layers=2, n_heads=4, d_ff=64, policy_dim=16)).train()
    fens = [FEN_WHITE, FEN_BLACK, chess.STARTING_FEN, "1n5k/P7/8/8/8/8/8/K7 w - - 0 1"]
    b = batch_of(*fens, history_uci=["e2e4", "e7e5"], time_control="180+0")
    targets = torch.tensor([legal_moves_with_indices(chess.Board(f))[0][0] for f in fens])
    loss = F.cross_entropy(m.masked_logits(b), targets)
    loss.backward()
    assert torch.isfinite(loss)
    missing = [n for n, p in m.named_parameters() if p.grad is None or not torch.isfinite(p.grad).all()]
    assert not missing, missing


def test_time_control_changes_the_output(model):
    """Time control is a real input, not decoration."""
    bullet = model.forward_batch(batch_of(FEN_WHITE, time_control="60+0"))
    classical = model.forward_batch(batch_of(FEN_WHITE, time_control="1800+0"))
    unknown = model.forward_batch(batch_of(FEN_WHITE))
    assert not torch.allclose(bullet, classical, atol=1e-6)
    assert not torch.allclose(bullet, unknown, atol=1e-6)


def test_history_changes_the_output(model):
    a = model.forward_batch(batch_of(FEN_WHITE, history_uci=["e2e4", "e7e5", "g1f3"]))
    b = model.forward_batch(batch_of(FEN_WHITE))
    assert not torch.allclose(a, b, atol=1e-6)


# ------------------------------------------------------------------ legal masking
def test_probs_sum_to_one_and_illegal_moves_get_exactly_zero(model):
    b = batch_of(FEN_WHITE, FEN_BLACK, chess.STARTING_FEN, "1n5k/P7/8/8/8/8/8/K7 w - - 0 1")
    p = model.probs(b)
    assert torch.allclose(p.sum(1), torch.ones(4), atol=1e-5)
    assert (p[~b["legal_mask"]] == 0).all()
    assert (p[b["legal_mask"]] > 0).all()
    assert torch.equal((p > 0), b["legal_mask"])


def test_argmax_is_always_legal_even_if_illegal_logits_are_enormous():
    """Adversarial: give every illegal move a huge logit; masking must win."""
    b = batch_of(FEN_WHITE, FEN_BLACK, chess.STARTING_FEN)
    logits = torch.randn(3, NUM_MOVES)
    logits[~b["legal_mask"]] += 1e6
    masked = mask_logits(logits, b["legal_mask"])
    assert b["legal_mask"].gather(1, masked.argmax(1, keepdim=True)).all()
    assert (masked[~b["legal_mask"]] == ILLEGAL_LOGIT).all()


def test_learned_bias_on_illegal_move_cannot_make_it_predictable():
    m = MagnusModel(MagnusModelConfig(d_model=32, n_layers=1, n_heads=2, d_ff=32, policy_dim=8)).eval()
    a1h8 = chess.A1 * 64 + chess.H8  # illegal from the start position
    with torch.no_grad():
        m.pair_bias.view(-1)[a1h8] = 1e4
    b = batch_of(chess.STARTING_FEN)
    assert m.forward_batch(b)[0].argmax().item() == a1h8   # raw logits DO prefer it...
    p = m.probs(b)[0]
    assert p[a1h8] == 0 and b["legal_mask"][0][p.argmax()]  # ...masked output never does


def test_position_with_no_legal_moves_raises(model):
    b = batch_of(STALEMATE)
    assert not b["legal_mask"].any()
    with pytest.raises(ValueError):
        model.probs(b)


def test_mask_shape_mismatch_raises():
    with pytest.raises(ValueError):
        mask_logits(torch.zeros(2, NUM_MOVES), torch.ones(NUM_MOVES, dtype=torch.bool))


def test_masked_cross_entropy_is_finite_and_uses_only_legal_moves(model):
    b = batch_of(FEN_WHITE)
    target = torch.tensor([legal_moves_with_indices(chess.Board(FEN_WHITE))[0][0]])
    loss = F.cross_entropy(model.masked_logits(b), target)
    assert torch.isfinite(loss)
    # a uniform model over n legal moves has loss ln(n); random init should be near it
    n = int(b["legal_mask"].sum())
    assert abs(loss.item() - torch.log(torch.tensor(float(n))).item()) < 1.5


# ------------------------------------------------------------------ checkpoints
def test_checkpoint_roundtrip_gives_identical_outputs(tmp_path, model):
    path = save_checkpoint(model, tmp_path / "ckpt.pt", meta={"trained_steps": 0, "note": "unit test"})
    loaded, meta = load_checkpoint(path)
    assert meta["note"] == "unit test" and meta["trained_steps"] == 0
    assert loaded.config == model.config and not loaded.training
    b = batch_of(FEN_WHITE, FEN_BLACK, time_control="180+2")
    assert torch.equal(model.forward_batch(b), loaded.forward_batch(b))
    for (k1, v1), (k2, v2) in zip(model.state_dict().items(), loaded.state_dict().items()):
        assert k1 == k2 and torch.equal(v1, v2)


def test_checkpoint_saves_optimizer_state_for_resume(tmp_path, model):
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    path = save_checkpoint(model, tmp_path / "c.pt", optimizer=opt)
    payload = torch.load(path, weights_only=True)
    assert "optimizer_state" in payload and payload["parameter_count"] == model.parameter_count()


def test_checkpoint_with_incompatible_move_space_is_rejected(tmp_path, model):
    path = save_checkpoint(model, tmp_path / "c.pt")
    payload = torch.load(path, weights_only=True)
    payload["config"]["num_moves"] = 1851
    torch.save(payload, tmp_path / "bad.pt")
    with pytest.raises(ValueError):
        load_checkpoint(tmp_path / "bad.pt")


def test_checkpoint_with_unknown_format_is_rejected(tmp_path, model):
    payload = torch.load(save_checkpoint(model, tmp_path / "c.pt"), weights_only=True)
    payload["checkpoint_format"] = 99
    torch.save(payload, tmp_path / "bad.pt")
    with pytest.raises(ValueError):
        load_checkpoint(tmp_path / "bad.pt")


# ------------------------------------------------------------------ inference on real FENs
@pytest.mark.parametrize("fen", [FEN_WHITE, FEN_BLACK, chess.STARTING_FEN])
def test_inference_on_real_fen_returns_ranked_legal_moves(model, fen):
    board = chess.Board(fen)
    legal = {m.uci() for m in board.legal_moves}
    out = MagnusPredictor(model).predict(fen, top_k=5, time_control="180+0", history_uci=["e2e4"])
    assert len(out) == 5
    probs = [o["probability"] for o in out]
    assert probs == sorted(probs, reverse=True) and all(0 < p <= 1 for p in probs)
    for o in out:
        assert o["uci"] in legal
        assert board.san(chess.Move.from_uci(o["uci"])) == o["san"]


def test_inference_top_k_larger_than_legal_count_returns_all_legal(model):
    out = MagnusPredictor(model).predict(chess.STARTING_FEN, top_k=500)
    assert len(out) == 20
    assert abs(sum(o["probability"] for o in out) - 1.0) < 1e-4


def test_inference_covers_promotions_and_underpromotions(model):
    fen = "1n5k/P7/8/8/8/8/8/K7 w - - 0 1"
    board = chess.Board(fen)
    out = MagnusPredictor(model).predict(fen, top_k=500)
    assert {o["uci"] for o in out} == {m.uci() for m in board.legal_moves}
    assert any(o["uci"].endswith("n") for o in out)  # knight underpromotion is scoreable


def test_inference_rejects_position_without_moves(model):
    with pytest.raises(ValueError):
        MagnusPredictor(model).predict(STALEMATE)


def test_predictor_reports_untrained_status(tmp_path, model):
    save_checkpoint(model, tmp_path / "u.pt", meta={"trained_steps": 0})
    assert MagnusPredictor.from_checkpoint(tmp_path / "u.pt").is_trained is False
    save_checkpoint(model, tmp_path / "t.pt", meta={"trained_steps": 10})
    assert MagnusPredictor.from_checkpoint(tmp_path / "t.pt").is_trained is True


def test_missing_checkpoint_fails_loudly_not_silently(tmp_path):
    with pytest.raises(FileNotFoundError):
        MagnusPredictor.from_checkpoint(tmp_path / "nope.pt")


def test_predict_magnus_moves_spec_api(monkeypatch, model):
    monkeypatch.setattr(predict_mod, "_default", MagnusPredictor(model))
    out = predict_mod.predict_magnus_moves(FEN_WHITE, top_k=3)
    assert len(out) == 3 and set(out[0]) == {"uci", "san", "probability"}


# ------------------------------------------------------------------ real corpus (read-only)
@pytest.mark.skipif(not CORPUS.exists(), reason="corpus not present")
def test_real_magnus_target_moves_are_always_scoreable():
    """Every historical Magnus move in a corpus sample maps into the move space
    and is legal, including moves that rarely/never occur as targets."""
    checked = 0
    with open(CORPUS, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh):
            if line_no % 40:  # every 40th game keeps this fast
                continue
            g = json.loads(line)
            board = chess.Board(g["start_fen"])
            for uci in g["moves"]:
                mv = chess.Move.from_uci(uci)
                is_magnus = (board.turn == chess.WHITE) == (g["magnus_color"] == "white")
                if is_magnus:
                    mask = encode_position(board)["legal_mask"]
                    from src.model.move_space import move_to_index
                    assert mask[move_to_index(mv, board.turn)], (g["game_id"], uci)
                    checked += 1
                board.push(mv)
    assert checked > 10_000
