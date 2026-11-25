document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("login-form");
  const alertBox = document.getElementById("login-alert");
  const btnConferma = document.getElementById("btn-conferma");

  function showAlert(message) {
    alertBox.textContent = message;
    alertBox.classList.add("show");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    alertBox.classList.remove("show");

    const username = document.getElementById("username").value.trim();
    const id = document.getElementById("codice_fiscale").value.trim().toUpperCase();
    const password = document.getElementById("password").value;

    if (!username || !id || !password) {
      showAlert("Compila tutti i campi obbligatori: Username, ID (Codice Fiscale) e Password.");
      return;
    }

    btnConferma.disabled = true;
    btnConferma.textContent = "Verifica Zero-Trust in corso...";

    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, id, password })
      });
      const result = await response.json();

      if (!response.ok) {
        showAlert(result.error || "Accesso negato.");
        btnConferma.disabled = false;
        btnConferma.textContent = "Conferma";
        return;
      }

      window.location.href = result.redirect || "/dashboard";
    } catch (err) {
      showAlert("Errore di connessione al server HTTPS Ισονομία.");
      btnConferma.disabled = false;
      btnConferma.textContent = "Conferma";
    }
  });
});
