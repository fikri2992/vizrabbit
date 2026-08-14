"""Defect taxonomy — categories and severities.

Extensible by design (domain-model.md), but frozen to this set for v1.
"""

from enum import StrEnum


class Category(StrEnum):
    ANATOMY = "anatomy"  # hands, faces, limbs
    PHYSICS = "physics"  # impossible actions, floating objects, wrong interactions
    ARTIFACT = "artifact"  # garbled text, warped patterns, melted edges
    BRAND = "brand"  # per-project guideline violations
    MEMORY = "memory"  # violations of promoted memory rules


class Severity(StrEnum):
    BLOCKER = "blocker"  # unpublishable
    WARNING = "warning"  # judgment call
    NITPICK = "nitpick"  # polish


#: Categories the built-in AI-slop guideline covers without any project guideline.
BUILT_IN_CATEGORIES: frozenset[Category] = frozenset(
    {Category.ANATOMY, Category.PHYSICS, Category.ARTIFACT}
)


def requires_project_rule(category: Category) -> bool:
    """BRAND and MEMORY defects must cite a project-scoped rule id."""
    return category not in BUILT_IN_CATEGORIES
