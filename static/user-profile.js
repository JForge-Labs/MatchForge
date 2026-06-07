const panel = document.getElementById("user-profile-panel");
const openBtn = document.getElementById("nav-profile-open");
const closeBackdrop = document.getElementById("user-profile-close");
const dismissBtn = document.getElementById("user-profile-dismiss");
const deleteBtn = document.getElementById("delete-account-btn");
const deleteConfirm = document.getElementById("delete-account-confirm");
const deleteStatus = document.getElementById("delete-account-status");

function showAvatarFallback(img) {
  img.classList.add("hidden");
  const wrap = img.parentElement;
  const fallback = wrap?.querySelector("[data-avatar-fallback]:not(img)");
  if (fallback) fallback.classList.remove("hidden");
}

document.querySelectorAll("img[data-avatar-fallback]").forEach((img) => {
  img.addEventListener("error", () => showAvatarFallback(img));
  if (img.complete && img.naturalWidth === 0) showAvatarFallback(img);
});

function openPanel() {
  if (!panel) return;
  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");
  document.body.classList.add("profile-panel-open");
  dismissBtn?.focus();
}

function closePanel() {
  if (!panel) return;
  panel.classList.add("hidden");
  panel.setAttribute("aria-hidden", "true");
  document.body.classList.remove("profile-panel-open");
  openBtn?.focus();
}

function showDeleteStatus(message, type) {
  if (!deleteStatus) return;
  deleteStatus.textContent = message;
  deleteStatus.className = `status ${type}`;
}

openBtn?.addEventListener("click", openPanel);
closeBackdrop?.addEventListener("click", closePanel);
dismissBtn?.addEventListener("click", closePanel);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && panel && !panel.classList.contains("hidden")) {
    closePanel();
  }
});

deleteBtn?.addEventListener("click", async () => {
  const confirm = (deleteConfirm?.value || "").trim();
  if (confirm.toUpperCase() !== "DELETE") {
    showDeleteStatus("Type DELETE to confirm.", "error");
    return;
  }
  deleteBtn.disabled = true;
  deleteBtn.textContent = "Deleting…";
  showDeleteStatus("", "");
  deleteStatus?.classList.add("hidden");
  try {
    const resp = await fetch("/account/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const detail = data.detail;
      const message =
        typeof detail === "string"
          ? detail
          : detail?.message || "Delete failed";
      throw new Error(message);
    }
    window.location.href = data.redirect || "/";
  } catch (err) {
    deleteStatus?.classList.remove("hidden");
    showDeleteStatus(err.message || "Could not delete account", "error");
    deleteBtn.disabled = false;
    deleteBtn.textContent = "Delete my account";
  }
});