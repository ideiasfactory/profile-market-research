from __future__ import annotations

import os
from typing import Any


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# Skill tier default weights (LLM recommends; user may edit; finals persist).
TIER_WEIGHTS: dict[str, int] = {
    "MUST_HAVE": int(_env_float("TIER_WEIGHT_MUST_HAVE", 10)),
    "CORE": int(_env_float("TIER_WEIGHT_CORE", 7)),
    "SUPPORTING": int(_env_float("TIER_WEIGHT_SUPPORTING", 3)),
    "DIFFERENTIAL": int(_env_float("TIER_WEIGHT_DIFFERENTIAL", 2)),
    "SOFT": int(_env_float("TIER_WEIGHT_SOFT", 3)),
}

TIER_WEIGHT_RANGES: dict[str, tuple[int, int]] = {
    "MUST_HAVE": (8, 10),
    "CORE": (6, 7),
    "SUPPORTING": (2, 3),
    "DIFFERENTIAL": (1, 2),
    "SOFT": (1, 5),
}

# Wider ranges for scoring model v3 (OpenAI weight recalibration).
TIER_WEIGHT_RANGES_V3: dict[str, tuple[int, int]] = {
    "MUST_HAVE": (7, 10),
    "CORE": (4, 9),
    "SUPPORTING": (2, 6),
    "DIFFERENTIAL": (1, 4),
    "SOFT": (1, 6),
}

# Composite dimension weights (must sum ~1.0).
DIMENSION_WEIGHTS: dict[str, float] = {
    "core_technical_fit": _env_float("WEIGHT_CORE_TECHNICAL", 0.45),
    "role_fit": _env_float("WEIGHT_ROLE_FIT", 0.20),
    "context_fit": _env_float("WEIGHT_CONTEXT_FIT", 0.15),
    "behavioral_fit": _env_float("WEIGHT_BEHAVIORAL", 0.10),
    "differentials": _env_float("WEIGHT_DIFFERENTIALS", 0.10),
}

# Verdict thresholds (final_score 0–100).
VERDICT_THRESHOLDS: dict[str, float] = {
    "strong_fit": _env_float("VERDICT_STRONG_FIT", 85),
    "recommended": _env_float("VERDICT_RECOMMENDED", 70),
    "evaluate": _env_float("VERDICT_EVALUATE", 50),
}

# Must-have considered covered when score >= this (0–5 scale).
MUST_HAVE_COVERED_MIN_SCORE = int(_env_float("MUST_HAVE_COVERED_MIN_SCORE", 3))

# If True, any critical must-have gap forces not_recommended.
AUTO_ELIMINATE_ON_CRITICAL_GAP = _env_bool("AUTO_ELIMINATE_ON_CRITICAL_GAP", False)

# Scoring model: v1 = flat; v2 = hierarchical; v3 = hierarchical + OpenAI weight policy.
SCORING_MODEL = (os.getenv("SCORING_MODEL") or "v2").strip().lower()
if SCORING_MODEL not in {"v1", "v2", "v3"}:
    SCORING_MODEL = "v2"

JOB_ANALYSIS_VERSION = 2
PROMPT_VERSIONS: dict[str, str] = {
    "analyse_job": "v2",
    "score_skills": "v2",
    "score_fit": "v1",
    "score_narrative": "v2",
    "score_weights": "v1",
}

EVIDENCE_STATUSES = frozenset(
    {"explicit", "inferred", "not_found", "negative", "needs_validation"}
)

# Known platform non-equivalence pairs (for grounding / anti-hallucination).
NON_EQUIVALENT_SKILL_HINTS: list[tuple[str, str]] = [
    ("oracle integration cloud", "sap cpi"),
    ("oracle integration cloud", "integration suite"),
    ("oracle integration cloud", "sap integration suite"),
    ("oic", "cpi"),
    ("oracle cloud infrastructure", "sap btp"),
    ("oci", "btp"),
]


def active_scoring_model(override: str | None = None) -> str:
    if override and override.strip().lower() in {"v1", "v2", "v3"}:
        return override.strip().lower()
    return SCORING_MODEL


def normalize_dimension_weights(weights: dict[str, float] | None = None) -> dict[str, float]:
    source = dict(weights or DIMENSION_WEIGHTS)
    total = sum(max(0.0, float(value)) for value in source.values())
    if total <= 0:
        return dict(DIMENSION_WEIGHTS)
    return {key: max(0.0, float(value)) / total for key, value in source.items()}


def default_tier_weight(tier: str) -> int:
    key = (tier or "").upper()
    return int(TIER_WEIGHTS.get(key, 3))


def tier_weight_ranges(policy: str = "v2") -> dict[str, tuple[int, int]]:
    if (policy or "").strip().lower() == "v3":
        return TIER_WEIGHT_RANGES_V3
    return TIER_WEIGHT_RANGES


def clamp_tier_weight(tier: str, weight: Any, *, policy: str = "v2") -> int:
    key = (tier or "").upper()
    ranges = tier_weight_ranges(policy)
    low, high = ranges.get(key, (1, 10))
    try:
        value = int(float(weight))
    except (TypeError, ValueError):
        value = default_tier_weight(key)
    return max(low, min(high, value))
