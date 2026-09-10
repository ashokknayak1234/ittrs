# ITTRS frontend

The static website is in `public/`. This directory no longer contains a JavaScript backend or a Wrangler deployment config.

- HTML: `public/index.html`
- CSS: `public/style.css`
- Browser behaviour: `public/app.js`
- Queue filtering: `public/view-model.js`
- Frontend checks: `npm test`

The **Python/FastAPI backend and deployment configuration are in `../backend/`**. Deploy both frontend and backend from that directory:

```powershell
uv run pytest -q
uv run pywrangler deploy --dry-run
uv run pywrangler deploy
```

Full development/setup instructions: [repository guide](../README.md).

Optional Ollama tunnel configuration template: `../backend/tunnel/config.example.yml`.
