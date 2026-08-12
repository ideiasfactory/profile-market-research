# ADR-014 — Load `.env` at Application Startup

Decision: `app.main` calls `load_app_env()` from `app.env_loader` before configuring logging or creating the FastAPI app. The loader reads the project-root `.env` with `override=False`, so exported shell variables win.

Reason: local and IHL runs need provider keys and Ollama settings without requiring every operator to export them manually, while preserving explicit environment overrides.
