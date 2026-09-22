"""Write data/splits/split_manifest.json from the validated corpus.

Run:  python src/data/make_splits.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.splits import build_manifest  # noqa: E402

CORPUS = ROOT / "data" / "cleaned" / "magnus_games.jsonl"
MANIFEST = ROOT / "data" / "splits" / "split_manifest.json"

if __name__ == "__main__":
    manifest = build_manifest(CORPUS)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print("games per split:", manifest["games_per_split"])
    print("expected positions per split:", manifest["expected_positions_per_split"])
    print("wrote", MANIFEST)
