const form = document.getElementById("onboarding-form");
const statusEl = document.getElementById("onboard-status");
const btn = document.getElementById("onboard-btn");
const otherCheck = document.getElementById("other-check");
const otherNote = document.getElementById("other-note");

if (otherCheck) {
  otherCheck.addEventListener("change", () => {
    otherNote.classList.toggle("hidden", !otherCheck.checked);
  });
}

async function loadExistingProfile() {
  try {
    const resp = await fetch("/onboarding/status");
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.gender) {
      const genderInput = form.querySelector(`input[name="gender"][value="${data.gender}"]`);
      if (genderInput) genderInput.checked = true;
    }
    const preferred = data.preferred_genders || [];
    for (const value of preferred) {
      const el = form.querySelector(`input[name="preferred_genders"][value="${value}"]`);
      if (el) el.checked = true;
    }
    for (const value of data.intentions || []) {
      const el = form.querySelector(`input[name="intentions"][value="${value}"]`);
      if (el) el.checked = true;
    }
    if (otherCheck && (data.intentions || []).includes("other")) {
      otherCheck.checked = true;
      otherNote.classList.remove("hidden");
    }
  } catch (_) {
    /* ignore */
  }
}

if (form) {
  loadExistingProfile();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const gender = form.querySelector('input[name="gender"]:checked');
    const preferredGenders = [
      ...form.querySelectorAll('input[name="preferred_genders"]:checked'),
    ].map((el) => el.value);
    const goals = [...form.querySelectorAll('input[name="intentions"]:checked')].map(
      (el) => el.value
    );

    if (!gender) {
      showStatus("Please select your gender.", "error");
      return;
    }
    if (!preferredGenders.length) {
      showStatus("Select at least one gender you're interested in.", "error");
      return;
    }
    if (!goals.length) {
      showStatus("Select at least one goal.", "error");
      return;
    }

    btn.disabled = true;
    btn.textContent = "Building your ranking profile…";
    showStatus("Saving profile and generating personalized ranking weights…", "");

    const formData = new FormData();
    formData.append("gender", gender.value);
    formData.append("preferred_genders", JSON.stringify(preferredGenders));
    formData.append("intentions", JSON.stringify(goals));
    if (otherCheck.checked && otherNote.value) {
      formData.append("other_intention_note", otherNote.value);
    }
    const files = document.getElementById("example-input").files;
    for (const file of files) {
      formData.append("examples", file);
    }

    try {
      const resp = await fetch("/onboarding/profile", { method: "POST", body: formData });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Save failed");
      showStatus(data.message, "ok");
      setTimeout(() => (window.location.href = "/dashboard"), 1500);
    } catch (err) {
      showStatus(err.message, "error");
      btn.disabled = false;
      btn.textContent = "Save profile & build ranking";
    }
  });
}

function showStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = "status" + (type ? ` ${type}` : "");
}