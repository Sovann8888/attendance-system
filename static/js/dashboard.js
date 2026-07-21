function openAddSubject() {
  document.getElementById("addSubjectModal").classList.add("open");
  document.getElementById("newSubjectName").value = "";
  document.getElementById("subjectAddError").style.display = "none";
  document.getElementById("newSubjectName").focus();
}

function closeAddSubject() {
  document.getElementById("addSubjectModal").classList.remove("open");
}

async function submitAddSubject() {
  const name  = document.getElementById("newSubjectName").value.trim();
  const errEl = document.getElementById("subjectAddError");
  errEl.style.display = "none";

  if (!name) {
    errEl.textContent = "Please enter a subject name.";
    errEl.style.display = "block";
    return;
  }

  const res  = await fetch("/api/subjects/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await res.json();

  if (data.ok) {
    location.reload();
  } else {
    errEl.textContent = data.error || "Failed to add subject.";
    errEl.style.display = "block";
  }
}

// Allow Enter key inside the add-subject modal
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("newSubjectName");
  if (input) {
    input.addEventListener("keydown", e => {
      if (e.key === "Enter") submitAddSubject();
    });
  }
});
