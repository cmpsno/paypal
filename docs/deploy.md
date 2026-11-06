# Deploy — Pages frontend + Render API

Two pieces, in this order. Render first, Pages second — the Pages
site is useless without the API answering.

Live URLs when done:
- Frontend: https://cmpsno.github.io/paypal/
- API: https://paypal-risk-api.onrender.com (your Render URL may differ)

## 1. Render — the Python API

1. In Render, create a new **Blueprint** (or Web Service) from this
   repo. `render.yaml` at the repo root already defines it:
   - Service: `paypal-risk-api`, Python, free plan
   - Build: `pip install -r requirements.txt` (no real dependencies)
   - Start: `python3 -m backend.app`
   - Health check: `/health`
   - Render injects `PORT` automatically; the server reads it.
2. Wait for the first deploy to go green, then open
   `https://<your-service>.onrender.com/health` — it should return
   `{"ok": true}`.
3. Copy the service URL, with **no trailing slash**.

Notes:
- History is in-memory and resets when the service restarts or
  Render spins it down on the free plan. That is fine for the demo:
  the dashboard's demo buttons reset + seed history on every click.
- No secrets are needed for the API itself. PayPal Sandbox
  credentials are only for the separate CLI demo
  (`backend/demo_sandbox.py`) and are never put on Render.

## 2. GitHub Pages — the frontend

1. In the repo, go to **Settings → Pages → Build and deployment →
   Source: GitHub Actions**. (The workflow does the rest.)
2. Set a repo variable: **Settings → Secrets and variables →
   Actions → Variables → New variable**
   - Name: `RENDER_API_URL`
   - Value: your Render URL from step 1, no trailing slash.
3. Push (or re-run) the `Deploy frontend to GitHub Pages`
   workflow. It injects that URL into a *copy* of
   `frontend/config.js` at deploy time — the file in the repo
   stays as `window.API_BASE = "";` for local use.
4. Open https://cmpsno.github.io/paypal/ and click a demo case.
   Clean should score 0, pattern 60, capped 100.

If `RENDER_API_URL` is not set, Pages still deploys, but scoring
fails there — the page calls `/api/score` on Pages itself, which
does not exist. Set the variable and re-run the workflow.

## 3. Local — still works unchanged

```bash
python3 -m backend.app
# open http://localhost:8000
```

Locally `config.js` stays `""`, so the frontend calls the same
origin. Nothing about the local flow changed.

## What still needs a human

- Creating the Render service (needs the Render account).
- Setting the `RENDER_API_URL` repo variable.
- A classic PAT with `repo` + `workflow` scopes to push
  `.github/workflows/pages.yml` — earlier tokens could not push
  that folder. One-shot, used once, never stored.
