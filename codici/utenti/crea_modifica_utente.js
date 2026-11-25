let currentUser = null;
let allUsers = [];

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("btn-logout").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  });

  const sessionRes = await fetch("/api/session");
  if (!sessionRes.ok) {
    window.location.href = "/login";
    return;
  }
  const sessionData = await sessionRes.json();
  currentUser = sessionData.user;

  if (currentUser.livello !== 1 && currentUser.livello !== 2) {
    window.location.href = "/dashboard";
    return;
  }

  populateLevelSelect();
  setupAutoUsername();
  await loadUsers();

  document.getElementById("btn-reset-form").addEventListener("click", resetForm);
  document.getElementById("utente-form").addEventListener("submit", handleSaveUser);
});

function populateLevelSelect() {
  const select = document.getElementById("livello");
  select.innerHTML = "";
  const levels = [
    { val: 1, text: "Livello 1 — Super Admin" },
    { val: 2, text: "Livello 2 — Amministratore" },
    { val: 3, text: "Livello 3 — Moderatore" },
    { val: 4, text: "Livello 4 — Votante Ordinario" },
    { val: 5, text: "Livello 5 — Votante Base" }
  ];

  // Livello 1 assegna 1-5; Livello 2 assegna solo 3-5
  const allowed = currentUser.livello === 1 ? [1, 2, 3, 4, 5] : [3, 4, 5];
  levels.filter(l => allowed.includes(l.val)).forEach(l => {
    const opt = document.createElement("option");
    opt.value = l.val;
    opt.textContent = l.text;
    select.appendChild(opt);
  });

  if (currentUser.livello === 2) {
    document.getElementById("role-limit-desc").textContent =
      "Permessi Livello 2: puoi creare e modificare esclusivamente account di Livello 3, 4 e 5.";
  }
}

function setupAutoUsername() {
  const nomeInput = document.getElementById("nome");
  const cognomeInput = document.getElementById("cognome");
  const usernameInput = document.getElementById("username");

  function updateUsername() {
    if (document.getElementById("edit-mode-id").value) return;
    const n = nomeInput.value.trim().toLowerCase().replace(/[^a-z0-9]/g, "");
    const c = cognomeInput.value.trim().toLowerCase().replace(/[^a-z0-9]/g, "");
    if (n && c) {
      let base = `${n}.${c}`;
      let candidate = base;
      let counter = 2;
      while (allUsers.some(u => u.username.toLowerCase() === candidate)) {
        candidate = `${base}${counter}`;
        counter++;
      }
      usernameInput.value = candidate;
    }
  }

  nomeInput.addEventListener("input", updateUsername);
  cognomeInput.addEventListener("input", updateUsername);
}

function validatePasswordClient(pwd) {
  if (pwd.length < 12) return "La password deve contenere almeno 12 caratteri.";
  if (!/[A-Z]/.test(pwd)) return "La password deve contenere almeno una lettera maiuscola.";
  if (!/[a-z]/.test(pwd)) return "La password deve contenere almeno una lettera minuscola.";
  if (!/[^A-Za-z0-9]/.test(pwd)) return "La password deve contenere almeno un carattere speciale.";
  return null;
}

function showAlert(msg, isSuccess = false) {
  const box = document.getElementById("utente-alert");
  box.textContent = msg;
  box.className = `alert show ${isSuccess ? "alert-success" : "alert-error"}`;
}

async function loadUsers() {
  const res = await fetch("/api/utenti");
  if (!res.ok) return;
  const data = await res.json();
  allUsers = data.utenti || [];

  const tbody = document.getElementById("utenti-tbody");
  tbody.innerHTML = "";

  allUsers.forEach(u => {
    const canEdit = currentUser.livello === 1 || (currentUser.livello === 2 && [3, 4, 5].includes(u.livello));
    const canDelete = currentUser.livello === 1 && u.id !== currentUser.id;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${u.nome} ${u.cognome}</strong></td>
      <td class="mono">${u.id}</td>
      <td class="mono">${u.username}</td>
      <td><span class="badge badge-gold">Livello ${u.livello}</span></td>
      <td>${u.presenze}</td>
      <td>${u.assenze}</td>
      <td>${u.percentuale_presenze}%</td>
      <td>${u.percentuale_assenze}%</td>
      <td>
        ${canEdit ? `<button type="button" class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.85rem;" onclick="startEditUser('${u.id}')">Modifica</button>` : ""}
        ${canDelete ? `<button type="button" class="btn btn-danger" onclick="deleteUser('${u.id}')">Elimina</button>` : ""}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

window.startEditUser = function(uid) {
  const u = allUsers.find(item => item.id === uid);
  if (!u) return;

  document.getElementById("edit-mode-id").value = u.id;
  document.getElementById("nome").value = u.nome;
  document.getElementById("cognome").value = u.cognome;
  document.getElementById("codice_fiscale").value = u.id;
  document.getElementById("codice_fiscale").disabled = true;
  document.getElementById("username").value = u.username;
  document.getElementById("livello").value = u.livello;
  document.getElementById("password").value = "";
  document.getElementById("pwd-req-label").textContent = "(lascia vuoto per mantenere attuale)";
  document.getElementById("form-utente-heading").textContent = `Modifica Account: ${u.nome} ${u.cognome}`;
  document.getElementById("btn-reset-form").classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
};

function resetForm() {
  document.getElementById("edit-mode-id").value = "";
  document.getElementById("utente-form").reset();
  document.getElementById("codice_fiscale").disabled = false;
  document.getElementById("pwd-req-label").textContent = "*";
  document.getElementById("form-utente-heading").textContent = "Crea o Modifica Account Utente";
  document.getElementById("btn-reset-form").classList.add("hidden");
}

async function handleSaveUser(e) {
  e.preventDefault();
  const editId = document.getElementById("edit-mode-id").value;
  const nome = document.getElementById("nome").value.trim();
  const cognome = document.getElementById("cognome").value.trim();
  const id = document.getElementById("codice_fiscale").value.trim().toUpperCase();
  const username = document.getElementById("username").value.trim().toLowerCase();
  const livello = parseInt(document.getElementById("livello").value, 10);
  const password = document.getElementById("password").value;

  if (!nome || !cognome || !id || !username) {
    showAlert("Compila tutti i campi anagrafici obbligatori.");
    return;
  }

  if (!editId || password.length > 0) {
    const pwdErr = validatePasswordClient(password);
    if (pwdErr) {
      showAlert(pwdErr);
      return;
    }
  }

  const url = editId ? `/api/utenti/${editId}` : "/api/utenti";
  const method = editId ? "PUT" : "POST";

  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nome, cognome, id, username, livello, password })
  });
  const data = await res.json();

  if (!res.ok) {
    showAlert(data.error || "Errore durante il salvataggio.");
    return;
  }

  showAlert(data.message, true);
  resetForm();
  await loadUsers();
}

window.deleteUser = async function(uid) {
  if (!confirm(`Confermi l'eliminazione definitiva dell'utente ${uid}?`)) return;
  const res = await fetch(`/api/utenti/${uid}`, { method: "DELETE" });
  const data = await res.json();
  if (!res.ok) {
    showAlert(data.error || "Errore durante l'eliminazione.");
    return;
  }
  showAlert(data.message, true);
  await loadUsers();
};
