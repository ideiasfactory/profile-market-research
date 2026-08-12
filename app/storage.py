from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DATA_DIR = Path("data")
CANDIDATES_DIR = DATA_DIR / "candidates"
SCORES_DIR = DATA_DIR / "scores"

CANDIDATE_INDEX_KEYS = (
    "id",
    "name",
    "city",
    "reported_role",
    "source_type",
    "source_label",
    "source_url",
    "path",
    "created_at",
    "updated_at",
)

SCORE_INDEX_KEYS = (
    "id",
    "job_id",
    "candidate_id",
    "job_title",
    "candidate_name",
    "final_score",
    "verdict_label",
    "method",
    "scoring_model_version",
    "llm_provider",
    "llm_model",
    "created_at",
    "path",
)

SCORE_HISTORY_INDEX_KEYS = (
    "id",
    "score_id",
    "job_id",
    "candidate_id",
    "job_title",
    "candidate_name",
    "final_score",
    "verdict_label",
    "method",
    "scoring_model_version",
    "llm_provider",
    "llm_model",
    "created_at",
    "archived_at",
    "estimated_cost_usd",
    "total_tokens",
    "path",
)

SCORES_HISTORY_DIR = SCORES_DIR / "history"


DEFAULT_DOMAINS = {
    "profiles": [
        {"id": "backend", "name": "Backend"},
        {"id": "frontend", "name": "Frontend"},
        {"id": "fullstack", "name": "Full Stack"},
        {"id": "data", "name": "Dados"},
        {"id": "devops", "name": "DevOps"},
    ],
    "seniorities": [
        {"id": "junior", "name": "Júnior"},
        {"id": "pleno", "name": "Pleno"},
        {"id": "senior", "name": "Sênior"},
        {"id": "lead", "name": "Lead"},
    ],
}


class JsonStore:
    def __init__(self, path: Path, default: Any):
        self.path = path
        self.default = default
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write(default)

    def read(self) -> Any:
        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def write(self, data: Any) -> None:
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)


def slugify(name: str, max_len: int = 48) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    if not text:
        text = "candidate"
    return text[:max_len].rstrip("_") or "candidate"


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


class CandidateStore:
    """Index in candidates.json + full profiles under data/candidates/."""

    def __init__(self, index_path: Path, profiles_dir: Path):
        self.index_path = index_path
        self.profiles_dir = profiles_dir
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            _write_json(self.index_path, [])
        self.migrate()

    def read(self) -> list[dict[str, Any]]:
        """Return lightweight index entries (no resume_text)."""
        data = _read_json(self.index_path)
        return data if isinstance(data, list) else []

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        index = find_by_id(self.read(), candidate_id)
        if not index:
            return None
        path = self._resolve_path(index)
        if path.exists():
            profile = _read_json(path)
            if isinstance(profile, dict):
                return {**index, **profile, "path": index.get("path") or self._relative_path(path)}
        return dict(index)

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = self.read()
        if not payload.get("id"):
            payload["id"] = new_id()

        existing = find_by_id(items, payload["id"])
        slug = slugify(str(payload.get("name") or ""))
        if existing and existing.get("path"):
            rel_path = existing["path"]
            path = DATA_DIR / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)
        else:
            filename = f"{payload['id']}_{slug}_profile.json"
            path = self.profiles_dir / filename
            rel_path = self._relative_path(path)

        profile = {
            "id": payload["id"],
            "name": payload.get("name", ""),
            "city": payload.get("city", ""),
            "reported_role": payload.get("reported_role", ""),
            "resume_text": payload.get("resume_text", ""),
            "source_type": payload.get("source_type", ""),
            "source_label": payload.get("source_label", ""),
            "source_url": payload.get("source_url", ""),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }
        _write_json(path, profile)

        index_entry = {
            "id": profile["id"],
            "name": profile["name"],
            "city": profile["city"],
            "reported_role": profile["reported_role"],
            "source_type": profile["source_type"],
            "source_label": profile["source_label"],
            "source_url": profile["source_url"],
            "path": rel_path,
            "created_at": profile["created_at"],
            "updated_at": profile["updated_at"],
        }

        if existing is None:
            items.append(index_entry)
        else:
            existing.clear()
            existing.update(index_entry)
        _write_json(self.index_path, items)
        return {**index_entry, **profile}

    def migrate(self) -> None:
        raw = _read_json(self.index_path)
        if not isinstance(raw, list) or not raw:
            return

        changed = False
        index: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict) or not item.get("id"):
                continue

            needs_split = "resume_text" in item or not item.get("path")
            path = self._resolve_path(item) if item.get("path") else None
            if path is None or not path.exists():
                needs_split = True

            if needs_split:
                slug = slugify(str(item.get("name") or ""))
                filename = f"{item['id']}_{slug}_profile.json"
                path = self.profiles_dir / filename
                rel_path = self._relative_path(path)

                if path.exists() and "resume_text" not in item:
                    profile = _read_json(path)
                else:
                    profile = {
                        "id": item["id"],
                        "name": item.get("name", ""),
                        "city": item.get("city", ""),
                        "reported_role": item.get("reported_role", ""),
                        "resume_text": item.get("resume_text", ""),
                        "source_type": item.get("source_type", ""),
                        "source_label": item.get("source_label", ""),
                        "source_url": item.get("source_url", ""),
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at"),
                    }
                    if path.exists():
                        existing_profile = _read_json(path)
                        if isinstance(existing_profile, dict) and existing_profile.get("resume_text") and not profile.get(
                            "resume_text"
                        ):
                            profile["resume_text"] = existing_profile["resume_text"]
                    _write_json(path, profile)

                index_entry = {
                    "id": item["id"],
                    "name": item.get("name", ""),
                    "city": item.get("city", ""),
                    "reported_role": item.get("reported_role", ""),
                    "source_type": item.get("source_type", ""),
                    "source_label": item.get("source_label", ""),
                    "source_url": item.get("source_url", ""),
                    "path": rel_path,
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                }
                index.append(index_entry)
                changed = True
            else:
                index.append({key: item.get(key) for key in CANDIDATE_INDEX_KEYS})

        if changed:
            _write_json(self.index_path, index)

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(DATA_DIR))
        except ValueError:
            return str(path)

    def _resolve_path(self, entry: dict[str, Any]) -> Path:
        rel = str(entry.get("path") or "")
        path = Path(rel)
        if path.is_absolute():
            return path
        # Paths are stored relative to data/ (e.g. candidates/foo.json)
        return DATA_DIR / path


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _history_stamp(iso_ts: str | None) -> str:
    """Compact UTC stamp for history filenames/ids (e.g. 20260812T183448Z)."""
    raw = (iso_ts or "").strip()
    if raw:
        try:
            normalized = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y%m%dT%H%M%SZ")
        except ValueError:
            pass
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _provider_slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "", str(value or "unknown").lower())
    return text or "unknown"


def _score_meta_fields(payload: dict[str, Any]) -> dict[str, Any]:
    audit = payload.get("audit") if isinstance(payload.get("audit"), dict) else {}
    usage = audit.get("usage") if isinstance(audit.get("usage"), dict) else {}
    provider = payload.get("llm_provider") or audit.get("llm_provider")
    model = payload.get("llm_model") or audit.get("llm_model")
    return {
        "llm_provider": provider,
        "llm_model": model,
        "estimated_cost_usd": usage.get("estimated_cost_usd"),
        "total_tokens": usage.get("total_tokens"),
    }


class ScoreStore:
    """Index in scores.json + full scores under data/scores/.

    Latest score per (job_id, candidate_id) keeps identity ``{job_id}_{candidate_id}``.
    On re-score, the previous detail is archived under data/scores/history/ and indexed
    in score_history.json so Local vs OpenAI (and other) runs remain comparable.
    """

    def __init__(
        self,
        index_path: Path,
        scores_dir: Path,
        *,
        history_index_path: Path | None = None,
        history_dir: Path | None = None,
    ):
        self.index_path = index_path
        self.scores_dir = scores_dir
        self.history_index_path = history_index_path or (DATA_DIR / "score_history.json")
        self.history_dir = history_dir or (scores_dir / "history")
        self.scores_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            _write_json(self.index_path, [])
        if not self.history_index_path.exists():
            _write_json(self.history_index_path, [])
        self.migrate()

    def read(self) -> list[dict[str, Any]]:
        """Return lightweight index entries (latest per pair)."""
        data = _read_json(self.index_path)
        return data if isinstance(data, list) else []

    def read_history(self) -> list[dict[str, Any]]:
        data = _read_json(self.history_index_path)
        return data if isinstance(data, list) else []

    def get(self, score_id: str) -> dict[str, Any] | None:
        index = find_by_id(self.read(), score_id)
        if not index:
            return None
        return self._hydrate(index)

    def get_any(self, entry_id: str) -> dict[str, Any] | None:
        """Resolve latest score id or a history run id."""
        latest = self.get(entry_id)
        if latest:
            return latest
        return self.get_history(entry_id)

    def find(self, job_id: str, candidate_id: str) -> dict[str, Any] | None:
        for entry in self.read():
            if entry.get("job_id") == job_id and entry.get("candidate_id") == candidate_id:
                return self._hydrate(entry)
        return None

    def history_for(self, job_id: str, candidate_id: str) -> list[dict[str, Any]]:
        """History index entries for a pair, newest first."""
        items = [
            entry
            for entry in self.read_history()
            if entry.get("job_id") == job_id and entry.get("candidate_id") == candidate_id
        ]
        items.sort(key=lambda e: str(e.get("archived_at") or e.get("created_at") or ""), reverse=True)
        return items

    def get_history(self, history_id: str) -> dict[str, Any] | None:
        index = find_by_id(self.read_history(), history_id)
        if not index:
            return None
        hydrated = self._hydrate(index)
        hydrated["history_id"] = index.get("id")
        hydrated["is_history"] = True
        # Keep pair identity available; history id is the archival key.
        if not hydrated.get("score_id"):
            hydrated["score_id"] = index.get("score_id")
        return hydrated

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = self.read()
        score_id = str(payload.get("id") or f"{payload.get('job_id')}_{payload.get('candidate_id')}")
        payload = {**payload, "id": score_id}

        existing = find_by_id(items, score_id)
        if existing is not None:
            self._archive_existing(existing)

        slug = slugify(str(payload.get("candidate_name") or ""))
        if existing and existing.get("path"):
            rel_path = existing["path"]
            path = self._resolve_path(existing)
        else:
            filename = f"{score_id}_{slug}_score.json"
            path = self.scores_dir / filename
            rel_path = self._relative_path(path)

        detail = dict(payload)
        detail.pop("path", None)
        meta = _score_meta_fields(detail)
        _write_json(path, detail)

        index_entry = {
            "id": score_id,
            "job_id": payload.get("job_id"),
            "candidate_id": payload.get("candidate_id"),
            "job_title": payload.get("job_title"),
            "candidate_name": payload.get("candidate_name"),
            "final_score": payload.get("final_score"),
            "verdict_label": payload.get("verdict_label"),
            "method": payload.get("method"),
            "scoring_model_version": payload.get("scoring_model_version") or "v1",
            "llm_provider": meta["llm_provider"],
            "llm_model": meta["llm_model"],
            "created_at": payload.get("created_at"),
            "path": rel_path,
        }

        if existing is None:
            items.append(index_entry)
        else:
            existing.clear()
            existing.update(index_entry)
        _write_json(self.index_path, items)
        return {**detail, "path": rel_path}

    def _archive_existing(self, index_entry: dict[str, Any]) -> dict[str, Any] | None:
        """Copy current detail into history before overwrite. Returns history index entry."""
        detail = self._hydrate(index_entry)
        if not detail:
            return None

        score_id = str(index_entry.get("id") or detail.get("id") or "")
        if not score_id:
            return None

        # Skip empty shells with no score payload.
        if detail.get("final_score") is None and not detail.get("items") and not detail.get("method"):
            path = self._resolve_path(index_entry)
            if not path.exists():
                return None

        meta = _score_meta_fields(detail)
        created_at = detail.get("created_at") or index_entry.get("created_at")
        archived_at = _iso_now()
        stamp = _history_stamp(created_at)
        provider = _provider_slug(meta["llm_provider"])
        history_id = f"{score_id}_{stamp}_{provider}"

        # Avoid collisions if the same second is archived twice.
        history_items = self.read_history()
        if find_by_id(history_items, history_id):
            history_id = f"{history_id}_{uuid4().hex[:6]}"

        filename = f"{history_id}_score.json"
        path = self.history_dir / filename
        rel_path = self._relative_path(path)

        archived_detail = dict(detail)
        archived_detail.pop("path", None)
        archived_detail["id"] = history_id
        archived_detail["score_id"] = score_id
        archived_detail["archived_at"] = archived_at
        archived_detail["is_history"] = True
        _write_json(path, archived_detail)

        history_entry = {
            "id": history_id,
            "score_id": score_id,
            "job_id": detail.get("job_id") or index_entry.get("job_id"),
            "candidate_id": detail.get("candidate_id") or index_entry.get("candidate_id"),
            "job_title": detail.get("job_title") or index_entry.get("job_title"),
            "candidate_name": detail.get("candidate_name") or index_entry.get("candidate_name"),
            "final_score": detail.get("final_score"),
            "verdict_label": detail.get("verdict_label"),
            "method": detail.get("method"),
            "scoring_model_version": detail.get("scoring_model_version")
            or index_entry.get("scoring_model_version")
            or "v1",
            "llm_provider": meta["llm_provider"],
            "llm_model": meta["llm_model"],
            "created_at": created_at,
            "archived_at": archived_at,
            "estimated_cost_usd": meta["estimated_cost_usd"],
            "total_tokens": meta["total_tokens"],
            "path": rel_path,
        }
        history_items.append(history_entry)
        _write_json(self.history_index_path, history_items)
        return history_entry

    def migrate(self) -> None:
        raw = _read_json(self.index_path)
        if not isinstance(raw, list) or not raw:
            return

        heavy_keys = {"items", "profile_summary", "verdict"}
        changed = False
        index: list[dict[str, Any]] = []

        for item in raw:
            if not isinstance(item, dict):
                continue
            score_id = str(item.get("id") or f"{item.get('job_id')}_{item.get('candidate_id')}")
            if not item.get("job_id") or not item.get("candidate_id"):
                continue

            has_heavy = any(key in item for key in heavy_keys)
            path = self._resolve_path(item) if item.get("path") else None
            needs_split = has_heavy or not item.get("path") or path is None or not path.exists()

            if needs_split:
                slug = slugify(str(item.get("candidate_name") or ""))
                filename = f"{score_id}_{slug}_score.json"
                path = self.scores_dir / filename
                rel_path = self._relative_path(path)

                if path.exists() and not has_heavy:
                    detail = _read_json(path)
                else:
                    detail = {**item, "id": score_id}
                    detail.pop("path", None)
                    if path.exists():
                        existing_detail = _read_json(path)
                        if isinstance(existing_detail, dict):
                            for key in heavy_keys:
                                if key in existing_detail and key not in detail:
                                    detail[key] = existing_detail[key]
                    _write_json(path, detail)

                meta = _score_meta_fields(detail if isinstance(detail, dict) else {})
                index_entry = {
                    "id": score_id,
                    "job_id": item.get("job_id"),
                    "candidate_id": item.get("candidate_id"),
                    "job_title": item.get("job_title"),
                    "candidate_name": item.get("candidate_name"),
                    "final_score": item.get("final_score"),
                    "verdict_label": item.get("verdict_label") or (
                        detail.get("verdict_label") if isinstance(detail, dict) else None
                    ),
                    "method": item.get("method"),
                    "scoring_model_version": item.get("scoring_model_version")
                    or (detail.get("scoring_model_version") if isinstance(detail, dict) else None)
                    or "v1",
                    "llm_provider": item.get("llm_provider") or meta["llm_provider"],
                    "llm_model": item.get("llm_model") or meta["llm_model"],
                    "created_at": item.get("created_at"),
                    "path": rel_path,
                }
                index.append(index_entry)
                changed = True
            else:
                entry = {key: item.get(key) for key in SCORE_INDEX_KEYS}
                entry["id"] = score_id
                # Backfill provider/model from detail when missing on index.
                if not entry.get("llm_provider") or not entry.get("llm_model"):
                    detail_path = self._resolve_path(item)
                    if detail_path.exists():
                        detail = _read_json(detail_path)
                        if isinstance(detail, dict):
                            meta = _score_meta_fields(detail)
                            if not entry.get("llm_provider") and meta["llm_provider"]:
                                entry["llm_provider"] = meta["llm_provider"]
                                changed = True
                            if not entry.get("llm_model") and meta["llm_model"]:
                                entry["llm_model"] = meta["llm_model"]
                                changed = True
                index.append(entry)

        if changed:
            _write_json(self.index_path, index)

    def _hydrate(self, index: dict[str, Any]) -> dict[str, Any]:
        path = self._resolve_path(index)
        if path.exists():
            detail = _read_json(path)
            if isinstance(detail, dict):
                return {**index, **detail, "path": index.get("path") or self._relative_path(path)}
        return dict(index)

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(DATA_DIR))
        except ValueError:
            return str(path)

    def _resolve_path(self, entry: dict[str, Any]) -> Path:
        rel = str(entry.get("path") or "")
        path = Path(rel)
        if path.is_absolute():
            return path
        return DATA_DIR / path


domains_store = JsonStore(DATA_DIR / "domains.json", DEFAULT_DOMAINS)
jobs_store = JsonStore(DATA_DIR / "jobs.json", [])
candidates_store = CandidateStore(DATA_DIR / "candidates.json", CANDIDATES_DIR)
scores_store = ScoreStore(DATA_DIR / "scores.json", SCORES_DIR)


def new_id() -> str:
    return uuid4().hex[:12]


def find_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("id") == item_id), None)


def upsert(items: list[dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("id"):
        payload["id"] = new_id()
        items.append(payload)
        return payload

    existing = find_by_id(items, payload["id"])
    if existing is None:
        items.append(payload)
        return payload

    existing.clear()
    existing.update(payload)
    return existing
