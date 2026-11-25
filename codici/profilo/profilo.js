document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("btn-logout").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  });

  const res = await fetch("/api/session");
  if (!res.ok) {
    window.location.href = "/login";
    return;
  }
  const { user } = await res.json();

  if (user.livello === 1 || user.livello === 2) {
    document.getElementById("nav-utenti").classList.remove("hidden");
  }

  document.getElementById("profilo-livello-badge").textContent = `Livello ${user.livello}`;
  document.getElementById("prof-nome-cognome").textContent = `${user.nome} ${user.cognome}`;
  document.getElementById("prof-id").textContent = user.id;
  document.getElementById("prof-username").textContent = user.username;
  document.getElementById("prof-presenze").textContent = user.presenze;
  document.getElementById("prof-assenze").textContent = user.assenze;
  document.getElementById("prof-totale").textContent = user.totale_votazioni;
  document.getElementById("prof-percentuali").textContent = `${user.percentuale_presenze}% / ${user.percentuale_assenze}%`;

  const form = document.getElementById("password-form");
  const alertBox = document.getElementById("profilo-alert");

  function showAlert(msg, isSuccess = false) {
    alertBox.textContent = msg;
    alertBox.className = `alert show ${isSuccess ? "alert-success" : "alert-error"}`;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const oldPassword = document.getElementById("old-password").value;
    const newPassword = document.getElementById("new-password").value;
    const confirmPassword = document.getElementById("confirm-password").value;

    if (!oldPassword || !newPassword || !confirmPassword) {
      showAlert("Compila tutti i campi password.");
      return;
    }

    if (newPassword !== confirmPassword) {
      showAlert("La nuova password e la conferma non coincidono.");
      return;
    }

    if (
      newPassword.length < 12 ||
      !/[A-Z]/.test(newPassword) ||
      !/[a-z]/.test(newPassword) ||
      !/[^A-Za-z0-9]/.test(newPassword)
    ) {
      showAlert("La nuova password deve avere almeno 12 caratteri, una maiuscola, una minuscola e un carattere speciale.");
      return;
    }

    const updateRes = await fetch("/api/profilo/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
    });
    const data = await updateRes.json();

    if (!updateRes.ok) {
      showAlert(data.error || "Errore durante l'aggiornamento della password.");
      return;
    }

    showAlert(data.message, true);
    form.reset();
  });
});
