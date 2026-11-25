const LEVEL_NAMES = {
  1: "Livello 1 — Super Admin",
  2: "Livello 2 — Amministratore",
  3: "Livello 3 — Moderatore",
  4: "Livello 4 — Votante Ordinario",
  5: "Livello 5 — Votante Base"
};

document.addEventListener("DOMContentLoaded", async () => {
  const btnLogout = document.getElementById("btn-logout");
  btnLogout.addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  });

  try {
    const res = await fetch("/api/session");
    if (!res.ok) {
      window.location.href = "/login";
      return;
    }
    const { user } = await res.json();

    document.getElementById("welcome-heading").textContent = `Benvenuto, ${user.nome} ${user.cognome}`;
    document.getElementById("user-subtitle").textContent = `Username: ${user.username} | ID (Codice Fiscale): ${user.id}`;
    document.getElementById("user-level-badge").textContent = LEVEL_NAMES[user.livello] || `Livello ${user.livello}`;

    document.getElementById("kpi-presenze").textContent = user.presenze;
    document.getElementById("kpi-assenze").textContent = user.assenze;
    document.getElementById("kpi-totale").textContent = user.totale_votazioni;
    document.getElementById("kpi-perc").textContent = `${user.percentuale_presenze}%`;

    // Filtraggio navigazione e sezioni in base al livello account
    if (user.livello === 1 || user.livello === 2) {
      document.getElementById("nav-utenti").classList.remove("hidden");
      document.getElementById("card-gestione-utenti").classList.remove("hidden");
      document.getElementById("audit-section").classList.remove("hidden");
      loadAuditLedger();
    }
  } catch (err) {
    window.location.href = "/login";
  }
});

async function loadAuditLedger() {
  try {
    const res = await fetch("/api/audit");
    if (!res.ok) return;
    const { ledger } = await res.json();
    const tbody = document.getElementById("audit-tbody");
    tbody.innerHTML = "";
    ledger.forEach((entry) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="mono">${entry.index}</td>
        <td class="mono">${entry.timestamp}</td>
        <td><strong>${entry.action}</strong></td>
        <td class="mono">${entry.actor_commitment}</td>
        <td class="mono" title="${entry.block_hash}">${entry.block_hash.substring(0, 20)}...</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error(e);
  }
}
