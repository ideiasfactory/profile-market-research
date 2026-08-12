from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Formatter


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@lru_cache(maxsize=32)
def _read_prompt_file(relative_name: str) -> str:
    path = PROMPTS_DIR / relative_name
    if not path.exists():
        raise FileNotFoundError(f"Prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_prompt(relative_name: str, **kwargs: str) -> str:
    """Carrega um prompt da pasta `prompts/` e aplica placeholders.

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
    # Only format fields that exist in the template to avoid surprises with braces in JSON examples.
    field_names = {
        name for _, name, _, _ in Formatter().parse(template) if name
    }
    if not field_names:
        return template
    return template.format_map(_SafeDict(values))
