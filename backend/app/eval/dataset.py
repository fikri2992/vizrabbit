"""The labelled eval set: ground-truth defects per image.

Labels are authored as grid cells against the same deterministic grid the pipeline
computes from the image's dimensions, so predictions and truth share a coordinate
system without storing pixel boxes.

    eval/labels.json
    [
      {"image": "hands_01.png", "defects": [
          {"cells": ["C4"], "category": "anatomy", "rule": "ANAT-01", "note": "six fingers"}
      ]},
      {"image": "clean_03.png", "defects": []}
    ]
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.taxonomy import Category


@dataclass(frozen=True)
class TruthDefect:
    cells: list[str]
    category: Category
    rule: str = ""
    note: str = ""


@dataclass(frozen=True)
class LabelledImage:
    image: str
    defects: list[TruthDefect] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """Clean images measure the false-positive rate — Gate 1 caps it at 1.0."""
        return not self.defects


def load_labels(path: str | Path) -> list[LabelledImage]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        LabelledImage(
            image=entry["image"],
            defects=[
                TruthDefect(
                    cells=[c.strip().upper() for c in defect["cells"]],
                    category=Category(defect["category"]),
                    rule=defect.get("rule", ""),
                    note=defect.get("note", ""),
                )
                for defect in entry.get("defects", [])
            ],
        )
        for entry in raw
    ]


def summarise(labels: list[LabelledImage]) -> dict[str, int]:
    """Composition of the eval set, so a thin set cannot masquerade as a good score."""
    counts = {"images": len(labels), "clean_images": 0, "defects": 0}
    for category in Category:
        counts[f"defects_{category.value}"] = 0

    for entry in labels:
        if entry.is_clean:
            counts["clean_images"] += 1
        counts["defects"] += len(entry.defects)
        for defect in entry.defects:
            counts[f"defects_{defect.category.value}"] += 1
    return counts
