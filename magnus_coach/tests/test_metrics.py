import math

import torch

from src.model.encoding import SPEEDS, SPEED_TO_ID
from src.model.metrics import MetricAccumulator, batch_stats


def mask_of(n_legal, size=20):
    m = torch.zeros(size, dtype=torch.bool)
    m[:n_legal] = True
    return m


def test_uniform_model_has_perplexity_equal_to_number_of_legal_moves():
    logits = torch.zeros(1, 20)
    st = batch_stats(logits, mask_of(8)[None], torch.tensor([3]))
    assert math.isclose(st["nll"].item(), math.log(8), rel_tol=1e-5)


def test_rank_and_topk_and_mrr():
    logits = torch.tensor([[5.0, 4.0, 3.0, 2.0, 1.0] + [0.0] * 15])
    m = mask_of(5)[None]
    acc = MetricAccumulator()
    for tgt in (0, 2, 4):
        acc.update(logits, m, torch.tensor([tgt]), torch.tensor([0]), torch.tensor([0]))
    s = acc.overall
    assert s["n"] == 3 and abs(s["top1"] - 1 / 3) < 1e-9 and abs(s["top3"] - 2 / 3) < 1e-9
    assert abs(s["top5"] - 1.0) < 1e-9
    assert abs(s["mrr"] - (1 + 1 / 3 + 1 / 5) / 3) < 1e-6


def test_illegal_moves_never_beat_the_target_in_rank():
    logits = torch.zeros(1, 20)
    logits[0, 10] = 100.0                           # huge score on an ILLEGAL move
    st = batch_stats(logits, mask_of(5)[None], torch.tensor([0]))
    assert st["rank"].item() <= 5 and st["masked_legal"].item()


def test_raw_legal_rate_exposes_what_masking_hides():
    logits = torch.zeros(2, 20)
    logits[0, 10] = 9.0                             # raw argmax illegal
    logits[1, 1] = 9.0                              # raw argmax legal
    m = torch.stack([mask_of(5), mask_of(5)])
    acc = MetricAccumulator()
    acc.update(logits, m, torch.tensor([0, 1]), torch.tensor([0, 0]), torch.tensor([0, 1]))
    s = acc.overall
    assert s["raw_top1_legal_rate"] == 0.5 and s["masked_top1_legal_rate"] == 1.0


def test_groups_by_speed_and_color():
    logits = torch.zeros(4, 20)
    logits[torch.arange(4), torch.tensor([0, 0, 1, 1])] = 3.0
    m = mask_of(5)[None].repeat(4, 1)
    speeds = torch.tensor([SPEED_TO_ID["bullet"], SPEED_TO_ID["bullet"], SPEED_TO_ID["classical"], SPEED_TO_ID["unknown"]])
    colors = torch.tensor([0, 1, 0, 1])
    acc = MetricAccumulator()
    acc.update(logits, m, torch.tensor([0, 1, 1, 1]), speeds, colors)
    s = acc.summary()
    assert s["overall"]["n"] == 4 and s["speed/bullet"]["n"] == 2 and s["speed/classical"]["n"] == 1
    assert s["speed/bullet"]["top1"] == 0.5 and s["speed/classical"]["top1"] == 1.0
    assert s["color/white"]["n"] == 2 and s["color/black"]["n"] == 2
    assert "speed/rapid" not in s                    # empty groups are omitted, not reported as 0


def test_accumulation_across_batches_matches_single_batch():
    torch.manual_seed(0)
    logits, tgt = torch.randn(30, 20), torch.randint(0, 5, (30,))
    m = mask_of(5)[None].repeat(30, 1)
    sp, co = torch.randint(0, len(SPEEDS), (30,)), torch.randint(0, 2, (30,))
    a, b = MetricAccumulator(), MetricAccumulator()
    a.update(logits, m, tgt, sp, co)
    for i in range(0, 30, 7):
        b.update(logits[i:i + 7], m[i:i + 7], tgt[i:i + 7], sp[i:i + 7], co[i:i + 7])
    sa, sb = a.summary(), b.summary()
    for k in sa:
        for f in sa[k]:
            assert abs(sa[k][f] - sb[k][f]) < 1e-5, (k, f)
