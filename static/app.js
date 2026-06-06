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
      showStatus(data.message || "Upload complete.", "ok");
      setTimeout(() => window.location.reload(), 1500);
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
}

async function enrichProfile(profileId) {
  try {
    const resp = await fetch("/profiles/enrich", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ profile_ids: [profileId] }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(parseErrorDetail(data) || "Vetting failed");
    showStatus(`Deep vetting queued for profile ${profileId}`, "ok");
    setTimeout(() => window.location.reload(), 2000);
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

async function addNote(profileId) {
  const note = window.prompt("Add a private note about this person (3 tokens + rank refresh):");
  if (!note || !note.trim()) return;
  try {
    const body = new FormData();
    body.append("note", note.trim());
    const resp = await fetch(`/profiles/${profileId}/evidence/note`, {
      method: "POST",
      body,
      credentials: "same-origin",
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(parseErrorDetail(data) || "Note failed");
    showStatus(`Note saved. Balance: ${data.balance} tokens`, "ok");
    setTimeout(() => window.location.reload(), 1200);
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function addMessageSnip(profileId) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.onchange = async () => {
    if (!input.files?.length) return;
    const body = new FormData();
    body.append("file", input.files[0]);
    showStatus("Analyzing message screenshot…", "");
    try {
      const resp = await fetch(`/profiles/${profileId}/evidence/screenshot`, {
        method: "POST",
        body,
        credentials: "same-origin",
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(parseErrorDetail(data) || "Screenshot failed");
      showStatus(`Message snip added. Balance: ${data.balance} tokens`, "ok");
      setTimeout(() => window.location.reload(), 1200);
    } catch (err) {
      showStatus(err.message, "error");
    }
  };
  input.click();
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