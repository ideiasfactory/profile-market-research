from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Formatter


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@lru_cache(maxsize=64)
def _read_prompt_file(relative_name: str) -> str:
    """Read prompt text: active managed version if present, else prompts/ file."""
    try:
        from app.prompt_store import get_active_prompt_content

        override = get_active_prompt_content(relative_name)
        if override is not None and override.strip():
            return override.strip()
    except Exception:
        pass
    path = PROMPTS_DIR / relative_name
    if not path.exists():
        raise FileNotFoundError(f"Prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8").strip()


def clear_prompt_cache() -> None:
    _read_prompt_file.cache_clear()


def load_prompt(relative_name: str, **kwargs: str) -> str:
    """Carrega um prompt (arquivo ou versão ativa gerenciada) e aplica placeholders.

    Sempre mescla parâmetros de negócio (quando `inject_in_prompts=true`):
    - `{business_context}` — bloco textual com label/chave/valor
    - `{<key>}` — valor individual (ex.: `{target_margin_pct}`, `{iss_pct}`)

    kwargs explícitos têm precedência sobre parâmetros de negócio.
    Placeholders ausentes permanecem literais (não quebram o template).
    """
    template = _read_prompt_file(relative_name)
    values: dict[str, str] = {}
    try:
        from app.business_settings import prompt_placeholders

        values.update(prompt_placeholders())
    except Exception:
        pass
    values.update({key: str(value) for key, value in kwargs.items()})
    if not values and "{" not in template:
        return template
    field_names = {name for _, name, _, _ in Formatter().parse(template) if name}
    if not field_names:
        return template
    return template.format_map(_SafeDict(values))
