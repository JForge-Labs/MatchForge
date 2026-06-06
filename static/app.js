const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const uploadForm = document.getElementById("upload-form");
const uploadStatus = document.getElementById("upload-status");
const uploadBtn = document.getElementById("upload-btn");

if (dropZone) {
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
    fileInput.files = e.dataTransfer.files;
  });
}

if (uploadForm) {
  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!fileInput.files.length) {
      showStatus("Select at least one screenshot.", "error");
      return;
    }

    uploadBtn.disabled = true;
    uploadBtn.textContent = "Analyzing…";
    showStatus("Running vision analysis + ranking (may take 1–3 min per image on CPU)…", "");

    const formData = new FormData();
    for (const file of fileInput.files) {
      formData.append("files", file);
    }

    try {
      const resp = await fetch("/toolbox/upload-screenshots", {
        method: "POST",
        body: formData,
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Upload failed");
      showStatus(data.message, "ok");
      setTimeout(() => window.location.reload(), 1500);
    } catch (err) {
      showStatus(err.message, "error");
    } finally {
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Analyze & Rank";
    }
  });
}

function showStatus(msg, type) {
  uploadStatus.textContent = msg;
  uploadStatus.className = "status" + (type ? ` ${type}` : "");
}

async function enrichProfile(profileId) {
  try {
    const resp = await fetch("/profiles/enrich", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_ids: [profileId] }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Enrich failed");
    showStatus(`Enrichment queued for profile ${profileId}`, "ok");
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function feedback(rankingId, type) {
  try {
    const resp = await fetch("/profiles/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ranking_id: rankingId, feedback: type }),
    });
    if (!resp.ok) throw new Error("Feedback failed");
    window.location.reload();
  } catch (err) {
    showStatus(err.message, "error");
  }
}