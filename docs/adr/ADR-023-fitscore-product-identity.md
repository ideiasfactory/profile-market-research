# ADR-023 — FitScore Product Identity and UI Themes

## Status

Accepted

## Context

The application shipped under the technical name Professional Profile Analyser (`professional_profile_analyser` / `Profile Analyser` in the UI). Product use is currently internal (hiring operations) while a possible commercial path (e.g. Ideas Factory) remains open. The UI was dark-only, with Inter/system typography and no durable brand mark.

We need a **generic product identity** that is not tied to a client or holding brand, plus first-class light/dark themes so operators can choose contrast for long sessions.

## Decision

1. **Product brand name is FitScore** in the operator UI (header, document title, FastAPI app title, home copy).
2. **Technical identifiers stay unchanged** for this ADR: repo path, Python package name (`professional-profile-analyser`), and conversational packages under `llm-tools/` may keep the legacy name until a dedicated rename.
3. **Visual identity** uses teal accent, Space Grotesk (brand) + DM Sans (body), and a geometric mark (F + score arc) at `app/static/brand/fitscore-mark.svg` (PNG reference also stored for design use).
4. **Themes** are `light` (default) and `dark`, applied via `html[data-theme]`, persisted in `localStorage` key `fitscore-theme`, with a FOUC-safe bootstrap script in `base.html` and a header toggle in `app.js`.
5. Branding remains **generic** — no Aggrandize or Ideas Factory marks in the product shell.

## Consequences

- Operators see FitScore immediately; docs should mention both FitScore (product) and the legacy technical name where relevant.
- Theme preference is client-only (no server setting).
- A future rename of package/repo or white-label theming would be separate ADRs.
