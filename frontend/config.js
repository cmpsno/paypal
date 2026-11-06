// API base URL for the scoring server.
//
// Local / Render-served dashboard: leave this as "" — the frontend
// calls the same origin (/api/score), so it just works.
//
// GitHub Pages dashboard: the Pages workflow replaces this line
// with the Render URL (repo variable RENDER_API_URL, no trailing
// slash), e.g. window.API_BASE = "https://paypal-risk-api.onrender.com";
// The Pages build never edits this file in the repo — the workflow
// edits a copy during deploy only.
window.API_BASE = "";
