let currentUser = null;
let availableUsers = [];
let selectedParticipants = []; // [{ nome, cognome, id, presente }]
let allVotazioni = [];

const VOT_LEVEL_LABELS = {
  1: "Livello 1 — Votazione Suprema / Costituzionale (Accesso Livelli 1-2)",
  2: "Livello 2 — Votazione Maggiore / Ordinaria (Accesso Livelli 1-4)",
  3: "Livello 3 — Votazione Minore / Consultiva (Accesso Livelli 1-5)"
};

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
  const { user } = await sessionRes.json();
  currentUser = user;

  if (currentUser.livello === 1 || currentUser.livello === 2) {
    document.getElementById("nav-utenti").classList.remove("hidden");
  }

  // Livelli 1, 2 e 3 possono creare/gestire votazioni
  if ([1, 2, 3].includes(currentUser.livello)) {
    document.getElementById("create-votazione-card").classList.remove("hidden");
    setupVotazioneForm();
    await loadAvailableUsers();
  }

  await loadVotazioni();
});

function showAlert(msg, isSuccess = false) {
  const box = document.getElementById("votazioni-alert");
  box.textContent = msg;
  box.className = `alert show ${isSuccess ? "alert-success" : "alert-error"}`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setupVotazioneForm() {
  const selectLivello = document.getElementById("vot-livello");
  selectLivello.innerHTML = "";

  // Livello 1: 1,2,3 | Livello 2: 1,2 | Livello 3: solo 3
  let allowedLevels = [1, 2, 3];
  if (currentUser.livello === 2) allowedLevels = [1, 2];
  if (currentUser.livello === 3) allowedLevels = [3];

  allowedLevels.forEach(lvl => {
    const opt = document.createElement("option");
    opt.value = lvl;
    opt.textContent = VOT_LEVEL_LABELS[lvl];
    selectLivello.appendChild(opt);
  });

  document.getElementById("btn-aggiungi-persona").addEventListener("click", () => {
    const selectPersona = document.getElementById("select-persona");
    const uid = selectPersona.value;
    if (!uid) return;

    if (selectedParticipants.some(p => p.id === uid)) {
      showAlert("Questa persona è già presente nell'elenco dei partecipanti.");
      return;
    }

    const userObj = availableUsers.find(u => u.id === uid);
    if (!userObj) return;

    selectedParticipants.push({
      nome: userObj.nome,
      cognome: userObj.cognome,
      id: userObj.id,
      presente: false
    });
    renderParticipantsFormTable();
  });

  document.getElementById("btn-cancel-edit-vot").addEventListener("click", resetVotazioneForm);
  document.getElementById("votazione-form").addEventListener("submit", handleSaveVotazione);
}

async function loadAvailableUsers() {
  const res = await fetch("/api/utenti");
  if (!res.ok) return;
  const data = await res.json();
  availableUsers = data.utenti || [];

  const selectPersona = document.getElementById("select-persona");
  selectPersona.innerHTML = '<option value="">-- Seleziona un utente registrato --</option>';
  availableUsers.forEach(u => {
    const opt = document.createElement("option");
    opt.value = u.id;
    opt.textContent = `${u.nome} ${u.cognome} (${u.id}) — Livello ${u.livello}`;
    selectPersona.appendChild(opt);
  });
}

function renderParticipantsFormTable() {
  const tbody = document.getElementById("partecipanti-form-tbody");
  tbody.innerHTML = "";

  selectedParticipants.forEach((p, index) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.nome}</td>
      <td>${p.cognome}</td>
      <td class="mono">${p.id}</td>
      <td>
        <label style="display: inline-flex; align-items: center; gap: 8px; margin: 0; cursor: pointer;">
          <input type="checkbox" class="presence-checkbox" ${p.presente ? "checked" : ""}
            onchange="toggleParticipantPresence(${index}, this.checked)"
            aria-label="Presenza per ${p.nome} ${p.cognome}">
          <span>${p.presente ? "Presente" : "Assente"}</span>
        </label>
      </td>
      <td>
        <button type="button" class="btn btn-danger" onclick="removeParticipantFromForm(${index})">Elimina</button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  const presenti = selectedParticipants.filter(p => p.presente).length;
  const assenti = selectedParticipants.length - presenti;
  const perc = selectedParticipants.length > 0 ? ((presenti / selectedParticipants.length) * 100).toFixed(2) : 0;
  document.getElementById("live-stats-preview").textContent =
    `Presenti: ${presenti} | Assenti: ${assenti} | Percentuale Presenze: ${perc}%`;
}

window.toggleParticipantPresence = function(index, isChecked) {
  selectedParticipants[index].presente = isChecked;
  renderParticipantsFormTable();
};

window.removeParticipantFromForm = function(index) {
  selectedParticipants.splice(index, 1);
  renderParticipantsFormTable();
};

function resetVotazioneForm() {
  document.getElementById("edit-vot-id").value = "";
  document.getElementById("votazione-form").reset();
  document.getElementById("vot-livello").disabled = false;
  document.getElementById("vot-pwd-hint").textContent = "*";
  document.getElementById("vot-form-heading").textContent = "Crea o Modifica Votazione";
  document.getElementById("btn-cancel-edit-vot").classList.add("hidden");
  selectedParticipants = [];
  renderParticipantsFormTable();
}

async function handleSaveVotazione(e) {
  e.preventDefault();
  const editId = document.getElementById("edit-vot-id").value;
  const titolo = document.getElementById("vot-titolo").value.trim();
  const descrizione = document.getElementById("vot-descrizione").value.trim();
  const livello = parseInt(document.getElementById("vot-livello").value, 10);
  const password = document.getElementById("vot-password").value;

  if (!titolo || !descrizione) {
    showAlert("Inserisci titolo e descrizione della votazione.");
    return;
  }
  if (!editId && !password) {
    showAlert("La password della votazione è obbligatoria.");
    return;
  }

  const url = editId ? `/api/votazioni/${editId}` : "/api/votazioni";
  const method = editId ? "PUT" : "POST";

  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      titolo,
      descrizione,
      livello,
      password,
      partecipanti: selectedParticipants
    })
  });
  const data = await res.json();

  if (!res.ok) {
    showAlert(data.error || "Errore durante il salvataggio della votazione.");
    return;
  }

  showAlert(data.message, true);
  resetVotazioneForm();
  await loadVotazioni();
}

async function loadVotazioni() {
  const res = await fetch("/api/votazioni");
  if (!res.ok) return;
  const data = await res.json();
  allVotazioni = data.votazioni || [];

  const container = document.getElementById("votazioni-list");
  container.innerHTML = "";

  if (allVotazioni.length === 0) {
    container.innerHTML = '<p class="card-desc">Nessuna votazione disponibile per il tuo livello account.</p>';
    return;
  }

  allVotazioni.forEach(v => {
    const canManage =
      currentUser.livello === 1 ||
      (currentUser.livello === 2 && [1, 2].includes(v.livello)) ||
      (currentUser.livello === 3 && v.livello === 3);

    const canDelete =
      currentUser.livello === 1 ||
      (currentUser.livello === 2 && v.livello === 2) ||
      (currentUser.livello === 3 && v.livello === 3);

    const isPresentUser = v.presenti.includes(currentUser.id);

    const card = document.createElement("article");
    card.className = "card";
    card.style.backgroundColor = "var(--bg-secondary)";

    let rowsHtml = "";
    v.partecipanti.forEach(p => {
      rowsHtml += `
        <tr>
          <td>${p.nome}</td>
          <td>${p.cognome}</td>
          <td class="mono">${p.id}</td>
          <td>
            <input type="checkbox" class="presence-checkbox" ${p.presente ? "checked" : ""}
              ${canManage ? `onchange="quickTogglePresence('${v.id}', '${p.id}', this.checked)"` : "disabled"}
              aria-label="Presenza ${p.nome} ${p.cognome}">
            <span style="margin-left: 8px;">${p.presente ? "Presente" : "Assente"}</span>
          </td>
          <td>
            ${canManage ? `<button type="button" class="btn btn-danger" onclick="quickRemoveParticipant('${v.id}', '${p.id}')">Elimina</button>` : "—"}
          </td>
        </tr>
      `;
    });

    card.innerHTML = `
      <div class="card-header">
        <div>
          <span class="badge badge-gold">Livello ${v.livello}</span>
          <span class="badge badge-cyan">Affluenza: ${v.percentuale_presenze}%</span>
          <span class="badge badge-green">Schede Cifrate E2E: ${v.voti_registrati}</span>
          <h3 class="card-title" style="margin-top: 8px;">${v.titolo} <span class="mono" style="font-size: 0.85rem; color: var(--text-muted);">(${v.id})</span></h3>
          <p class="card-desc">${v.descrizione}</p>
        </div>
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
          ${canManage ? `<button type="button" class="btn btn-secondary" onclick="editVotazione('${v.id}')">Modifica Votazione</button>` : ""}
          ${canDelete ? `<button type="button" class="btn btn-danger" onclick="deleteVotazione('${v.id}')">Elimina Votazione</button>` : ""}
        </div>
      </div>

      <div class="table-responsive" style="margin-bottom: 16px;">
        <table>
          <thead>
            <tr>
              <th>Nome</th>
              <th>Cognome</th>
              <th>Cod. Fiscale</th>
              <th>Presenza</th>
              <th>Azione</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml || '<tr><td colspan="5">Nessun partecipante assegnato.</td></tr>'}
          </tbody>
        </table>
      </div>

      ${isPresentUser ? `
        <div style="border-top: 1px solid var(--border-color); padding-top: 14px; display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;">
          <div>
            <label for="vote-choice-${v.id}">Espressione Voto Segreto (E2E-V)</label>
            <select id="vote-choice-${v.id}">
              <option value="FAVOREVOLE">FAVOREVOLE</option>
              <option value="CONTRARIO">CONTRARIO</option>
              <option value="ASTENUTO">ASTENUTO</option>
            </select>
          </div>
          <div>
            <label for="vote-pwd-${v.id}">Password Votazione</label>
            <input type="password" id="vote-pwd-${v.id}" placeholder="Conferma password votazione">
          </div>
          <button type="button" class="btn btn-primary" onclick="castEncryptedVote('${v.id}')">Invia Scheda Cifrata</button>
        </div>
      ` : `<p class="form-hint">Nota: solo i partecipanti contrassegnati come <strong>Presente</strong> possono inviare la scheda di voto cifrata.</p>`}
    `;

    container.appendChild(card);
  });
}

window.quickTogglePresence = async function(votId, targetUid, isPresent) {
  const vot = allVotazioni.find(v => v.id === votId);
  if (!vot) return;
  const updated = vot.partecipanti.map(p => ({
    id: p.id,
    presente: p.id === targetUid ? isPresent : p.presente
  }));

  const res = await fetch(`/api/votazioni/${votId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ partecipanti: updated })
  });
  const data = await res.json();
  if (!res.ok) {
    showAlert(data.error || "Errore aggiornamento presenza.");
    return;
  }
  showAlert("Presenza aggiornata e statistiche utenti ricalcolate.", true);
  await loadVotazioni();
};

window.quickRemoveParticipant = async function(votId, targetUid) {
  const vot = allVotazioni.find(v => v.id === votId);
  if (!vot) return;
  const updated = vot.partecipanti
    .filter(p => p.id !== targetUid)
    .map(p => ({ id: p.id, presente: p.presente }));

  const res = await fetch(`/api/votazioni/${votId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ partecipanti: updated })
  });
  if (res.ok) {
    showAlert("Partecipante rimosso e statistiche aggiornate.", true);
    await loadVotazioni();
  }
};

window.editVotazione = function(votId) {
  const vot = allVotazioni.find(v => v.id === votId);
  if (!vot) return;
  document.getElementById("edit-vot-id").value = vot.id;
  document.getElementById("vot-titolo").value = vot.titolo;
  document.getElementById("vot-descrizione").value = vot.descrizione;
  document.getElementById("vot-livello").value = vot.livello;
  document.getElementById("vot-livello").disabled = true;
  document.getElementById("vot-password").value = "";
  document.getElementById("vot-pwd-hint").textContent = "(lascia vuoto per mantenere password attuale)";
  document.getElementById("vot-form-heading").textContent = `Modifica Votazione: ${vot.titolo}`;
  document.getElementById("btn-cancel-edit-vot").classList.remove("hidden");

  selectedParticipants = vot.partecipanti.map(p => ({ ...p }));
  renderParticipantsFormTable();
  window.scrollTo({ top: 0, behavior: "smooth" });
};

window.deleteVotazione = async function(votId) {
  if (!confirm(`Confermi l'eliminazione della votazione ${votId}?`)) return;
  const res = await fetch(`/api/votazioni/${votId}`, { method: "DELETE" });
  const data = await res.json();
  if (!res.ok) {
    showAlert(data.error || "Impossibile eliminare la votazione.");
    return;
  }
  showAlert(data.message, true);
  await loadVotazioni();
};

window.castEncryptedVote = async function(votId) {
  const scelta = document.getElementById(`vote-choice-${votId}`).value;
  const password = document.getElementById(`vote-pwd-${votId}`).value;
  if (!password) {
    showAlert("Inserisci la password della votazione per confermare la scheda cifrata.");
    return;
  }

  const res = await fetch(`/api/votazioni/${votId}/vota`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scelta, password })
  });
  const data = await res.json();
  if (!res.ok) {
    showAlert(data.error || "Errore durante l'espressione del voto.");
    return;
  }

  showAlert(`${data.message} Ricevuta crittografica ZKP: ${data.zkp_ballot_receipt}`, true);
  await loadVotazioni();
};
