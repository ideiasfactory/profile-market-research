from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from urllib.parse import urlsplit
from html.parser import HTMLParser

import httpx

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - fallback for fresh MVP venvs
    BeautifulSoup = None

from app.compensation.core import ProviderConfig
from app.compensation.domain.schemas import CrawledDocument, SearchResult
from app.compensation.logging_utils import log_event
from app.compensation.utils import now_iso


class CompensationCrawler(ABC):
    name: str
    domains: tuple[str, ...] = ()

    def __init__(self, config: ProviderConfig):
        self.config = config

    def can_handle(self, url: str) -> bool:
        host = urlsplit(url).netloc.lower()
        return any(domain in host for domain in self.domains)

    async def crawl(self, url: str, search_result: SearchResult | None = None) -> CrawledDocument:
        try:
            document = await self._http_crawl(url)
            if self._is_content_sufficient(document.content):
                return document
            log_event(
                "crawl_http_insufficient",
                level=logging.INFO,
                crawler=self.name,
                url=url,
                content_chars=len(document.content or ""),
            )
            playwright_document = await self._playwright_crawl(url)
            if playwright_document and self._is_content_sufficient(playwright_document.content):
                return playwright_document
            if playwright_document is None:
                log_event(
                    "crawl_playwright_unavailable",
                    level=logging.WARNING,
                    crawler=self.name,
                    url=url,
                )
            return self._snippet_document(url, search_result, status="partial")
        except httpx.HTTPStatusError as exc:
            status = "blocked" if exc.response.status_code in {401, 403, 429} else "failed"
            log_event(
                "crawl_http_error",
                level=logging.WARNING,
                crawler=self.name,
                url=url,
                status_code=exc.response.status_code,
                status=status,
            )
            return self._snippet_document(url, search_result, status=status)
        except Exception as exc:
            log_event(
                "crawl_failed",
                level=logging.WARNING,
                crawler=self.name,
                url=url,
                error=str(exc),
            )
            return self._snippet_document(url, search_result, status="failed")

    async def _http_crawl(self, url: str) -> CrawledDocument:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; CompensationResearchBot/0.1; +internal-mvp)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
        title, content = clean_html(response.text)
        return CrawledDocument(
            url=str(response.url),
            source=self.name,
            title=title,
            content=content,
            html=response.text[:50000],
            retrieved_at=now_iso(),
            crawl_method="http",
            status="success",
            metadata={"status_code": response.status_code},
        )

    async def _playwright_crawl(self, url: str) -> CrawledDocument | None:
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return None
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_seconds * 1000)
                content = await page.content()
                title = await page.title()
                await browser.close()
            _title, text = clean_html(content)
            return CrawledDocument(
                url=url,
                source=self.name,
                title=title or _title,
                content=text,
                html=content[:50000],
                retrieved_at=now_iso(),
                crawl_method="playwright",
                status="success",
            )
        except Exception:
            return None

    def _snippet_document(
        self,
        url: str,
        search_result: SearchResult | None,
        *,
        status: str = "partial",
    ) -> CrawledDocument:
        return CrawledDocument(
            url=url,
            source=self.name,
            title=search_result.title if search_result else "",
            content=search_result.snippet if search_result else "",
            html=None,
            retrieved_at=now_iso(),
            crawl_method="search_snippet",
            status=status,  # type: ignore[arg-type]
            metadata={"provider": search_result.provider if search_result else ""},
        )

    def _is_content_sufficient(self, content: str) -> bool:
        text = content or ""
        return len(text) >= 300 and ("R$" in text or "salário" in text.lower() or "remuneração" in text.lower())

    @abstractmethod
    def source_queries(self, profile: str, location: str) -> list[str]:
        raise NotImplementedError


def clean_html(html: str) -> tuple[str, str]:
    if BeautifulSoup is None:
        parser = SimpleHTMLTextExtractor()
        parser.feed(html or "")
        return parser.title, "\n".join(line for line in parser.text.splitlines() if line.strip())[:25000]
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    structured = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        structured.append(script.get_text(" ", strip=True))
    text = soup.get_text("\n", strip=True)
    content = "\n".join([*structured, text])
    return title, "\n".join(line for line in content.splitlines() if line.strip())[:25000]


class SimpleHTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self._skip = False
        self.title = ""
        self._parts: list[str] = []

    @property
    def text(self) -> str:
        return "\n".join(self._parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        text = " ".join((data or "").split())
        if not text or self._skip:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
        self._parts.append(text)
