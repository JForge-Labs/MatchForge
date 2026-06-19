const statusEl = document.getElementById("affiliate-status");
const createStatusEl = document.getElementById("create-affiliate-status");
const payoutNoteEl = document.getElementById("payout-note");

function showStatus(msg, ok = true, el = statusEl) {
  if (!el) return;
  el.textContent = msg;
  el.className = ok ? "status ok" : "status error";
}

async function markPaid(ids, note) {
  if (!ids.length) {
    showStatus("No commissions selected", false);
    return;
  }
  const resp = await fetch("/admin/api/affiliate-commissions/mark-paid", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, payout_note: note || null }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || "Mark paid failed");
  return data;
}

function copyInputValue(input) {
  if (!input?.value) return Promise.reject(new Error("Nothing to copy"));
  return navigator.clipboard.writeText(input.value);
}

document.querySelectorAll(".copy-signup-link").forEach((btn) => {
  btn.addEventListener("click", () => {
    const input = btn.closest(".referral-row")?.querySelector(".affiliate-signup-link");
    copyInputValue(input).then(() => showStatus("Signup link copied — share with their audience"));
  });
});

document.querySelectorAll(".copy-dashboard-link").forEach((btn) => {
  btn.addEventListener("click", () => {
    const input = btn.closest(".referral-row")?.querySelector(".affiliate-dashboard-link");
    copyInputValue(input).then(() => showStatus("Dashboard link copied — share with partner only"));
  });
});

document.getElementById("create-affiliate-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const btn = form.querySelector('button[type="submit"]');
  const body = {
    slug: document.getElementById("aff-slug")?.value?.trim(),
    name: document.getElementById("aff-name")?.value?.trim(),
    contact_email: document.getElementById("aff-email")?.value?.trim(),
    commission_rate_pct: Number(document.getElementById("aff-rate")?.value || 15),
    notes: document.getElementById("aff-notes")?.value?.trim() || null,
  };
  btn.disabled = true;
  showStatus("Creating affiliate…", true, createStatusEl);
  try {
    const resp = await fetch("/admin/api/affiliates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || "Could not create affiliate");
    showStatus(`Created ${data.affiliate.name} — reloading…`, true, createStatusEl);
    setTimeout(() => window.location.reload(), 900);
  } catch (err) {
    showStatus(err.message, false, createStatusEl);
    btn.disabled = false;
  }
});

document.getElementById("cleanup-test-affiliates")?.addEventListener("click", async () => {
  const btn = document.getElementById("cleanup-test-affiliates");
  if (!confirm("Remove all test-suite affiliate records from the database?")) return;
  btn.disabled = true;
  try {
    const resp = await fetch("/admin/api/affiliates/cleanup-test", { method: "POST" });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || "Cleanup failed");
    showStatus(`Removed ${data.deleted} test affiliate(s)`);
    setTimeout(() => window.location.reload(), 900);
  } catch (err) {
    showStatus(err.message, false);
    btn.disabled = false;
  }
});

document.querySelectorAll(".mark-paid-one").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const id = Number(btn.dataset.id);
    const note = payoutNoteEl?.value?.trim() || null;
    btn.disabled = true;
    try {
      const data = await markPaid([id], note);
      showStatus(`Marked ${data.marked_paid} commission(s) paid`);
      setTimeout(() => window.location.reload(), 900);
    } catch (err) {
      showStatus(err.message, false);
      btn.disabled = false;
    }
  });
});

document.getElementById("mark-selected-paid")?.addEventListener("click", async () => {
  const ids = [...document.querySelectorAll(".commission-select:checked")].map((el) =>
    Number(el.value)
  );
  const note = payoutNoteEl?.value?.trim() || null;
  const btn = document.getElementById("mark-selected-paid");
  btn.disabled = true;
  try {
    const data = await markPaid(ids, note);
    showStatus(`Marked ${data.marked_paid} commission(s) paid`);
    setTimeout(() => window.location.reload(), 900);
  } catch (err) {
    showStatus(err.message, false);
    btn.disabled = false;
  }
});

document.querySelectorAll(".mark-all-paid").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const affiliateId = btn.dataset.affiliateId;
    const ids = [...document.querySelectorAll(`tr[data-affiliate-id="${affiliateId}"][data-status="pending"] .commission-select`)]
      .map((el) => Number(el.value));
    const note = payoutNoteEl?.value?.trim() || null;
    btn.disabled = true;
    try {
      const data = await markPaid(ids, note);
      showStatus(`Marked ${data.marked_paid} commission(s) paid`);
      setTimeout(() => window.location.reload(), 900);
    } catch (err) {
      showStatus(err.message, false);
      btn.disabled = false;
    }
  });
});

document.getElementById("select-all-pending")?.addEventListener("change", (e) => {
  const checked = e.target.checked;
  document.querySelectorAll(".commission-select").forEach((el) => {
    el.checked = checked;
  });
});

document.getElementById("filter-commissions")?.addEventListener("click", () => {
  const affiliateId = document.getElementById("filter-affiliate")?.value || "";
  const status = document.getElementById("filter-status")?.value || "";
  const params = new URLSearchParams();
  if (affiliateId) params.set("affiliate_id", affiliateId);
  if (status) params.set("status", status);
  window.location.href = `/admin/affiliates?${params}`;
});
