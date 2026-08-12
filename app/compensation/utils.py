from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(*parts: object, length: int = 16) -> str:
    text = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def canonicalize_url(url: str) -> str:
    split = urlsplit(url.strip())
    query = urlencode(
        [(key, value) for key, value in parse_qsl(split.query, keep_blank_values=True) if key.lower() not in TRACKING_PARAMS]
    )
    path = split.path.rstrip("/") or "/"
    return urlunsplit((split.scheme.lower(), split.netloc.lower(), path, query, ""))


def extract_money_values(text: str) -> list[float]:
    values: list[float] = []
    pattern = (
        r"R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?|[0-9]+(?:,[0-9]{2})?)"
        r"(?:\s*(milh(?:ao|ões|oes)|mil))?"
    )
    for match in re.finditer(pattern, text or "", flags=re.I):
        raw = match.group(1).replace(".", "").replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            continue
        scale = (match.group(2) or "").lower()
        if scale.startswith("milh"):
            value *= 1_000_000
        elif scale.startswith("mil"):
            value *= 1_000
        values.append(value)
    return values
