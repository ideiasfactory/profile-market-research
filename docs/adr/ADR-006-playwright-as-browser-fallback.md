# ADR-006 — Playwright as Browser Fallback

Decision: Playwright is used only after HTTP extraction fails or content is insufficient.

Reason: headless browser crawling is slower, heavier and should not be used indiscriminately.
