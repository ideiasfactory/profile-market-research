from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=32)
def _read_prompt_file(relative_name: str) -> str:
    path = PROMPTS_DIR / relative_name
    if not path.exists():
        raise FileNotFoundError(f"Prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_prompt(relative_name: str, **kwargs: str) -> str:
    """Carrega um prompt da pasta `prompts/` e aplica placeholders opcionais."""
    template = _read_prompt_file(relative_name)
    if not kwargs:
        return template
    return template.format(**kwargs)
