const grantForm = document.getElementById("admin-grant-form");
const grantStatus = document.getElementById("grant-status");

grantForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const accountId = Number(document.getElementById("grant-account-id")?.value);
  const amount = Number(document.getElementById("grant-amount")?.value);
  const note = document.getElementById("grant-note")?.value?.trim() || null;
  const btn = grantForm.querySelector('button[type="submit"]');

  if (!accountId || !amount) return;

  btn.disabled = true;
  grantStatus.className = "status";
  grantStatus.textContent = "Granting…";

  try {
    const resp = await fetch("/admin/api/grant-tokens", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId, amount, note }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || "Grant failed");
    grantStatus.textContent = `Granted ${amount} tokens — new balance: ${data.balance}`;
    grantStatus.className = "status ok";
    setTimeout(() => window.location.reload(), 1200);
  } catch (err) {
    grantStatus.textContent = err.message || "Could not grant tokens";
    grantStatus.className = "status error";
    btn.disabled = false;
  }
});