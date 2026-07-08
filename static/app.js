const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const fileSelectedEl = document.getElementById("file-selected");
const uploadForm = document.getElementById("upload-form");
const uploadStatus = document.getElementById("upload-status");
const uploadBtn = document.getElementById("upload-btn");
const uploadSection = document.getElementById("upload-section");
const uploadProgress = document.getElementById("upload-progress");
const uploadProgressStep = document.getElementById("upload-progress-step");
const dropZoneOverlay = document.getElementById("drop-zone-overlay");

const UPLOAD_STEPS = [
  "Reading screenshots…",
  "Extracting names, employers, and bios…",
  "Running trust vetting on photos…",
  "Searching public footprint…",
  "Ranking compatibility for you…",
];

const AGENT_STEPS = [
  "Ingesting your attachments…",
  "Re-running trust signals…",
  "Searching Brave for public matches…",
  "Updating your vet report…",
];

let uploadInFlight = false;
let uploadStepTimer = null;
let uploadStepIndex = 0;

function startStepCycler(stepEl, steps) {
  if (!stepEl || !steps.length) return null;
  let index = 0;
  stepEl.textContent = steps[0];
  stepEl.style.opacity = "1";
  return window.setInterval(() => {
    index = (index + 1) % steps.length;
    stepEl.style.opacity = "0";
    window.setTimeout(() => {
      stepEl.textContent = steps[index];
      stepEl.style.opacity = "1";
    }, 180);
  }, 2800);
}

function startUploadProgress(fileCount) {
  uploadInFlight = true;
  uploadSection?.classList.add("processing");
  uploadProgress?.classList.remove("hidden");
  dropZoneOverlay?.classList.remove("hidden");
  uploadBtn.disabled = true;
  uploadBtn.setAttribute("aria-busy", "true");
  uploadBtn.textContent = "Analyzing…";
  if (fileInput) fileInput.disabled = true;
  uploadStepIndex = 0;
  if (uploadStepTimer) clearInterval(uploadStepTimer);
  if (uploadProgressStep) uploadProgressStep.textContent = "Uploading screenshots…";
  showStatus(
    `Processing ${fileCount} screenshot${fileCount === 1 ? "" : "s"} — vision, trust, and ranking in flight.`,
    "processing"
  );
}

const FILE_STAGE_LABELS = {
  queued: "waiting for a slot…",
  analyzing: "reading profile + photo forensics…",
  scoring: "scoring trust + fit for you…",
  done: "done",
  failed: "failed",
};
const FILE_STAGE_FRACTION = { queued: 0, analyzing: 0.45, scoring: 0.85, done: 1, failed: 1 };

function renderJobProgress(job) {
  const files = job.files || [];
  const total = files.length || 1;
  const progress =
    files.reduce((sum, f) => sum + (FILE_STAGE_FRACTION[f.stage] ?? 0), 0) / total;
  const track = uploadProgress?.querySelector(".upload-progress-track");
  const bar = uploadProgress?.querySelector(".upload-progress-bar");
  track?.classList.add("real");
  if (bar) bar.style.width = `${Math.round(6 + progress * 94)}%`;
  if (!uploadProgressStep) return;
  const active = files.find((f) => f.stage === "analyzing" || f.stage === "scoring");
  if (active) {
    const n = files.indexOf(active) + 1;
    uploadProgressStep.textContent =
      total > 1
        ? `Screenshot ${n} of ${total} — ${FILE_STAGE_LABELS[active.stage]}`
        : FILE_STAGE_LABELS[active.stage];
  } else if (job.status === "running" && job.message) {
    uploadProgressStep.textContent = job.message;
  }
}

function pollUploadJob(jobId) {
  if (uploadStepTimer) {
    clearInterval(uploadStepTimer);
    uploadStepTimer = null;
  }
  let misses = 0;
  const poll = async () => {
    let job = null;
    try {
      const resp = await fetch(`/toolbox/upload-jobs/${jobId}`, {
        credentials: "same-origin",
      });
      if (!resp.ok) throw new Error(`status ${resp.status}`);
      job = await resp.json();
      misses = 0;
    } catch (_) {
      misses += 1;
      if (misses >= 4) {
        stopUploadProgress(true);
        showStatus(
          "Analysis was interrupted — refresh to see any completed profiles.",
          "error"
        );
        return;
      }
      setTimeout(poll, 3000);
      return;
    }
    renderJobProgress(job);
    if (job.status !== "done" && job.status !== "error") {
      setTimeout(poll, 2500);
      return;
    }
    stopUploadProgress(true);
    if (fileInput) {
      fileInput.value = "";
      updateFileSelection();
    }
    if (job.status === "error") {
      showStatus(job.error || "Analysis failed.", "error");
      return;
    }
    showStatus(job.message || "Analysis complete.", "ok");
    const doneFiles = (job.files || []).filter(
      (f) => f.stage === "done" && f.profile_id
    );
    const seen = new Set();
    let newProfiles = 0;
    for (const f of doneFiles) {
      if (seen.has(f.profile_id)) continue;
      seen.add(f.profile_id);
      if (!f.merged) newProfiles += 1;
      await refreshCard(f.profile_id, { highlight: true });
    }
    const statEl = document.querySelector(".stats .stat-num");
    if (statEl && newProfiles && /^\d+$/.test(statEl.textContent.trim())) {
      statEl.textContent = String(Number(statEl.textContent.trim()) + newProfiles);
    }
  };
  setTimeout(poll, 1200);
}

function stopUploadProgress(resetButton = true) {
  uploadInFlight = false;
  if (uploadStepTimer) {
    clearInterval(uploadStepTimer);
    uploadStepTimer = null;
  }
  uploadSection?.classList.remove("processing");
  uploadProgress?.classList.add("hidden");
  dropZoneOverlay?.classList.add("hidden");
  uploadBtn.removeAttribute("aria-busy");
  if (fileInput) fileInput.disabled = false;
  if (resetButton) {
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Analyze & Rank";
  }
}

function updateFileSelection() {
  if (!fileInput || !fileSelectedEl) return;
  const count = fileInput.files?.length || 0;
  if (!count) {
    fileSelectedEl.textContent = "";
    fileSelectedEl.classList.add("hidden");
    return;
  }
  const names = [...fileInput.files].map((f) => f.name).join(", ");
  fileSelectedEl.textContent =
    count === 1 ? `Selected: ${names}` : `${count} files selected: ${names}`;
  fileSelectedEl.classList.remove("hidden");
}

if (fileInput) {
  fileInput.addEventListener("change", updateFileSelection);
}

if (dropZone && fileInput) {
  dropZone.addEventListener("click", (e) => {
    if (e.target === fileInput) return;
    fileInput.click();
  });

  ["dragenter", "dragover"].forEach((evt) => {
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((evt) => {
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
    });
  });
  dropZone.addEventListener("drop", (e) => {
    if (!e.dataTransfer?.files?.length) return;
    const dt = new DataTransfer();
    for (const file of e.dataTransfer.files) {
      if (file.type.startsWith("image/")) dt.items.add(file);
    }
    if (dt.files.length) {
      fileInput.files = dt.files;
      updateFileSelection();
    }
  });
}

function parseErrorDetail(data) {
  if (!data?.detail) return "Upload failed";
  if (typeof data.detail === "string") return data.detail;
  if (typeof data.detail === "object" && data.detail.error === "capacity") {
    return data.detail.message || "We're scaling up — please try again in a few minutes.";
  }
  if (typeof data.detail === "object" && data.detail.error === "insufficient_tokens") {
    return `You need ${data.detail.required} tokens for this (balance: ${data.detail.balance}).`;
  }
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  }
  return String(data.detail);
}

function errorCodeOf(data) {
  const detail = data?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    return detail.error || null;
  }
  return null;
}

if (uploadForm && fileInput) {
  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (uploadInFlight) return;
    if (!fileInput.files.length) {
      showStatus("Select at least one screenshot.", "error");
      return;
    }

    const fileCount = fileInput.files.length;
    startUploadProgress(fileCount);

    const formData = new FormData();
    for (const file of fileInput.files) {
      formData.append("files", file);
    }

    try {
      const resp = await fetch("/toolbox/upload-screenshots", {
        method: "POST",
        body: formData,
        credentials: "same-origin",
      });
      let data = {};
      try {
        data = await resp.json();
      } catch (_) {
        /* non-JSON error body */
      }
      if (!resp.ok) {
        const error = new Error(parseErrorDetail(data) || `Upload failed (${resp.status})`);
        error.code = errorCodeOf(data);
        throw error;
      }
      // 202 accepted — poll the job for real per-file progress
      pollUploadJob(data.job_id);
    } catch (err) {
      const isCapacity =
        err.code === "capacity" ||
        String(err.message || "").includes("influx of new users");
      const link =
        err.code === "insufficient_tokens"
          ? { href: "/billing", label: "Add tokens" }
          : null;
      showStatus(err.message, isCapacity ? "capacity" : "error", link);
      stopUploadProgress(true);
    }
  });
}

function updateCompareBar(changed) {
  const checked = [...document.querySelectorAll(".compare-checkbox:checked")];
  if (checked.length > 3 && changed) {
    changed.checked = false;
    showToast("Compare up to 3 profiles at a time", "error");
    return updateCompareBar();
  }
  let bar = document.getElementById("compare-bar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "compare-bar";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn primary";
    btn.id = "compare-go";
    btn.addEventListener("click", () => {
      const ids = [...document.querySelectorAll(".compare-checkbox:checked")].map(
        (c) => c.dataset.profileId
      );
      if (ids.length >= 2) {
        window.location.href = `/dashboard/compare?ids=${ids.join(",")}`;
      }
    });
    bar.appendChild(btn);
    document.body.appendChild(bar);
  }
  const btn = document.getElementById("compare-go");
  if (checked.length >= 2) {
    btn.textContent = `Compare ${checked.length} profiles →`;
    bar.classList.add("visible");
  } else {
    bar.classList.remove("visible");
  }
}

async function startRename(profileId) {
  const h3 = document.getElementById(`card-title-${profileId}`);
  if (!h3 || h3.dataset.editing) return;
  h3.dataset.editing = "1";
  const current = h3.textContent.trim();
  const input = document.createElement("input");
  input.type = "text";
  input.className = "rename-input";
  input.value = current;
  input.maxLength = 80;
  h3.replaceWith(input);
  input.focus();
  input.select();

  let done = false;
  const finish = async (save) => {
    if (done) return;
    done = true;
    const value = input.value.trim();
    input.replaceWith(h3);
    delete h3.dataset.editing;
    if (!save || value === current) return;
    try {
      const resp = await fetch(`/profiles/${profileId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ display_name: value }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(parseErrorDetail(data) || "Rename failed");
      if (data.display_name) {
        h3.textContent = data.display_name;
        showToast("Profile renamed", "ok");
      } else {
        // cleared — card falls back to the extracted name
        await refreshCard(profileId);
        showToast("Name reset", "ok");
      }
    } catch (err) {
      showToast(err.message, "error");
    }
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      finish(true);
    }
    if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
}

async function saveNote(profileId, rerank) {
  const input = document.getElementById(`note-input-${profileId}`);
  const note = input?.value?.trim() || "";
  if (!note) {
    showToast("Write a note first", "error");
    return;
  }
  const body = new FormData();
  body.append("note", note);
  body.append("rerank", rerank ? "true" : "false");
  try {
    const resp = await fetch(`/profiles/${profileId}/evidence/note`, {
      method: "POST",
      body,
      credentials: "same-origin",
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const error = new Error(parseErrorDetail(data) || "Saving the note failed");
      error.code = errorCodeOf(data);
      throw error;
    }
    showToast(
      rerank ? "Note saved — ranking refreshed" : "Note saved", "ok"
    );
    await refreshCard(profileId);
  } catch (err) {
    showToast(err.message, "error");
  }
}

function showToast(msg, type = "ok") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("visible"));
  setTimeout(() => {
    toast.classList.remove("visible");
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

async function refreshCard(profileId, { highlight = false } = {}) {
  try {
    const resp = await fetch(`/dashboard/cards/${profileId}`, {
      credentials: "same-origin",
    });
    if (!resp.ok) return false;
    const html = await resp.text();
    const tpl = document.createElement("template");
    tpl.innerHTML = html.trim();
    const fresh = tpl.content.querySelector("article.card");
    if (!fresh) return false;
    const existing = document.querySelector(
      `article.card[data-profile-id="${profileId}"]`
    );
    if (existing) {
      existing.replaceWith(fresh);
    } else {
      let cards = document.querySelector(".cards");
      if (!cards) {
        document.querySelector(".shortlist .empty")?.remove();
        cards = document.createElement("div");
        cards.className = "cards";
        document.querySelector(".shortlist")?.appendChild(cards);
      }
      cards.prepend(fresh);
    }
    if (highlight) {
      fresh.classList.add("card-new");
      setTimeout(() => fresh.classList.remove("card-new"), 2400);
    }
    initAgentPanels();
    return true;
  } catch (_) {
    return false;
  }
}

function showStatus(msg, type, link) {
  if (!uploadStatus) return;
  uploadStatus.textContent = msg;
  uploadStatus.className = "status" + (type ? ` ${type}` : "");
  uploadStatus.classList.remove("hidden");
  uploadStatus.style.whiteSpace = "pre-wrap";
  if (link && link.href) {
    const a = document.createElement("a");
    a.href = link.href;
    a.textContent = `${link.label} →`;
    a.className = "status-link";
    uploadStatus.appendChild(a);
  }
}

const agentFileStore = new Map();
const agentUrlStore = new Map();
const agentPreviewUrls = new Map();
const URL_IN_TEXT_RE = /https?:\/\/[^\s<>"']+/gi;

function getAgentFiles(profileId) {
  return agentFileStore.get(String(profileId)) || [];
}

function getAgentUrls(profileId) {
  return agentUrlStore.get(String(profileId)) || [];
}

function normalizeAgentUrl(url) {
  return (url || "").trim().replace(/[.,);>\]"']+$/, "");
}

function extractUrlsFromText(text) {
  if (!text) return [];
  const seen = new Set();
  const urls = [];
  for (const match of text.matchAll(URL_IN_TEXT_RE)) {
    const url = normalizeAgentUrl(match[0]);
    if (url && !seen.has(url)) {
      seen.add(url);
      urls.push(url);
    }
  }
  return urls;
}

function addAgentUrls(profileId, urlList) {
  const urls = [...urlList].map(normalizeAgentUrl).filter(Boolean);
  if (!urls.length) return false;
  const key = String(profileId);
  const merged = [...getAgentUrls(profileId)];
  for (const url of urls) {
    if (!merged.includes(url)) merged.push(url);
  }
  agentUrlStore.set(key, merged);
  renderAgentAttachments(profileId);
  return true;
}

function removeAgentUrl(profileId, index) {
  const key = String(profileId);
  const urls = [...getAgentUrls(profileId)];
  urls.splice(index, 1);
  agentUrlStore.set(key, urls);
  renderAgentAttachments(profileId);
}

function revokeAgentPreviews(profileId) {
  const urls = agentPreviewUrls.get(String(profileId)) || [];
  for (const url of urls) URL.revokeObjectURL(url);
  agentPreviewUrls.set(String(profileId), []);
}

function syncAgentFileInput(profileId) {
  const input = document.getElementById(`agent-files-${profileId}`);
  if (!input) return;
  const dt = new DataTransfer();
  for (const file of getAgentFiles(profileId)) dt.items.add(file);
  input.files = dt.files;
}

function renderAgentAttachments(profileId) {
  const container = document.getElementById(`agent-attachments-${profileId}`);
  if (!container) return;
  revokeAgentPreviews(profileId);
  const files = getAgentFiles(profileId);
  const socialUrls = getAgentUrls(profileId);
  container.innerHTML = "";
  if (!files.length && !socialUrls.length) {
    container.classList.add("hidden");
    return;
  }
  container.classList.remove("hidden");
  const urls = [];
  socialUrls.forEach((url, index) => {
    const chip = document.createElement("div");
    chip.className = "agent-attachment-chip url-chip";
    const link = document.createElement("a");
    link.className = "agent-url-link";
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = url.replace(/^https?:\/\/(www\.)?/, "");
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "agent-attachment-remove";
    remove.setAttribute("aria-label", "Remove link");
    remove.textContent = "×";
    remove.addEventListener("click", () => removeAgentUrl(profileId, index));
    chip.appendChild(link);
    chip.appendChild(remove);
    container.appendChild(chip);
  });
  files.forEach((file, index) => {
    const chip = document.createElement("div");
    chip.className = "agent-attachment-chip";
    const img = document.createElement("img");
    const url = URL.createObjectURL(file);
    urls.push(url);
    img.src = url;
    img.alt = file.name || `Attachment ${index + 1}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "agent-attachment-remove";
    remove.setAttribute("aria-label", "Remove image");
    remove.textContent = "×";
    remove.addEventListener("click", () => removeAgentFile(profileId, index));
    chip.appendChild(img);
    chip.appendChild(remove);
    container.appendChild(chip);
  });
  agentPreviewUrls.set(String(profileId), urls);
}

function addAgentFiles(profileId, fileList) {
  const images = [...fileList].filter((f) => f.type.startsWith("image/"));
  if (!images.length) return false;
  const key = String(profileId);
  agentFileStore.set(key, [...getAgentFiles(profileId), ...images]);
  syncAgentFileInput(profileId);
  renderAgentAttachments(profileId);
  return true;
}

function removeAgentFile(profileId, index) {
  const key = String(profileId);
  const files = [...getAgentFiles(profileId)];
  files.splice(index, 1);
  agentFileStore.set(key, files);
  syncAgentFileInput(profileId);
  renderAgentAttachments(profileId);
}

function extractUrlsFromDataTransfer(dt) {
  if (!dt) return [];
  const urls = [];
  const uriList = dt.getData("text/uri-list");
  if (uriList) urls.push(...extractUrlsFromText(uriList));
  const plain = dt.getData("text/plain");
  if (plain) urls.push(...extractUrlsFromText(plain));
  const seen = new Set();
  return urls.filter((url) => {
    if (seen.has(url)) return false;
    seen.add(url);
    return true;
  });
}

function extractImagesFromDataTransfer(dt) {
  if (!dt) return [];
  const files = [];
  if (dt.files?.length) {
    for (const file of dt.files) {
      if (file.type.startsWith("image/")) files.push(file);
    }
  }
  if (!files.length && dt.items) {
    for (const item of dt.items) {
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
  }
  return files;
}

function extractImagesFromClipboard(clipboardData) {
  if (!clipboardData?.items) return [];
  const files = [];
  for (const item of clipboardData.items) {
    if (item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) files.push(file);
    }
  }
  return files;
}

function initAgentPanels() {
  document.querySelectorAll(".agent-panel").forEach((panel) => {
    const profileId = panel.dataset.profileId;
    if (!profileId) return;
    if (panel.dataset.bound === "1") return;
    panel.dataset.bound = "1";

    const compose = panel.querySelector(".agent-compose");
    const textarea = panel.querySelector(".agent-prompt");
    const fileInput = panel.querySelector(".agent-files-input");

    fileInput?.addEventListener("change", () => {
      if (fileInput.files?.length) addAgentFiles(profileId, fileInput.files);
    });

    textarea?.addEventListener("paste", (e) => {
      const images = extractImagesFromClipboard(e.clipboardData);
      const pastedUrls = extractUrlsFromText(e.clipboardData?.getData("text/plain") || "");
      if (images.length) {
        e.preventDefault();
        addAgentFiles(profileId, images);
      }
      if (pastedUrls.length) addAgentUrls(profileId, pastedUrls);
    });

    if (compose) {
      ["dragenter", "dragover"].forEach((evt) => {
        compose.addEventListener(evt, (e) => {
          e.preventDefault();
          compose.classList.add("dragover");
        });
      });
      ["dragleave", "drop"].forEach((evt) => {
        compose.addEventListener(evt, (e) => {
          e.preventDefault();
          compose.classList.remove("dragover");
        });
      });
      compose.addEventListener("drop", (e) => {
        const images = extractImagesFromDataTransfer(e.dataTransfer);
        const droppedUrls = extractUrlsFromDataTransfer(e.dataTransfer);
        if (images.length) addAgentFiles(profileId, images);
        if (droppedUrls.length) addAgentUrls(profileId, droppedUrls);
      });
    }
  });
}

initAgentPanels();

const deleteArmTimers = new Map();

function disarmDeleteButton(btn, profileId) {
  btn.dataset.armed = "";
  btn.textContent = "×";
  btn.classList.remove("armed");
  btn.title = "Delete this profile workup";
  deleteArmTimers.delete(profileId);
}

async function deleteProfile(profileId) {
  const card = document.querySelector(`[data-profile-id="${profileId}"]`);
  const btn = card ? card.querySelector(".btn-delete") : null;
  if (btn && !btn.dataset.armed) {
    btn.dataset.armed = "1";
    btn.textContent = "Delete?";
    btn.classList.add("armed");
    btn.title = "Click again to permanently delete this workup";
    deleteArmTimers.set(
      profileId,
      setTimeout(() => disarmDeleteButton(btn, profileId), 4000)
    );
    return;
  }
  const timer = deleteArmTimers.get(profileId);
  if (timer) {
    clearTimeout(timer);
    deleteArmTimers.delete(profileId);
  }
  try {
    const resp = await fetch(`/profiles/${profileId}`, {
      method: "DELETE",
      credentials: "same-origin",
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(parseErrorDetail(data) || "Delete failed");
    if (card) {
      card.style.opacity = "0";
      card.style.transform = "scale(0.98)";
      setTimeout(() => {
        card.remove();
        if (!document.querySelector(".cards .card")) {
          const cards = document.querySelector(".cards");
          if (cards) {
            const empty = document.createElement("p");
            empty.className = "empty";
            empty.textContent =
              "No profiles yet — upload a screenshot to get started.";
            cards.replaceWith(empty);
          }
        }
      }, 200);
    }
    showToast("Profile removed", "ok");
  } catch (err) {
    showStatus(err.message, "error");
  }
}

function agentPanel(profileId) {
  return document.querySelector(`.agent-panel[data-profile-id="${profileId}"]`);
}

function ensureAgentBanner(panel) {
  if (!panel) return null;
  let banner = panel.querySelector(".agent-processing-banner");
  if (!banner) {
    banner = document.createElement("p");
    banner.className = "agent-processing-banner hidden";
    banner.setAttribute("role", "status");
    banner.setAttribute("aria-live", "polite");
    panel.appendChild(banner);
  }
  return banner;
}

let agentInFlight = new Set();
let agentStepTimers = new Map();

async function submitAgent(profileId) {
  if (agentInFlight.has(String(profileId))) return;

  const promptEl = document.getElementById(`agent-prompt-${profileId}`);
  const prompt = promptEl?.value?.trim() || "";
  const files = getAgentFiles(profileId);
  const socialUrls = getAgentUrls(profileId);
  if (!prompt && !files.length && !socialUrls.length) {
    showStatus("Enter a prompt, social link, or attach images for the agent.", "error");
    return;
  }

  const panel = agentPanel(profileId);
  const banner = ensureAgentBanner(panel);
  const runBtn = panel?.querySelector(".agent-row .btn.primary");
  const key = String(profileId);
  agentInFlight.add(key);
  panel?.classList.add("processing");
  if (runBtn) {
    runBtn.disabled = true;
    runBtn.setAttribute("aria-busy", "true");
    runBtn.textContent = "Working…";
  }
  if (banner) {
    banner.classList.remove("hidden");
    const timer = startStepCycler(banner, AGENT_STEPS);
    if (timer) agentStepTimers.set(key, timer);
  }

  const body = new FormData();
  body.append("prompt", prompt);
  for (const file of files) body.append("files", file);
  for (const url of socialUrls) body.append("urls", url);

  showStatus("Agent running — trust vet and public search in progress…", "processing");
  try {
    const resp = await fetch(`/profiles/${profileId}/agent`, {
      method: "POST",
      body,
      credentials: "same-origin",
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(parseErrorDetail(data) || "Agent failed");
    const acts = (data.actions || []).join(", ");
    showStatus(
      `Agent done (+${data.tokens_charged} tokens, ${data.tokens_spent_total} total on profile). ${acts}. Balance: ${data.balance}`,
      "ok"
    );
    await refreshCard(profileId, { highlight: true });
    showToast("Agent findings merged into the card", "ok");
  } catch (err) {
    showStatus(err.message, "error");
  } finally {
    const timer = agentStepTimers.get(key);
    if (timer) clearInterval(timer);
    agentStepTimers.delete(key);
    agentInFlight.delete(key);
    panel?.classList.remove("processing");
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.removeAttribute("aria-busy");
      runBtn.textContent = "Run agent";
    }
    banner?.classList.add("hidden");
  }
}

async function vetTopCandidates() {
  const btn = document.getElementById("vet-top-btn");
  const originalLabel = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Vetting…";
  }
  try {
    const resp = await fetch("/profiles/vet-top", {
      method: "POST",
      credentials: "same-origin",
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(parseErrorDetail(data) || "Vet top failed");
    showStatus(
      `Deep vetting queued for top ${data.length} candidate(s) — cards update automatically as results land.`,
      "ok"
    );
    const ids = data.map((r) => r.profile_id).filter(Boolean);
    [12000, 32000].forEach((delay) =>
      setTimeout(() => ids.forEach((id) => refreshCard(id)), delay)
    );
  } catch (err) {
    showStatus(err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalLabel;
    }
  }
}

async function shareAnalysis(rankingId) {
  try {
    const resp = await fetch(`/profiles/rankings/${rankingId}/share`, {
      credentials: "same-origin",
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(parseErrorDetail(data) || "Share failed");

    const shareData = {
      title: data.title || "MatchForge analysis",
      text: data.text,
      url: data.share_url,
    };

    if (navigator.share) {
      try {
        await navigator.share(shareData);
        showStatus("Shared", "ok");
        return;
      } catch (err) {
        if (err.name === "AbortError") return;
      }
    }

    await navigator.clipboard.writeText(data.text);
    showStatus("Analysis copied — includes your referral link", "ok");
  } catch (err) {
    showStatus(err.message, "error");
  }
}

function copyReferralLink() {
  const input = document.getElementById("referral-url");
  if (!input) return;
  input.select();
  input.setSelectionRange(0, input.value.length);
  navigator.clipboard.writeText(input.value).then(() => {
    showStatus("Referral link copied", "ok");
  }).catch(() => {
    showStatus("Copy failed — select the link manually", "error");
  });
}

// --- X verification (agentic Grok + official X API) ---

const X_VERIFY_STEPS = [
  "Looking up the X account (official API)…",
  "Reading recent public posts…",
  "Grok is searching X for evidence…",
  "Cross-checking dating-profile claims…",
  "Comparing photos across platforms…",
  "Scoring social proof…",
];

const xVerifyInFlight = new Set();

function xStatusEl(profileId) {
  return document.getElementById(`x-verify-status-${profileId}`);
}

function showXVerifyForm(profileId) {
  document.getElementById(`x-verify-form-${profileId}`)?.classList.remove("hidden");
}

function startXProgress(el, steps) {
  if (!el) return null;
  el.classList.remove("hidden", "error");
  el.classList.add("processing");
  return startStepCycler(el, steps);
}

async function submitXVerify(profileId) {
  const key = String(profileId);
  if (xVerifyInFlight.has(key)) return;

  const handleEl = document.getElementById(`x-handle-${profileId}`);
  const consentEl = document.getElementById(`x-consent-${profileId}`);
  const handle = handleEl?.value?.trim() || "";
  if (!handle) {
    showStatus("Enter an X handle (@name) or x.com link.", "error");
    return;
  }
  if (!consentEl?.checked) {
    showStatus("Please confirm the public-data acknowledgement first.", "error");
    return;
  }

  const statusEl = xStatusEl(profileId);
  const btn = document.querySelector(
    `#x-verify-form-${profileId} .btn.primary`
  );
  xVerifyInFlight.add(key);
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Investigating…";
  }
  const timer = startXProgress(statusEl, X_VERIFY_STEPS);

  const body = new FormData();
  body.append("x_username", handle);
  body.append("consent", "true");

  try {
    const resp = await fetch(`/profiles/${profileId}/x-verify`, {
      method: "POST",
      body,
      credentials: "same-origin",
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(parseErrorDetail(data) || "Verification failed");
    const score = data.report?.x_social_proof_score;
    showStatus(
      `X verification complete — ${data.report?.verdict?.replaceAll("_", " ")}` +
        (score != null ? ` · social proof ${Math.round(score)}/100` : "") +
        ` (+${data.tokens_charged} tokens). Balance: ${data.balance}`,
      "ok"
    );
    await refreshCard(profileId, { highlight: true });
  } catch (err) {
    showStatus(err.message, "error");
    if (statusEl) {
      statusEl.textContent = err.message;
      statusEl.classList.remove("processing");
      statusEl.classList.add("error");
    }
  } finally {
    if (timer) clearInterval(timer);
    xVerifyInFlight.delete(key);
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Verify on X";
    }
  }
}

async function xLookup() {
  const handleEl = document.getElementById("x-lookup-handle");
  const consentEl = document.getElementById("x-lookup-consent");
  const btn = document.getElementById("x-lookup-btn");
  const statusEl = document.getElementById("x-lookup-status");
  const handle = handleEl?.value?.trim() || "";
  if (!handle) {
    showStatus("Enter an X handle (@name) or x.com link.", "error");
    return;
  }
  if (!consentEl?.checked) {
    showStatus("Please confirm the public-data acknowledgement first.", "error");
    return;
  }
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Investigating…";
  }
  const timer = startXProgress(statusEl, X_VERIFY_STEPS);

  const body = new FormData();
  body.append("x_username", handle);
  body.append("consent", "true");

  try {
    const resp = await fetch("/profiles/x-lookup", {
      method: "POST",
      body,
      credentials: "same-origin",
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(parseErrorDetail(data) || "Lookup failed");
    showStatus(
      `@${data.report?.handle} verified — ${data.report?.verdict?.replaceAll("_", " ")}. New tile added to your shortlist.`,
      "ok"
    );
    if (data.profile_id) {
      await refreshCard(data.profile_id, { highlight: true });
      if (handleEl) handleEl.value = "";
      if (statusEl) {
        statusEl.classList.add("hidden");
        statusEl.classList.remove("processing");
      }
    } else {
      setTimeout(() => window.location.reload(), 1600);
    }
  } catch (err) {
    showStatus(err.message, "error");
    if (statusEl) {
      statusEl.textContent = err.message;
      statusEl.classList.remove("processing", "hidden");
      statusEl.classList.add("error");
    }
  } finally {
    if (timer) clearInterval(timer);
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Verify on X";
    }
  }
}

async function getVerificationQuestions(profileId) {
  const container = document.getElementById(`x-questions-${profileId}`);
  if (container) container.innerHTML = "<p class='x-questions-title'>Generating questions from their public X activity…</p>";
  try {
    const resp = await fetch(`/profiles/${profileId}/x-verify/questions`, {
      method: "POST",
      body: new FormData(),
      credentials: "same-origin",
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(parseErrorDetail(data) || "Question generation failed");
    if (container) {
      const items = (data.questions || [])
        .map(
          (q) =>
            `<li><span class="xq-question">${q.question}</span>` +
            (q.expected_signal
              ? `<span class="xq-signal">Genuine answer: ${q.expected_signal}</span>`
              : "") +
            `</li>`
        )
        .join("");
      container.innerHTML = items
        ? `<p class="x-questions-title">Ask them (only the real owner can answer):</p><ol>${items}</ol>`
        : "<p class='x-questions-title'>No questions could be grounded in their public activity.</p>";
    }
    showStatus(`Verification questions ready (+${data.tokens_charged} tokens).`, "ok");
  } catch (err) {
    if (container) container.innerHTML = "";
    showStatus(err.message, "error");
  }
}

async function shareXVerification(profileId) {
  try {
    const resp = await fetch(`/profiles/${profileId}/x-verify/share`, {
      method: "POST",
      credentials: "same-origin",
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(parseErrorDetail(data) || "Share failed");

    if (data.intent_url) {
      window.open(data.intent_url, "_blank", "noopener");
    }
    await navigator.clipboard.writeText(data.share_url).catch(() => {});
    showStatus("Verification report link copied — badge ready to post on X.", "ok");
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function feedback(rankingId, type) {
  const card = document.querySelector(
    `article.card[data-ranking-id="${rankingId}"]`
  );
  try {
    const resp = await fetch("/profiles/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ ranking_id: rankingId, feedback: type }),
    });
    if (!resp.ok) throw new Error("Feedback failed");
    const selector = { like: ".like", dislike: ".dislike", superlike: ".super" }[type];
    card?.querySelectorAll(".actions .btn").forEach((b) => b.classList.remove("active"));
    if (selector) card?.querySelector(`.actions ${selector}`)?.classList.add("active");
    const label = {
      like: "Liked — boosted in your shortlist",
      dislike: "Passed — lowered in your shortlist",
      superlike: "Pinned to the top of your shortlist",
    }[type];
    showToast(label || "Saved", "ok");
  } catch (err) {
    showToast(err.message, "error");
  }
}