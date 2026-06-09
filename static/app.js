const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const fileSelectedEl = document.getElementById("file-selected");
const uploadForm = document.getElementById("upload-form");
const uploadStatus = document.getElementById("upload-status");
const uploadBtn = document.getElementById("upload-btn");

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
    return `Need ${data.detail.required} tokens (balance: ${data.detail.balance}). Buy tokens coming soon.`;
  }
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  }
  return String(data.detail);
}

if (uploadForm && fileInput) {
  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!fileInput.files.length) {
      showStatus("Select at least one screenshot.", "error");
      return;
    }

    uploadBtn.disabled = true;
    uploadBtn.textContent = "Analyzing…";
    showStatus("Running Grok vision analysis + ranking…", "");

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
      if (!resp.ok) throw new Error(parseErrorDetail(data) || `Upload failed (${resp.status})`);
      let statusMsg = data.message || "Upload complete.";
      if (data.trust_breakdown?.length) {
        const lines = data.trust_breakdown.map((t, i) => {
          const auth = t.authenticity_score != null ? `${Math.round(t.authenticity_score)}% auth` : "";
          const nat = t.naturalness_score != null ? `${Math.round(t.naturalness_score)}% natural` : "";
          const cat = t.catfish_risk_score != null ? `${Math.round(t.catfish_risk_score)}% catfish` : "";
          const bot = t.bot_risk_score != null ? `${Math.round(t.bot_risk_score)}% bot` : "";
          const note = t.trust_explanation ? ` — ${t.trust_explanation}` : "";
          return `#${i + 1}: ${[auth, nat, cat, bot].filter(Boolean).join(", ")}${note}`;
        });
        statusMsg += "\n" + lines.join("\n");
      }
      if (data.profiles_merged) {
        statusMsg += `\n(${data.profiles_merged} existing profile(s) enriched — no duplicate tiles)`;
      }
      showStatus(statusMsg, "ok");
      setTimeout(() => window.location.reload(), 2500);
    } catch (err) {
      const isCapacity = String(err.message || "").includes("influx of new users");
      showStatus(err.message, isCapacity ? "capacity" : "error");
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Analyze & Rank";
    }
  });
}

function showStatus(msg, type) {
  if (!uploadStatus) return;
  uploadStatus.textContent = msg;
  uploadStatus.className = "status" + (type ? ` ${type}` : "");
  uploadStatus.classList.remove("hidden");
  uploadStatus.style.whiteSpace = "pre-wrap";
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

async function deleteProfile(profileId) {
  const card = document.querySelector(`[data-profile-id="${profileId}"]`);
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
          window.location.reload();
        }
      }, 200);
    }
    showStatus("Profile removed.", "ok");
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function submitAgent(profileId) {
  const promptEl = document.getElementById(`agent-prompt-${profileId}`);
  const prompt = promptEl?.value?.trim() || "";
  const files = getAgentFiles(profileId);
  const socialUrls = getAgentUrls(profileId);
  if (!prompt && !files.length && !socialUrls.length) {
    showStatus("Enter a prompt, social link, or attach images for the agent.", "error");
    return;
  }

  const body = new FormData();
  body.append("prompt", prompt);
  for (const file of files) body.append("files", file);
  for (const url of socialUrls) body.append("urls", url);

  showStatus("Agent running…", "");
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
    setTimeout(() => window.location.reload(), 1800);
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function vetTopCandidates() {
  const btn = document.getElementById("vet-top-btn");
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
    showStatus(`Deep vetting queued for top ${data.length} candidate(s)`, "ok");
    setTimeout(() => window.location.reload(), 2500);
  } catch (err) {
    showStatus(err.message, "error");
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Vet top 5";
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

async function feedback(rankingId, type) {
  try {
    const resp = await fetch("/profiles/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ ranking_id: rankingId, feedback: type }),
    });
    if (!resp.ok) throw new Error("Feedback failed");
    window.location.reload();
  } catch (err) {
    showStatus(err.message, "error");
  }
}