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

// The five deterministic demo cases from docs/scoring-spec.md.
// Amounts are chosen so the scores come out exact.
const DEMO_CASES = {
  clean:     { amount: 50,  payee_id: "payee-known", sandbox_status: "SUCCESS" },
  refused:   { amount: 50,  payee_id: "payee-known", sandbox_status: "TRANSACTION_REFUSED" },
  declined:  { amount: 50,  payee_id: "payee-known", sandbox_status: "INSTRUMENT_DECLINED" },
  pattern:   { amount: 400, payee_id: "payee-new",   sandbox_status: "SUCCESS" },
  capped:    { amount: 600, payee_id: "payee-new",   sandbox_status: "INSTRUMENT_DECLINED" },
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
  // Seed one clean $50 transaction to "payee-known" first, so that
  // payee is known (not first) for the clean / refused / declined cases.
  // The pattern / capped cases need account history to score 60 / 100:
  // a $100 median and 3 transactions in the last 60 minutes, so they
  // get three clean $100 transactions instead — they show up in history,
  // which is the point: the median and velocity come from history.
  const seedAmount = (btn.dataset.case === "pattern" || btn.dataset.case === "capped") ? 100 : 50;
  const seedCount = (btn.dataset.case === "pattern" || btn.dataset.case === "capped") ? 3 : 1;
  for (let i = 0; i < seedCount; i++) {
    await score({ amount: seedAmount, payee_id: "payee-known", sandbox_status: "SUCCESS" });
  }
  const r = await score(DEMO_CASES[btn.dataset.case]);
  if (r) { showResult(r); refreshHistory(); }
});

refreshHistory();
