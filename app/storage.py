from __future__ import annotations

import json
import re
import unicodedata
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
    "created_at",
    "path",
)


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


class ScoreStore:
    """Index in scores.json + full scores under data/scores/."""

    def __init__(self, index_path: Path, scores_dir: Path):
        self.index_path = index_path
        self.scores_dir = scores_dir
        self.scores_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            _write_json(self.index_path, [])
        self.migrate()

    def read(self) -> list[dict[str, Any]]:
        """Return lightweight index entries."""
        data = _read_json(self.index_path)
        return data if isinstance(data, list) else []

    def get(self, score_id: str) -> dict[str, Any] | None:
        index = find_by_id(self.read(), score_id)
        if not index:
            return None
        return self._hydrate(index)

    def find(self, job_id: str, candidate_id: str) -> dict[str, Any] | None:
        for entry in self.read():
            if entry.get("job_id") == job_id and entry.get("candidate_id") == candidate_id:
                return self._hydrate(entry)
        return None

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = self.read()
        score_id = str(payload.get("id") or f"{payload.get('job_id')}_{payload.get('candidate_id')}")
        payload = {**payload, "id": score_id}

        existing = find_by_id(items, score_id)
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
                    "created_at": item.get("created_at"),
                    "path": rel_path,
                }
                index.append(index_entry)
                changed = True
            else:
                entry = {key: item.get(key) for key in SCORE_INDEX_KEYS}
                entry["id"] = score_id
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
