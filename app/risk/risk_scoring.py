"""Deterministic risk scoring for ChangeGuard AI.

This module converts change signals into a normalized risk score and label
using stable, explainable rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from app.analyzers.test_gap_detector import GapAnalysis
from app.collectors.git_diff_collector import ChangedFileStat

RISK_LEVELS = (
    (60, "High"),
    (30, "Medium"),
    (0, "Low"),
)

CATEGORY_WEIGHTS: Mapping[str, int] = {
    "payments": 20,
    "infrastructure": 20,
    "auth": 15,
    "database": 15,
    "api": 10,
    "config": 10,
    "tests": 0,
}


@dataclass(frozen=True)
class RiskScore:
    """Represents the deterministic risk score and its contributing factors.

    Attributes:
        score: Normalized risk score from 0 to 100.
        level: Human-readable risk label.
        factors: Ordered list of score contributors.
        breakdown: Category-wise score breakdown for transparency.
    """

    score: int
    level: str
    factors: list[str]
    breakdown: dict[str, int]


def _sum_changed_lines(changes: Iterable[ChangedFileStat]) -> int:
    total = 0
    for change in changes:
        if change.added is None or change.removed is None:
            continue
        total += change.added + change.removed
    return total


def _size_score(total_lines: int) -> int:
    if total_lines <= 0:
        return 0
    if total_lines < 10:
        return 5
    if total_lines < 50:
        return 10
    if total_lines < 100:
        return 15
    if total_lines < 200:
        return 20
    if total_lines < 300:
        return 30
    return 40


def _file_count_score(file_count: int) -> int:
    if file_count <= 1:
        return 0
    if file_count <= 3:
        return 5
    if file_count <= 7:
        return 10
    return 15


def _category_score(categories: Iterable[str]) -> tuple[int, list[str], dict[str, int]]:
    factors: list[str] = []
    breakdown: dict[str, int] = {}
    total = 0
    for category in sorted(set(categories)):
        weight = CATEGORY_WEIGHTS.get(category, 0)
        if weight <= 0:
            continue
        total += weight
        breakdown[category] = weight
        factors.append(f"Category '{category}' (+{weight})")
    return total, factors, breakdown


def _label_for_score(score: int) -> str:
    for threshold, label in RISK_LEVELS:
        if score >= threshold:
            return label
    return "Low"


def calculate_risk_score(
    changes: Iterable[ChangedFileStat],
    category_matches: Mapping[str, Iterable[str]],
    test_gap: GapAnalysis,
) -> RiskScore:
    """Calculate the deterministic risk score for a change set.

    Args:
        changes: Iterable of per-file change statistics.
        category_matches: Mapping of category name to matching files.
        test_gap: Test gap analysis results.

    Returns:
        RiskScore: Normalized score and its contributing factors.
    """
    total_lines = _sum_changed_lines(changes)
    file_count = len({change.path for change in changes})

    factors: list[str] = []
    breakdown: dict[str, int] = {}

    size_points = _size_score(total_lines)
    if size_points:
        factors.append(f"Lines changed ({total_lines}) (+{size_points})")
        breakdown["size"] = size_points

    file_points = _file_count_score(file_count)
    if file_points:
        factors.append(f"Files touched ({file_count}) (+{file_points})")
        breakdown["files"] = file_points

    category_points, category_factors, category_breakdown = _category_score(
        category_matches.keys()
    )
    factors.extend(category_factors)
    breakdown.update(category_breakdown)

    test_points = 15 if test_gap.missing_tests else 0
    if test_points:
        factors.append("Missing tests (+15)")
        breakdown["missing_tests"] = test_points

    high_risk_categories = {"payments", "infrastructure", "database", "auth"}
    if test_gap.missing_tests and high_risk_categories.intersection(
        category_matches.keys()
    ):
        factors.append("Untested high-risk domain (+10)")
        breakdown["untested_domain"] = 10
        test_points += 10

    raw_score = size_points + file_points + category_points + test_points
    score = min(raw_score, 100)

    level = _label_for_score(score)

    return RiskScore(
        score=score,
        level=level,
        factors=factors,
        breakdown=breakdown,
    )
