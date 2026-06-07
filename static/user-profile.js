const panel = document.getElementById("user-profile-panel");
const openBtn = document.getElementById("nav-profile-open");
const closeBackdrop = document.getElementById("user-profile-close");
const dismissBtn = document.getElementById("user-profile-dismiss");
const deleteBtn = document.getElementById("delete-account-btn");
const deleteConfirm = document.getElementById("delete-account-confirm");
const deleteStatus = document.getElementById("delete-account-status");

function openPanel() {
  if (!panel) return;
  panel.classList.remove("hidden");
  document.body.classList.add("profile-panel-open");
}

function closePanel() {
  if (!panel) return;
  panel.classList.add("hidden");
  document.body.classList.remove("profile-panel-open");
}

openBtn?.addEventListener("click", openPanel);
closeBackdrop?.addEventListener("click", closePanel);
dismissBtn?.addEventListener("click", closePanel);

deleteBtn?.addEventListener("click", async () => {
  const confirm = (deleteConfirm?.value || "").trim();
  if (confirm.toUpperCase() !== "DELETE") {
    if (deleteStatus) {
      deleteStatus.textContent = "Type DELETE to confirm.";
      deleteStatus.className = "status error";
    }
    return;
  }
  deleteBtn.disabled = true;
  deleteBtn.textContent = "Deleting…";
  try {
    const resp = await fetch("/account/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.detail || "Delete failed");
    }
    window.location.href = data.redirect || "/";
  } catch (err) {
    if (deleteStatus) {
      deleteStatus.textContent = err.message || "Could not delete account";
      deleteStatus.className = "status error";
    }
    deleteBtn.disabled = false;
    deleteBtn.textContent = "Delete my account";
  }
});