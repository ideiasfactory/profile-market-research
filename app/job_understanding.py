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


def normalize_job_analysis(
    result: dict[str, Any] | None,
    *,
    policy: str | None = None,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        result = {}
    resolved = (policy or result.get("weight_policy") or "v2")
    resolved = "v3" if str(resolved).strip().lower() == "v3" else "v2"
    cleaned = _clean_job_analysis(result, policy=resolved)
    cleaned["weight_policy"] = resolved
    for key in ("llm_provider", "llm_model", "audit", "analyzed_at", "analysis_version", "prompt_set", "prompt_files"):
        if result.get(key) is not None:
            cleaned[key] = result[key]
    return cleaned


def normalize_stored_job_analysis(result: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize persisted job analysis using its stored weight_policy."""
    return normalize_job_analysis(result)


def _skill_name_key(name: Any) -> str:
    return " ".join(str(name or "").strip().lower().split())


def flatten_skill_snapshot(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Lightweight snapshot of tiered skills for audit / weight-policy prompts."""
    return [
        {
            "name": item["name"],
            "tier": item.get("tier") or "",
            "weight": int(item.get("weight") or default_tier_weight(str(item.get("tier") or ""))),
            "group": item.get("group") or "",
        }
        for item in flatten_skills_v2(analysis)
    ]


def normalize_weight_policy(
    result: dict[str, Any] | None,
    *,
    baseline: dict[str, Any],
    policy: str = "v3",
) -> dict[str, Any]:
    """Apply OpenAI (or other) weight recalibration without inventing skills.

    - Only skills present in ``baseline`` are kept.
    - Skills omitted by the LLM keep baseline tier/weight/group.
    - Tier moves are allowed; weights are clamped with the given policy ranges.
    - Metadata (role_intent, skill_groups, …) is preserved from baseline.
    """
    base = normalize_job_analysis(baseline)
    allowed: dict[str, dict[str, Any]] = {}
    for item in flatten_skills_v2(base):
        key = _skill_name_key(item["name"])
        if key and key not in allowed:
            allowed[key] = {
                "name": item["name"],
                "tier": str(item.get("tier") or "CORE").upper(),
                "weight": int(item.get("weight") or default_tier_weight(str(item.get("tier") or "CORE"))),
                "group": item.get("group") or "",
            }

    updated: dict[str, dict[str, Any]] = {key: dict(value) for key, value in allowed.items()}
    raw = result if isinstance(result, dict) else {}
    for list_key, default_tier in TIER_BY_LIST_KEY.items():
        items = raw.get(list_key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str) and item.strip():
                name = item.strip()
                weight = None
                group = None
                tier = default_tier
            elif isinstance(item, dict) and item.get("name"):
                name = str(item["name"]).strip()
                weight = item.get("weight")
                group = item.get("group") or item.get("skill_group")
                tier = str(item.get("tier") or default_tier).upper()
            else:
                continue
            key = _skill_name_key(name)
            if key not in allowed:
                continue
            if tier not in TIER_WEIGHTS:
                tier = default_tier
            canonical = allowed[key]["name"]
            group_text = str(group).strip()[:80] if group is not None else allowed[key]["group"]
            updated[key] = {
                "name": canonical,
                "tier": tier,
                "weight": clamp_tier_weight(
                    tier,
                    weight if weight is not None else allowed[key]["weight"],
                    policy=policy,
                ),
                "group": group_text or allowed[key]["group"],
            }

    cleaned = empty_job_analysis()
    cleaned["role_intent"] = base.get("role_intent") or ""
    cleaned["role_expectations"] = base.get("role_expectations") or ""
    cleaned["context_signals"] = list(base.get("context_signals") or [])
    cleaned["skill_groups"] = list(base.get("skill_groups") or [])
    cleaned["analysis_version"] = base.get("analysis_version") or base.get("version") or JOB_ANALYSIS_VERSION

    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in TIER_KEYS}
    list_by_tier = {tier: key for key, tier in TIER_BY_LIST_KEY.items()}
    for key in allowed:
        item = updated[key]
        tier = str(item.get("tier") or "CORE").upper()
        if tier not in TIER_WEIGHTS:
            tier = "CORE"
        item["tier"] = tier
        item["weight"] = clamp_tier_weight(tier, item.get("weight"), policy=policy)
        buckets[list_by_tier[tier]].append(
            {
                "name": item["name"],
                "tier": tier,
                "weight": item["weight"],
                "group": item.get("group") or "",
            }
        )

    for key in TIER_KEYS:
        cleaned[key] = buckets[key]
    soft_v3 = list(buckets["soft_skills"])
    _sync_flat_lists(cleaned)
    # _sync_flat_lists clamps soft to 1–5 for v1; restore wider v3 soft weights for scoring.
    if (policy or "").strip().lower() == "v3":
        cleaned["soft_skills"] = soft_v3
    return cleaned


def _clean_job_analysis(result: dict[str, Any], *, policy: str = "v2") -> dict[str, Any]:
    cleaned = empty_job_analysis()
    cleaned["role_intent"] = str(result.get("role_intent") or "").strip()[:2000]
    cleaned["role_expectations"] = str(result.get("role_expectations") or "").strip()[:2000]
    cleaned["context_signals"] = _clean_string_list(result.get("context_signals"))
    cleaned["skill_groups"] = _clean_skill_groups(result.get("skill_groups"))
    weight_policy = "v3" if (policy or "").strip().lower() == "v3" else "v2"

    has_tiered = any(
        isinstance(result.get(key), list) and result.get(key)
        for key in ("must_have", "core_skills", "supporting_skills", "differentials")
    )

    if has_tiered:
        for key, tier in TIER_BY_LIST_KEY.items():
            cleaned[key] = _clean_tiered_items(result.get(key), tier, policy=weight_policy)
    else:
        # Migrate flat v1 hard/soft/desired → tiered structure.
        hard = _clean_weighted_items_legacy(result.get("hard_skills", []))
        soft = _clean_weighted_items_legacy(result.get("soft_skills", []))
        desired = _clean_weighted_items_legacy(result.get("desired_skills", []))
        cleaned.update(_migrate_flat_to_tiers(hard, soft, desired, policy=weight_policy))

    # Soft skills may also arrive only under soft_skills in tiered responses.
    if not cleaned["soft_skills"]:
        cleaned["soft_skills"] = _clean_tiered_items(result.get("soft_skills"), "SOFT", policy=weight_policy)

    soft_v3 = list(cleaned["soft_skills"]) if weight_policy == "v3" else None
    _sync_flat_lists(cleaned)
    if soft_v3 is not None:
        cleaned["soft_skills"] = soft_v3
    return cleaned


def _migrate_flat_to_tiers(
    hard: list[dict[str, Any]],
    soft: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    *,
    policy: str = "v2",
) -> dict[str, Any]:
    must_have: list[dict[str, Any]] = []
    core: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []

    for item in hard:
        name = str(item["name"])
        weight = int(item.get("weight", 4))
        name_l = name.lower()
        if weight >= 5 or any(hint in name_l for hint in CRITICAL_NAME_HINTS):
            must_have.append(
                _as_tier_item(name, "MUST_HAVE", weight=TIER_WEIGHTS["MUST_HAVE"], group=item.get("group"), policy=policy)
            )
        elif weight >= 3:
            core.append(
                _as_tier_item(name, "CORE", weight=TIER_WEIGHTS["CORE"], group=item.get("group"), policy=policy)
            )
        else:
            supporting.append(
                _as_tier_item(
                    name, "SUPPORTING", weight=TIER_WEIGHTS["SUPPORTING"], group=item.get("group"), policy=policy
                )
            )

    # Ensure at least one must-have when hard skills exist (promote first core).
    if not must_have and core:
        promoted = dict(core[0])
        promoted["tier"] = "MUST_HAVE"
        promoted["weight"] = clamp_tier_weight("MUST_HAVE", TIER_WEIGHTS["MUST_HAVE"], policy=policy)
        must_have.append(promoted)
        core = core[1:]

    differentials = [
        _as_tier_item(
            str(item["name"]),
            "DIFFERENTIAL",
            weight=TIER_WEIGHTS["DIFFERENTIAL"],
            group=item.get("group"),
            policy=policy,
        )
        for item in desired
    ]
    soft_skills = [
        _as_tier_item(
            str(item["name"]),
            "SOFT",
            weight=min(5, max(1, int(item.get("weight", 3)))),
            group=item.get("group"),
            policy=policy,
        )
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


def _as_tier_item(
    name: str,
    tier: str,
    *,
    weight: Any = None,
    group: Any = None,
    policy: str = "v2",
) -> dict[str, Any]:
    return {
        "name": str(name)[:80],
        "tier": tier,
        "weight": clamp_tier_weight(
            tier,
            weight if weight is not None else default_tier_weight(tier),
            policy=policy,
        ),
        "group": str(group or "").strip()[:80],
    }


def _clean_tiered_items(items: Any, default_tier: str, *, policy: str = "v2") -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return cleaned
    for item in items:
        if isinstance(item, str) and item.strip():
            cleaned.append(_as_tier_item(item.strip(), default_tier, policy=policy))
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
                policy=policy,
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
