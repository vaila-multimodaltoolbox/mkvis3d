"""Per-source converters to kiki49 ``Sample`` objects.

Every source module exposes ``tasks(limit) -> list`` (picklable work items)
and ``process(task, opts) -> list[Sample | Reject | Tracking]`` so that the
builder can fan the work out over processes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

FIFA_ROOT = Path("/media/preto/Expansion/FIFA")
DATASET_ROOT = FIFA_ROOT / "dataset_vaila_fifa" / "sources"


@dataclass(frozen=True)
class Options:
    aux3d: bool = True  # label posts tops / net ground / flag tops when the camera is trusted
    tau: float = 0.35  # minimum line support for projected (not human-annotated) labels
    frames_dir: Path | None = None  # where decoded video frames are written


@dataclass
class Tracking:
    """Dense per-frame projections of one video (tracking benchmark)."""

    seq: str
    rows: list[list[float]] = field(default_factory=list)  # frame, then 49 x (x, y); NaN = absent


def hashed_split(group: str, val: float = 0.15, test: float = 0.15) -> str:
    """Deterministic split for sources without an official one (by group)."""
    u = int(hashlib.sha1(group.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if u < test else "val" if u < test + val else "train"
