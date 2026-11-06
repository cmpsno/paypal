// Dashboard logic: talk to the scoring API, nothing else.
// No framework, no build step. The server does the scoring;
// this file only sends the form and renders what comes back.
//
// API_BASE comes from config.js: "" locally (same origin), or the
// Render URL when this page is hosted on GitHub Pages.
const API_BASE = (window.API_BASE || "").replace(/\/$/, "");

async function api(path, options) {
  return fetch(API_BASE + path, options);
}

const form = document.getElementById("score-form");
const resultCard = document.getElementById("result-card");
const historyTable = document.getElementById("history-table");
const historyBody = document.getElementById("history-body");
const emptyMsg = document.getElementById("empty");

// The six deterministic demo cases from docs/scoring-spec.md.
// Amounts are chosen so the scores come out exact.
const DEMO_CASES = {
  clean:     { amount: 50,  payee_id: "payee-known", sandbox_status: "SUCCESS" },
  refused:   { amount: 50,  payee_id: "payee-known", sandbox_status: "TRANSACTION_REFUSED" },
  declined:  { amount: 50,  payee_id: "payee-known", sandbox_status: "INSTRUMENT_DECLINED" },
  pattern:   { amount: 400, payee_id: "payee-new",   sandbox_status: "SUCCESS" },
  capped:    { amount: 600, payee_id: "payee-new",   sandbox_status: "INSTRUMENT_DECLINED" },
  // Structuring: the 5th $20 to the same payee in 10 min.
  // Seeds below are 4 x $20 to the same payee, so this one scores
  // 20 (velocity) + 30 (structuring) = 50, HOLD.
  structuring: { amount: 20, payee_id: "payee-structuring", sandbox_status: "SUCCESS" },
};

// History seeded before each demo case so the score is exact on
// every click. The pattern / capped cases need account history to
// score 60 / 100: a $100 median and 3 transactions in the last
// 60 minutes, so they get three clean $100 transactions instead —
// they show up in history, which is the point: the median and
// velocity come from history.
const DEMO_SEEDS = {
  clean:       [{ amount: 50,  payee_id: "payee-known", count: 1 }],
  refused:     [{ amount: 50,  payee_id: "payee-known", count: 1 }],
  declined:    [{ amount: 50,  payee_id: "payee-known", count: 1 }],
  pattern:     [{ amount: 100, payee_id: "payee-known", count: 3 }],
  capped:      [{ amount: 100, payee_id: "payee-known", count: 3 }],
  structuring: [{ amount: 20,  payee_id: "payee-structuring", count: 4 }],
};

async function score(payload) {
  const res = await api("/api/score", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.error || "Scoring failed.");
    return null;
  }
  return res.json();
}

function showResult(r) {
  resultCard.hidden = false;
  const badge = document.getElementById("decision");
  badge.textContent = r.decision;
  badge.className = "badge " + r.decision.toLowerCase();
  document.getElementById("score").textContent = r.score;
  document.getElementById("codes").textContent =
    r.reason_codes.length ? r.reason_codes.join(", ") : "(none)";
  document.getElementById("why").textContent =
    r.decision === "HOLD"
      ? `Held at ${r.score}/100 — top reason: ${r.top_reason || "—"}.`
      : `Released at ${r.score}/100 — ${r.reason_codes.length ? "some risk signals, but below the 50-point bar." : "no risk signals."}`;
  // Plain-English explanation from the server. The score decides;
  // this only explains it. Falls back to the one-liner above if an
  // older server response has no explanation field.
  document.getElementById("explanation").textContent =
    r.explanation || "";
  document.getElementById("result-meta").textContent =
    `$${r.amount} · payee ${r.payee_id || "(unknown)"} · ${r.sandbox_status}` +
    (r.account_median_amount != null ? ` · account median $${r.account_median_amount}` : "") +
    ` · ${r.txns_last_60m} txn(s) in the last 60 min`;
  resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderHistory(rows) {
  historyBody.innerHTML = "";
  emptyMsg.hidden = rows.length > 0;
  historyTable.hidden = rows.length === 0;
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td>$${r.amount}</td>` +
      `<td>${r.payee_id || "(unknown)"}</td>` +
      `<td>${r.sandbox_status}</td>` +
      `<td>${r.score}</td>` +
      `<td>${r.decision}</td>` +
      `<td>${r.reason_codes.join(", ") || "(none)"}</td>`;
    historyBody.appendChild(tr);
  }
}

async function refreshHistory() {
  const res = await api("/api/transactions");
  renderHistory(await res.json());
  loadMonitoring();
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await score({
    amount: parseFloat(document.getElementById("amount").value),
    payee_id: document.getElementById("payee-id").value.trim() || null,
    sandbox_status: document.getElementById("sandbox-status").value,
  });
  if (r) { showResult(r); refreshHistory(); }
});

document.getElementById("demos").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-case]");
  if (!btn) return;
  // Reset first so every demo case is deterministic on every click.
  await api("/api/reset", { method: "POST" });
  for (const seed of DEMO_SEEDS[btn.dataset.case] || []) {
    for (let i = 0; i < seed.count; i++) {
      await score({ amount: seed.amount, payee_id: seed.payee_id, sandbox_status: "SUCCESS" });
    }
  }
  const r = await score(DEMO_CASES[btn.dataset.case]);
  if (r) { showResult(r); refreshHistory(); }
});

refreshHistory();

// --- Offline ML panel (Zenodo data only; never a PayPal transaction) ---
async function loadOfflineModel() {
  const el = document.getElementById("offline-metrics");
  try {
    const res = await api("/api/offline-model");
    const m = await res.json();
    const a = m.evaluation.amount_plus_v;
    el.textContent =
      `Logistic regression, ${m.trained_on}. Out-of-fold PR-AUC ${a.pr_auc} ` +
      `(amount-only: ${m.evaluation.amount_only.pr_auc}), F1 ${a.f1}, ` +
      `precision ${a.precision}, recall ${a.recall}, threshold ${m.threshold}. ` +
      `Amount rules catch all fraud but flag 27.5% of traffic; this model ` +
      `catches 96 of 111 while flagging 0.21%.`;
  } catch {
    el.textContent = "Offline model unavailable.";
  }
}

async function loadOfflineSamples() {
  const wrap = document.getElementById("offline-samples");
  try {
    const res = await api("/api/offline-samples");
    const data = await res.json();
    data.samples.forEach((s) => {
      const btn = document.createElement("button");
      btn.textContent = `${s.label} — $${s.amount} (dataset label: ${s.is_fraud ? "fraud" : "legitimate"})`;
      btn.addEventListener("click", async () => {
        const r = await api("/api/offline-score", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ amount: s.amount, features: s.features }),
        });
        if (!r.ok) return;
        const out = await r.json();
        document.getElementById("offline-result").hidden = false;
        document.getElementById("offline-label").textContent =
          `${s.label} — $${s.amount}, dataset label: ${s.is_fraud ? "fraud" : "legitimate"} (as recorded)`;
        document.getElementById("offline-prob").textContent = out.probability;
        document.getElementById("offline-threshold").textContent = out.threshold;
        const badge = document.getElementById("offline-decision");
        badge.textContent = out.decision;
        badge.className = "badge " + (out.decision === "FLAG" ? "hold" : "release");
        document.getElementById("offline-signals").textContent =
          out.top_signals.map((t) => t.feature).join(", ");
        loadMonitoring();
      });
      wrap.appendChild(btn);
    });
  } catch {
    wrap.textContent = "Offline samples unavailable.";
  }
}

loadOfflineModel();
loadOfflineSamples();

// --- Monitoring panel (the feedback loop) ---
async function loadMonitoring() {
  const metricsEl = document.getElementById("monitoring-metrics");
  const body = document.getElementById("monitoring-body");
  try {
    const [mRes, pRes] = await Promise.all([
      api("/api/monitoring"),
      api("/api/predictions"),
    ]);
    const m = await mRes.json();
    const rows = await pRes.json();
    const c = m.confirmed_outcomes;
    metricsEl.textContent =
      `${m.total_predictions} prediction(s) logged · ` +
      `hold/flag rate ${m.hold_or_flag_rate ?? "—"} · ` +
      `median amount all-time $${m.drift.median_amount_all ?? "—"}, ` +
      `last 20 $${m.drift.median_amount_last_20 ?? "—"} · ` +
      (c
        ? `confirmed: ${c.n} (${c.fraud} fraud, ${c.legitimate} legitimate) — ` +
          `precision ${c.precision}, recall ${c.recall}, F1 ${c.f1}`
        : m.confirmed_note);
    document.getElementById("monitoring-empty").hidden = rows.length > 0;
    document.getElementById("monitoring-table").hidden = rows.length === 0;
    body.innerHTML = "";
    for (const r of rows.slice(0, 10)) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${r.transaction_id}</td>` +
        `<td>${r.model}</td>` +
        `<td>${r.decision}</td>` +
        `<td>${r.score ?? r.probability ?? "—"}</td>` +
        `<td>${r.outcome || "(awaiting outcome)"}</td>`;
      body.appendChild(tr);
    }
  } catch {
    metricsEl.textContent = "Monitoring unavailable.";
  }
}

document.getElementById("outcome-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("outcome-msg");
  const res = await api("/api/outcomes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      transaction_id: document.getElementById("outcome-tx").value.trim(),
      outcome: document.getElementById("outcome-value").value,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    msg.textContent = err.error || "Could not record outcome.";
    return;
  }
  const entry = await res.json();
  msg.textContent = `Recorded: ${entry.transaction_id} confirmed ${entry.outcome}.`;
  loadMonitoring();
});

loadMonitoring();
