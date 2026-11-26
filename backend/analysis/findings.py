from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass
class Finding:
    code: str
    title: str
    detail: str
    # log-odds pushed toward "fake" (positive) or "genuine" (negative)
    weight: float

    @property
    def kind(self) -> str:
        if self.weight >= 0.35:
            return "bad"
        if self.weight <= -0.35:
            return "good"
        return "note"

    def to_dict(self):
        d = asdict(self)
        d["kind"] = self.kind
        return d


def combine(findings: list[Finding], prior: float = 0.0) -> float:
    """Percent chance the item is fake/edited. Clamped - we never claim certainty."""
    z = prior + sum(f.weight for f in findings)
    p = 1 / (1 + math.exp(-z))
    return round(min(97.0, max(3.0, p * 100)), 1)


def verdict(pct: float) -> tuple[str, str]:
    if pct >= 65:
        return "fake", "Likely fake or edited"
    if pct >= 35:
        return "unsure", "Needs a closer look"
    return "genuine", "Looks genuine"
