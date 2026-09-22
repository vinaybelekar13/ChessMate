"""Knowledge / RAG interface (Phase 26).

Every item MUST carry provenance; items without it are rejected. The seed
file contains short generic concept definitions authored for this project
(not book text). Future books/resources plug in through `KnowledgeSource`;
nothing here fabricates quotations.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KB_DIR = ROOT / "data" / "knowledge"
TOPICS = ("tactic", "opening", "strategy", "endgame", "method")


@dataclass(frozen=True)
class KnowledgeItem:
    id: str
    topic: str
    title: str
    text: str
    tags: tuple
    provenance: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tags"] = list(self.tags)
        return d


class KnowledgeSource(ABC):
    @abstractmethod
    def search(self, query: str = "", tags: Iterable[str] = (), topic: Optional[str] = None, k: int = 3) -> List[KnowledgeItem]: ...

    @abstractmethod
    def get(self, item_id: str) -> Optional[KnowledgeItem]: ...


def _validate(raw: dict, origin: str) -> KnowledgeItem:
    for f in ("id", "topic", "title", "text", "tags", "provenance"):
        if f not in raw or raw[f] in (None, "", [], {}):
            raise ValueError(f"{origin}: knowledge item missing required field {f!r} (provenance is mandatory)")
    if raw["topic"] not in TOPICS:
        raise ValueError(f"{origin}: unknown topic {raw['topic']!r}")
    if not isinstance(raw["provenance"], dict) or not raw["provenance"].get("type"):
        raise ValueError(f"{origin}: provenance must be an object with a 'type'")
    return KnowledgeItem(raw["id"], raw["topic"], raw["title"], raw["text"], tuple(raw["tags"]), raw["provenance"])


class LocalKnowledgeBase(KnowledgeSource):
    def __init__(self, directory=DEFAULT_KB_DIR):
        self.items: Dict[str, KnowledgeItem] = {}
        for f in sorted(Path(directory).glob("*.json")):
            for raw in json.loads(f.read_text(encoding="utf-8"))["items"]:
                it = _validate(raw, f.name)
                if it.id in self.items:
                    raise ValueError(f"duplicate knowledge id {it.id}")
                self.items[it.id] = it

    def get(self, item_id):
        return self.items.get(item_id)

    def search(self, query="", tags=(), topic=None, k=3):
        toks = set(re.findall(r"[a-z_]+", query.lower()))
        tags = set(tags)
        scored = []
        for it in self.items.values():
            if topic and it.topic != topic:
                continue
            s = 3 * len(tags & set(it.tags)) + sum(1 for t in toks if t in it.title.lower() or t in it.text.lower() or t in it.tags)
            if s > 0:
                scored.append((-s, it.id, it))
        scored.sort(key=lambda x: (x[0], x[1]))
        return [x[2] for x in scored[:k]]

    def for_concept(self, concept_key: Optional[str], k: int = 1) -> List[KnowledgeItem]:
        """Items for a coach concept key such as 'hanging_piece', 'missed_back_rank_mate' or 'opening'."""
        if not concept_key:
            return []
        base = concept_key[len("missed_"):] if concept_key.startswith("missed_") else concept_key
        return self.search(tags=[base], k=k)
