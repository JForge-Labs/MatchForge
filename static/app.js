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
      showStatus(err.message, "error");
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

async function submitAgent(profileId) {
  const promptEl = document.getElementById(`agent-prompt-${profileId}`);
  const filesEl = document.getElementById(`agent-files-${profileId}`);
  const prompt = promptEl?.value?.trim() || "";
  const files = filesEl?.files;
  if (!prompt && (!files || !files.length)) {
    showStatus("Enter a prompt or attach images for the agent.", "error");
    return;
  }

  const body = new FormData();
  body.append("prompt", prompt);
  if (files) {
    for (const file of files) body.append("files", file);
  }

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