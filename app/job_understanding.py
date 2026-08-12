from __future__ import annotations

from typing import Any

from app.scoring_config import (
    JOB_ANALYSIS_VERSION,
    TIER_WEIGHTS,
    clamp_tier_weight,
    default_tier_weight,
)


TIER_KEYS = (
    "must_have",
    "core_skills",
    "supporting_skills",
    "differentials",
    "soft_skills",
)

TIER_BY_LIST_KEY = {
    "must_have": "MUST_HAVE",
    "core_skills": "CORE",
    "supporting_skills": "SUPPORTING",
    "differentials": "DIFFERENTIAL",
    "soft_skills": "SOFT",
}

# Skills typically critical for integration-architect style roles when migrating v1→v2.
CRITICAL_NAME_HINTS = (
    "oracle integration cloud",
    "oic",
    "arquitetura de integracao",
    "arquitetura de integração",
)


def empty_job_analysis() -> dict[str, Any]:
    return {
        "version": JOB_ANALYSIS_VERSION,
        "role_intent": "",
        "must_have": [],
        "core_skills": [],
        "supporting_skills": [],
        "differentials": [],
        "soft_skills": [],
        "role_expectations": "",
        "context_signals": [],
        "skill_groups": [],
        # Backward-compatible flat lists
        "hard_skills": [],
        "desired_skills": [],
    }


def normalize_job_analysis(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        result = {}
    return _clean_job_analysis(result)


def _clean_job_analysis(result: dict[str, Any]) -> dict[str, Any]:
    cleaned = empty_job_analysis()
    cleaned["role_intent"] = str(result.get("role_intent") or "").strip()[:2000]
    cleaned["role_expectations"] = str(result.get("role_expectations") or "").strip()[:2000]
    cleaned["context_signals"] = _clean_string_list(result.get("context_signals"))
    cleaned["skill_groups"] = _clean_skill_groups(result.get("skill_groups"))

    has_tiered = any(
        isinstance(result.get(key), list) and result.get(key)
        for key in ("must_have", "core_skills", "supporting_skills", "differentials")
    )

    if has_tiered:
        for key, tier in TIER_BY_LIST_KEY.items():
            cleaned[key] = _clean_tiered_items(result.get(key), tier)
    else:
        # Migrate flat v1 hard/soft/desired → tiered structure.
        hard = _clean_weighted_items_legacy(result.get("hard_skills", []))
        soft = _clean_weighted_items_legacy(result.get("soft_skills", []))
        desired = _clean_weighted_items_legacy(result.get("desired_skills", []))
        cleaned.update(_migrate_flat_to_tiers(hard, soft, desired))

    # Soft skills may also arrive only under soft_skills in tiered responses.
    if not cleaned["soft_skills"]:
        cleaned["soft_skills"] = _clean_tiered_items(result.get("soft_skills"), "SOFT")

    _sync_flat_lists(cleaned)
    return cleaned


def _migrate_flat_to_tiers(
    hard: list[dict[str, Any]],
    soft: list[dict[str, Any]],
    desired: list[dict[str, Any]],
) -> dict[str, Any]:
    must_have: list[dict[str, Any]] = []
    core: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []

    for item in hard:
        name = str(item["name"])
        weight = int(item.get("weight", 4))
        name_l = name.lower()
        if weight >= 5 or any(hint in name_l for hint in CRITICAL_NAME_HINTS):
            must_have.append(_as_tier_item(name, "MUST_HAVE", weight=TIER_WEIGHTS["MUST_HAVE"], group=item.get("group")))
        elif weight >= 3:
            core.append(_as_tier_item(name, "CORE", weight=TIER_WEIGHTS["CORE"], group=item.get("group")))
        else:
            supporting.append(
                _as_tier_item(name, "SUPPORTING", weight=TIER_WEIGHTS["SUPPORTING"], group=item.get("group"))
            )

    # Ensure at least one must-have when hard skills exist (promote first core).
    if not must_have and core:
        promoted = dict(core[0])
        promoted["tier"] = "MUST_HAVE"
        promoted["weight"] = TIER_WEIGHTS["MUST_HAVE"]
        must_have.append(promoted)
        core = core[1:]

    differentials = [
        _as_tier_item(str(item["name"]), "DIFFERENTIAL", weight=TIER_WEIGHTS["DIFFERENTIAL"], group=item.get("group"))
        for item in desired
    ]
    soft_skills = [
        _as_tier_item(str(item["name"]), "SOFT", weight=min(5, max(1, int(item.get("weight", 3)))), group=item.get("group"))
        for item in soft
    ]
    return {
        "must_have": must_have,
        "core_skills": core,
        "supporting_skills": supporting,
        "differentials": differentials,
        "soft_skills": soft_skills,
    }


def _sync_flat_lists(analysis: dict[str, Any]) -> None:
    """Keep hard_skills / desired_skills in sync for v1 consumers."""
    hard: list[dict[str, Any]] = []
    for key in ("must_have", "core_skills", "supporting_skills"):
        for item in analysis.get(key) or []:
            hard.append(
                {
                    "name": item["name"],
                    "weight": _v1_weight_from_tier(item.get("tier"), item.get("weight")),
                    "tier": item.get("tier"),
                    "group": item.get("group") or "",
                }
            )
    analysis["hard_skills"] = hard
    analysis["desired_skills"] = [
        {
            "name": item["name"],
            "weight": _v1_weight_from_tier("DIFFERENTIAL", item.get("weight")),
            "tier": "DIFFERENTIAL",
            "group": item.get("group") or "",
        }
        for item in (analysis.get("differentials") or [])
    ]
    # soft_skills already present; ensure flat-compatible weight 1–5
    analysis["soft_skills"] = [
        {
            "name": item["name"],
            "weight": max(1, min(5, int(item.get("weight") or 3))),
            "tier": "SOFT",
            "group": item.get("group") or "",
        }
        for item in (analysis.get("soft_skills") or [])
    ]


def _v1_weight_from_tier(tier: Any, weight: Any) -> int:
    """Map tier weights (1–10) to legacy 1–5 scale for v1 scoring."""
    tier_key = str(tier or "").upper()
    try:
        raw = int(float(weight))
    except (TypeError, ValueError):
        raw = default_tier_weight(tier_key)
    if tier_key == "MUST_HAVE":
        return 5
    if tier_key == "CORE":
        return 4
    if tier_key == "SUPPORTING":
        return 3
    if tier_key == "DIFFERENTIAL":
        return 2
    return max(1, min(5, raw))


def _as_tier_item(name: str, tier: str, *, weight: Any = None, group: Any = None) -> dict[str, Any]:
    return {
        "name": str(name)[:80],
        "tier": tier,
        "weight": clamp_tier_weight(tier, weight if weight is not None else default_tier_weight(tier)),
        "group": str(group or "").strip()[:80],
    }


def _clean_tiered_items(items: Any, default_tier: str) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return cleaned
    for item in items:
        if isinstance(item, str) and item.strip():
            cleaned.append(_as_tier_item(item.strip(), default_tier))
            continue
        if not isinstance(item, dict) or not item.get("name"):
            continue
        tier = str(item.get("tier") or default_tier).upper()
        if tier not in TIER_WEIGHTS:
            tier = default_tier
        cleaned.append(
            _as_tier_item(
                str(item["name"]),
                tier,
                weight=item.get("weight"),
                group=item.get("group") or item.get("skill_group"),
            )
        )
    return cleaned


def _clean_weighted_items_legacy(items: Any) -> list[dict[str, Any]]:
    cleaned = []
    if not isinstance(items, list):
        return cleaned
    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        weight = item.get("weight", 1)
        try:
            weight = int(weight)
        except (TypeError, ValueError):
            weight = 1
        cleaned.append(
            {
                "name": str(item["name"])[:80],
                "weight": max(1, min(5, weight)),
                "group": str(item.get("group") or "").strip()[:80],
            }
        )
    return cleaned


def _clean_string_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text:
            out.append(text[:240])
    return out[:20]


def _clean_skill_groups(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    groups: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("group") or "").strip()
        if not name:
            continue
        skills_raw = item.get("skills") or item.get("members") or []
        skills: list[str] = []
        if isinstance(skills_raw, list):
            for skill in skills_raw:
                label = str(skill or "").strip()
                if label:
                    skills.append(label[:80])
        groups.append({"name": name[:80], "skills": skills[:30]})
    return groups[:20]


def flatten_skills_v2(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten tiered analysis into skill rows with category + tier + weight."""
    mapping = [
        ("must_have", "Must-have", "MUST_HAVE"),
        ("core_skills", "Core skill", "CORE"),
        ("supporting_skills", "Supporting skill", "SUPPORTING"),
        ("differentials", "Differential", "DIFFERENTIAL"),
        ("soft_skills", "Soft skill", "SOFT"),
    ]
    skills: list[dict[str, Any]] = []
    for key, category, tier in mapping:
        for item in analysis.get(key) or []:
            skills.append(
                {
                    "category": category,
                    "name": item["name"],
                    "weight": int(item.get("weight") or default_tier_weight(tier)),
                    "tier": item.get("tier") or tier,
                    "group": item.get("group") or "",
                }
            )
    return skills


def skill_group_index(analysis: dict[str, Any]) -> dict[str, str]:
    """Map skill name (lower) → group name from skill_groups and per-skill group."""
    index: dict[str, str] = {}
    for group in analysis.get("skill_groups") or []:
        group_name = str(group.get("name") or "")
        for skill in group.get("skills") or []:
            index[str(skill).lower()] = group_name
    for skill in flatten_skills_v2(analysis):
        name = str(skill["name"]).lower()
        if skill.get("group") and name not in index:
            index[name] = str(skill["group"])
    return index
