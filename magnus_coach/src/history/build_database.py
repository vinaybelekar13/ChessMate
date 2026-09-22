"""Build data/magnus_history.sqlite:  python -m src.history.build_database"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.history.database import DEFAULT_DB, build  # noqa: E402

if __name__ == "__main__":
    stats = build(ROOT / "data/cleaned/magnus_games.jsonl", ROOT / "data/splits", ROOT / "data/splits/split_manifest.json", DEFAULT_DB)
    (ROOT / "outputs" / "database_report.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
