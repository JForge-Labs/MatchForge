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

if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const gender = form.querySelector('input[name="gender"]:checked');
    const intentions = [...form.querySelectorAll('input[name="intentions"]:checked')].map(
      (el) => el.value
    );

    if (!gender) {
      showStatus("Please select your gender.", "error");
      return;
    }
    if (!intentions.length) {
      showStatus("Select at least one dating intention.", "error");
      return;
    }

    btn.disabled = true;
    btn.textContent = "Generating preference vector…";
    showStatus("Analyzing your profile and building personalized ranking weights…", "");

    const formData = new FormData();
    formData.append("gender", gender.value);
    formData.append("intentions", JSON.stringify(intentions));
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
      if (!resp.ok) throw new Error(data.detail || "Onboarding failed");
      showStatus(data.message, "ok");
      setTimeout(() => (window.location.href = "/dashboard"), 1500);
    } catch (err) {
      showStatus(err.message, "error");
      btn.disabled = false;
      btn.textContent = "Build My Preference Vector";
    }
  });
}

function showStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = "status" + (type ? ` ${type}` : "");
}