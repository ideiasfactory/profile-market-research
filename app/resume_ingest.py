from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader
from io import BytesIO


LINKEDIN_HOSTS = {"linkedin.com", "www.linkedin.com", "br.linkedin.com"}
MIN_PDF_CHARS = 40
MIN_LINKEDIN_CHARS = 120


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): (value or "") for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag == "meta":
            prop = attrs_map.get("property") or attrs_map.get("name")
            content = attrs_map.get("content", "").strip()
            if prop and content:
                self.meta[prop.lower()] = content

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return "\n".join(self._chunks)


def is_linkedin_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if host not in LINKEDIN_HOSTS:
        return False
    return "/in/" in (parsed.path or "").lower()


def normalize_linkedin_url(value: str) -> str:
    url = value.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    parsed = urlparse(url)
    path = re.sub(r"/+$", "", parsed.path or "")
    return f"https://{parsed.hostname}{path}"


def extract_text_from_pdf(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.strip())
    combined = "\n\n".join(pages).strip()
    if len(combined) < MIN_PDF_CHARS:
        raise ValueError("Não foi possível extrair texto útil do PDF. Verifique se o arquivo não é só imagem.")
    return combined


def extract_text_from_upload(filename: str, content: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf") or content[:4] == b"%PDF":
        return extract_text_from_pdf(content)
    for encoding in ("utf-8", "latin-1"):
        try:
            text = content.decode(encoding).strip()
            if text:
                return text
        except UnicodeDecodeError:
            continue
    raise ValueError("Não foi possível ler o arquivo enviado. Use PDF, TXT ou Markdown.")


def _linkedin_text_from_html(html: str, url: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    meta = parser.meta
    parts: list[str] = []

    title = meta.get("og:title") or meta.get("twitter:title")
    description = meta.get("og:description") or meta.get("description") or meta.get("twitter:description")
    if title:
        parts.append(title)
    if description:
        parts.append(description)

    body = parser.text()
    # Remove ruído comum de auth wall / chrome do LinkedIn.
    cleaned_lines = []
    skip_markers = (
        "sign in",
        "join now",
        "agree & join",
        "by clicking continue",
        "linkedin corporation",
        "cookie",
    )
    for line in body.splitlines():
        normalized = line.strip()
        if len(normalized) < 3:
            continue
        lower = normalized.lower()
        if any(marker in lower for marker in skip_markers):
            continue
        cleaned_lines.append(normalized)

    # Mantém um recorte razoável do corpo visível.
    if cleaned_lines:
        parts.append("\n".join(cleaned_lines[:250]))

    combined = "\n\n".join(part for part in parts if part).strip()
    auth_wall = any(
        marker in html.lower()
        for marker in ("authwall", "sessionredirect", "join linkedin", "sign in to view")
    )
    if len(combined) < MIN_LINKEDIN_CHARS or (auth_wall and len(combined) < 400):
        raise ValueError(
            "O LinkedIn bloqueou a leitura automática deste perfil (login/auth wall). "
            "Envie o PDF do currículo ou cole o texto exportado do perfil."
        )
    return f"Fonte: LinkedIn ({url})\n\n{combined}"


async def fetch_linkedin_profile_text(url: str) -> str:
    if not is_linkedin_url(url):
        raise ValueError("Informe uma URL válida de perfil do LinkedIn (ex.: https://www.linkedin.com/in/usuario).")
    normalized = normalize_linkedin_url(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
        response = await client.get(normalized)
        response.raise_for_status()
        return _linkedin_text_from_html(response.text, normalized)


async def resolve_resume_content(
    *,
    resume_text: str = "",
    resume_filename: str = "",
    resume_bytes: bytes | None = None,
    linkedin_url: str = "",
) -> dict[str, Any]:
    """Resolve o texto do currículo a partir de PDF/arquivo, texto colado ou LinkedIn."""
    pasted = (resume_text or "").strip()
    linkedin = (linkedin_url or "").strip()

    if resume_bytes and resume_filename:
        text = extract_text_from_upload(resume_filename, resume_bytes)
        source_type = "pdf" if resume_filename.lower().endswith(".pdf") or resume_bytes[:4] == b"%PDF" else "file"
        return {
            "resume_text": text,
            "source_type": source_type,
            "source_label": resume_filename,
            "source_url": "",
        }

    if pasted:
        source_type = "text"
        source_label = "Texto colado"
        source_url = ""
        if linkedin and is_linkedin_url(linkedin):
            source_type = "linkedin"
            source_label = "Perfil LinkedIn (texto armazenado)"
            source_url = normalize_linkedin_url(linkedin)
        return {
            "resume_text": pasted,
            "source_type": source_type,
            "source_label": source_label,
            "source_url": source_url,
        }

    if linkedin:
        text = await fetch_linkedin_profile_text(linkedin)
        return {
            "resume_text": text,
            "source_type": "linkedin",
            "source_label": "Perfil LinkedIn",
            "source_url": normalize_linkedin_url(linkedin),
        }

    raise ValueError("Envie um PDF, informe o link do LinkedIn ou cole o texto do currículo.")
