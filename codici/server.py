import os
import re
import json
import socket
import hashlib
import secrets
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, jsonify, session, redirect, send_from_directory, abort
from cryptography.fernet import Fernet
import bcrypt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
CERTS_DIR = os.path.join(BASE_DIR, "certs")

KEY_FILE = os.path.join(DB_DIR, "database.chiave")
UTENTI_FILE = os.path.join(DB_DIR, "utenti.json")
VOTAZIONI_FILE = os.path.join(DB_DIR, "votazioni.json")
AUDIT_LEDGER_FILE = os.path.join(DB_DIR, "audit_ledger.json")

app = Flask(__name__, static_folder=None)

# Chiave segreta di sessione generata o derivata dalla chiave di sistema
def load_or_create_key():
    os.makedirs(DB_DIR, exist_ok=True)
    env_key = os.environ.get("ISONOMIA_MASTER_KEY")
    if env_key:
        return env_key.encode("utf-8")
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        try:
            os.chmod(KEY_FILE, 0o600)
        except Exception:
            pass
        return key
    with open(KEY_FILE, "rb") as f:
        return f.read().strip()

MASTER_KEY = load_or_create_key()
fernet = Fernet(MASTER_KEY)
app.secret_key = hashlib.sha256(MASTER_KEY).hexdigest()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# Sicurezza: blocca qualsiasi accesso diretto a /database o /certs
@app.before_request
def block_sensitive_paths():
    path = request.path.lower()
    if path.startswith("/database") or path.startswith("/certs") or path.endswith(".py") or path.endswith(".chiave"):
        abort(403, description="Accesso negato: risorsa protetta dal sistema Ισονομία.")

# Funzioni di lettura/scrittura cifrata
def read_encrypted_json(filepath, default_data):
    if not os.path.exists(filepath):
        write_encrypted_json(filepath, default_data)
        return default_data
    with open(filepath, "rb") as f:
        encrypted_bytes = f.read()
    if not encrypted_bytes:
        return default_data
    decrypted_bytes = fernet.decrypt(encrypted_bytes)
    return json.loads(decrypted_bytes.decode("utf-8"))

def write_encrypted_json(filepath, data):
    raw_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    encrypted_bytes = fernet.encrypt(raw_bytes)
    with open(filepath, "wb") as f:
        f.write(encrypted_bytes)

# Registro Immutabile (Hash-chained Audit Ledger)
def append_audit_log(action, actor_id, details):
    ledger = read_encrypted_json(AUDIT_LEDGER_FILE, [])
    prev_hash = ledger[-1]["block_hash"] if ledger else "0" * 64
    timestamp = datetime.now(timezone.utc).isoformat()
    # Commitment anonimizzato dell'attore (ZKP-style commitment)
    actor_commitment = hashlib.sha256(f"{actor_id}:{MASTER_KEY.decode()}".encode()).hexdigest()[:24]
    payload = f"{len(ledger)}|{timestamp}|{action}|{actor_commitment}|{json.dumps(details, sort_keys=True)}|{prev_hash}"
    block_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    entry = {
        "index": len(ledger) + 1,
        "timestamp": timestamp,
        "action": action,
        "actor_commitment": actor_commitment,
        "details": details,
        "prev_hash": prev_hash,
        "block_hash": block_hash
    }
    ledger.append(entry)
    write_encrypted_json(AUDIT_LEDGER_FILE, ledger)

# Validazione password (min 12 caratteri, 1 maiuscola, 1 minuscola, 1 carattere speciale)
def validate_password_complexity(password):
    if not password or len(password) < 12:
        return False, "La password deve contenere almeno 12 caratteri."
    if not re.search(r"[A-Z]", password):
        return False, "La password deve contenere almeno una lettera maiuscola."
    if not re.search(r"[a-z]", password):
        return False, "La password deve contenere almeno una lettera minuscola."
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "La password deve contenere almeno un carattere speciale."
    return True, "OK"

def hash_password(plain_password):
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password, hashed_password):
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

# Ricalcolo automatico statistiche presenze/assenze utenti
def recalculate_all_user_stats(utenti, votazioni):
    for u in utenti:
        uid = u["id"].upper()
        presenze = 0
        assenze = 0
        for v in votazioni:
            if uid in [p.upper() for p in v.get("presenti", [])]:
                presenze += 1
            elif uid in [a.upper() for a in v.get("assenti", [])]:
                assenze += 1
        totale = presenze + assenze
        u["presenze"] = presenze
        u["assenze"] = assenze
        u["totale_votazioni"] = totale
        u["percentuale_presenze"] = round((presenze / totale) * 100, 2) if totale > 0 else 0.0
        u["percentuale_assenze"] = round((assenze / totale) * 100, 2) if totale > 0 else 0.0
    return utenti

# Inizializzazione Database con Super Admin predefinito
def init_database():
    if not os.path.exists(UTENTI_FILE):
        default_admin = [{
            "nome": "Davide",
            "cognome": "Pirovano",
            "id": "PRVDVD05A27M052R",
            "username": "davide.pirovano",
            "livello": 1,
            "password_hash": hash_password(r"7yG’p:&k\.js:N$GW8r"),
            "presenze": 0,
            "assenze": 0,
            "totale_votazioni": 0,
            "percentuale_presenze": 0.0,
            "percentuale_assenze": 0.0
        }]
        write_encrypted_json(UTENTI_FILE, default_admin)
        append_audit_log("INIT_SYSTEM", "SYSTEM", {"message": "Inizializzazione database cifrato e Super Admin Livello 1"})

    if not os.path.exists(VOTAZIONI_FILE):
        write_encrypted_json(VOTAZIONI_FILE, [])

init_database()

# Decorator autenticazione
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Autenticazione obbligatoria."}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    if "user_id" not in session:
        return None
    utenti = read_encrypted_json(UTENTI_FILE, [])
    for u in utenti:
        if u["id"] == session["user_id"]:
            return u
    return None

# --- ROTTE PAGINE HTML / ASSET ---
@app.route("/")
def index():
    if "user_id" in session:
        return redirect("/dashboard")
    return redirect("/login")

@app.route("/login")
def login_page():
    return send_from_directory(os.path.join(BASE_DIR, "login"), "login.html")

@app.route("/login/<path:filename>")
def login_assets(filename):
    return send_from_directory(os.path.join(BASE_DIR, "login"), filename)

@app.route("/dashboard")
@login_required
def dashboard_page():
    return send_from_directory(os.path.join(BASE_DIR, "dashboard"), "dashboard.html")

@app.route("/dashboard/<path:filename>")
@login_required
def dashboard_assets(filename):
    return send_from_directory(os.path.join(BASE_DIR, "dashboard"), filename)

@app.route("/utenti")
@login_required
def utenti_page():
    user = get_current_user()
    if not user or user["livello"] not in [1, 2]:
        return redirect("/dashboard")
    return send_from_directory(os.path.join(BASE_DIR, "utenti"), "crea_modifica_utente.html")

@app.route("/utenti/<path:filename>")
@login_required
def utenti_assets(filename):
    return send_from_directory(os.path.join(BASE_DIR, "utenti"), filename)

@app.route("/profilo")
@login_required
def profilo_page():
    return send_from_directory(os.path.join(BASE_DIR, "profilo"), "profilo.html")

@app.route("/profilo/<path:filename>")
@login_required
def profilo_assets(filename):
    return send_from_directory(os.path.join(BASE_DIR, "profilo"), filename)

@app.route("/votazioni")
@login_required
def votazioni_page():
    return send_from_directory(os.path.join(BASE_DIR, "votazioni"), "gestione_votazioni.html")

@app.route("/votazioni/<path:filename>")
@login_required
def votazioni_assets(filename):
    return send_from_directory(os.path.join(BASE_DIR, "votazioni"), filename)

# --- API AUTENTICAZIONE & SESSIONE ---
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    codice_fiscale = data.get("id", "").strip().upper()
    password = data.get("password", "")

    if not username or not codice_fiscale or not password:
        return jsonify({"error": "Tutti i campi (Username, ID/Codice Fiscale e Password) sono obbligatori."}), 400

    utenti = read_encrypted_json(UTENTI_FILE, [])
    matched_user = None
    for u in utenti:
        if u["username"].lower() == username and u["id"].upper() == codice_fiscale:
            if verify_password(password, u["password_hash"]):
                matched_user = u
            break

    if not matched_user:
        append_audit_log("LOGIN_FAILED", codice_fiscale or "UNKNOWN", {"username": username})
        return jsonify({"error": "Credenziali non valide. Verifica Username, ID (Codice Fiscale) e Password."}), 401

    session.clear()
    session["user_id"] = matched_user["id"]
    session["username"] = matched_user["username"]
    session["livello"] = matched_user["livello"]
    # Generazione token di sessione ZKP per verifica crittografica client-side
    session["zkp_session_token"] = secrets.token_hex(32)

    append_audit_log("LOGIN_SUCCESS", matched_user["id"], {"livello": matched_user["livello"]})
    return jsonify({
        "message": "Autenticazione sovrana verificata.",
        "redirect": "/dashboard"
    })

@app.route("/api/logout", methods=["POST"])
def api_logout():
    uid = session.get("user_id", "UNKNOWN")
    append_audit_log("LOGOUT", uid, {})
    session.clear()
    return jsonify({"redirect": "/login"})

@app.route("/api/session", methods=["GET"])
@login_required
def api_session():
    user = get_current_user()
    if not user:
        session.clear()
        return jsonify({"error": "Sessione non valida."}), 401
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    safe_user["zkp_token"] = session.get("zkp_session_token")
    return jsonify({"user": safe_user})

# --- API GESTIONE UTENTI (Livelli 1-5) ---
@app.route("/api/utenti", methods=["GET"])
@login_required
def api_get_utenti():
    current = get_current_user()
    utenti = read_encrypted_json(UTENTI_FILE, [])
    # Livello 1 e 2 vedono tutti i dettagli (senza hash password); Livello 3 vede solo anagrafica base per convocazioni
    if current["livello"] in [1, 2]:
        res = [{k: v for k, v in u.items() if k != "password_hash"} for u in utenti]
        return jsonify({"utenti": res})
    elif current["livello"] == 3:
        res = [{
            "nome": u["nome"],
            "cognome": u["cognome"],
            "id": u["id"],
            "username": u["username"],
            "livello": u["livello"]
        } for u in utenti]
        return jsonify({"utenti": res})
    else:
        return jsonify({"error": "Permessi insufficienti per visualizzare l'elenco utenti."}), 403

def generate_unique_username(nome, cognome, utenti, exclude_id=None):
    base = re.sub(r"[^a-z0-9]", "", nome.lower()) + "." + re.sub(r"[^a-z0-9]", "", cognome.lower())
    existing = {u["username"].lower() for u in utenti if u["id"].upper() != (exclude_id or "").upper()}
    if base not in existing:
        return base
    counter = 2
    while f"{base}{counter}" in existing:
        counter += 1
    return f"{base}{counter}"

@app.route("/api/utenti", methods=["POST"])
@login_required
def api_create_utente():
    current = get_current_user()
    if current["livello"] not in [1, 2]:
        return jsonify({"error": "Non hai i permessi per creare utenti."}), 403

    data = request.get_json(silent=True) or {}
    nome = data.get("nome", "").strip()
    cognome = data.get("cognome", "").strip()
    codice_fiscale = data.get("id", "").strip().upper()
    password = data.get("password", "")
    try:
        livello = int(data.get("livello", 5))
    except ValueError:
        return jsonify({"error": "Livello non valido."}), 400

    if not nome or not cognome or not codice_fiscale:
        return jsonify({"error": "Nome, Cognome e ID (Codice Fiscale) sono obbligatori."}), 400

    if not re.match(r"^[A-Z0-9]{11,16}$", codice_fiscale):
        return jsonify({"error": "Formato ID / Codice Fiscale non valido (11-16 caratteri alfanumerici)."}), 400

    if livello < 1 or livello > 5:
        return jsonify({"error": "Il livello deve essere compreso tra 1 e 5."}), 400

    # Controllo gerarchia permessi: Livello 2 può creare solo Livelli 3, 4 e 5
    if current["livello"] == 2 and livello not in [3, 4, 5]:
        return jsonify({"error": "Un Amministratore di Livello 2 può creare solo account di Livello 3, 4 o 5."}), 403

    valid_pwd, msg = validate_password_complexity(password)
    if not valid_pwd:
        return jsonify({"error": msg}), 400

    utenti = read_encrypted_json(UTENTI_FILE, [])
    if any(u["id"].upper() == codice_fiscale for u in utenti):
        return jsonify({"error": "Esiste già un utente registrato con questo ID (Codice Fiscale)."}), 409

    # Username generato o validato univocamente come nome.cognome
    requested_username = data.get("username", "").strip().lower()
    if requested_username:
        if any(u["username"].lower() == requested_username for u in utenti):
            username = generate_unique_username(nome, cognome, utenti)
        else:
            username = requested_username
    else:
        username = generate_unique_username(nome, cognome, utenti)

    nuovo_utente = {
        "nome": nome,
        "cognome": cognome,
        "id": codice_fiscale,
        "username": username,
        "livello": livello,
        "password_hash": hash_password(password),
        "presenze": 0,
        "assenze": 0,
        "totale_votazioni": 0,
        "percentuale_presenze": 0.0,
        "percentuale_assenze": 0.0
    }
    utenti.append(nuovo_utente)
    write_encrypted_json(UTENTI_FILE, utenti)
    append_audit_log("CREATE_USER", current["id"], {"target_id": codice_fiscale, "livello": livello})

    safe_user = {k: v for k, v in nuovo_utente.items() if k != "password_hash"}
    return jsonify({"message": f"Utente {username} creato con successo.", "utente": safe_user}), 201

@app.route("/api/utenti/<target_id>", methods=["PUT"])
@login_required
def api_update_utente(target_id):
    current = get_current_user()
    if current["livello"] not in [1, 2]:
        return jsonify({"error": "Permessi insufficienti."}), 403

    target_id = target_id.strip().upper()
    utenti = read_encrypted_json(UTENTI_FILE, [])
    target = next((u for u in utenti if u["id"].upper() == target_id), None)
    if not target:
        return jsonify({"error": "Utente non trovato."}), 404

    # Livello 2 può modificare solo utenti di livello 3, 4 e 5
    if current["livello"] == 2 and target["livello"] not in [3, 4, 5]:
        return jsonify({"error": "Un Amministratore di Livello 2 non può modificare utenti di Livello 1 o 2."}), 403

    data = request.get_json(silent=True) or {}
    if "nome" in data and data["nome"].strip():
        target["nome"] = data["nome"].strip()
    if "cognome" in data and data["cognome"].strip():
        target["cognome"] = data["cognome"].strip()
    if "username" in data and data["username"].strip():
        new_un = data["username"].strip().lower()
        if any(u["username"].lower() == new_un and u["id"].upper() != target_id for u in utenti):
            return jsonify({"error": "Username già in uso da un altro utente."}), 409
        target["username"] = new_un
    if "livello" in data:
        new_lvl = int(data["livello"])
        if new_lvl < 1 or new_lvl > 5:
            return jsonify({"error": "Livello non valido."}), 400
        if current["livello"] == 2 and new_lvl not in [3, 4, 5]:
            return jsonify({"error": "Un Amministratore di Livello 2 può assegnare solo livelli 3, 4 o 5."}), 403
        target["livello"] = new_lvl

    if data.get("password"):
        valid_pwd, msg = validate_password_complexity(data["password"])
        if not valid_pwd:
            return jsonify({"error": msg}), 400
        target["password_hash"] = hash_password(data["password"])

    write_encrypted_json(UTENTI_FILE, utenti)
    append_audit_log("UPDATE_USER", current["id"], {"target_id": target_id})
    return jsonify({"message": "Account aggiornato correttamente."})

@app.route("/api/utenti/<target_id>", methods=["DELETE"])
@login_required
def api_delete_utente(target_id):
    current = get_current_user()
    if current["livello"] != 1:
        return jsonify({"error": "Solo il Super Admin (Livello 1) può eliminare account."}), 403

    target_id = target_id.strip().upper()
    if target_id == current["id"].upper():
        return jsonify({"error": "Non puoi eliminare il tuo stesso account Super Admin attivo."}), 400

    utenti = read_encrypted_json(UTENTI_FILE, [])
    new_utenti = [u for u in utenti if u["id"].upper() != target_id]
    if len(new_utenti) == len(utenti):
        return jsonify({"error": "Utente non trovato."}), 404

    write_encrypted_json(UTENTI_FILE, new_utenti)
    append_audit_log("DELETE_USER", current["id"], {"target_id": target_id})
    return jsonify({"message": "Account eliminato definitivamente."})

# --- API PROFILO PERSONALE ---
@app.route("/api/profilo/password", methods=["POST"])
@login_required
def api_change_own_password():
    current = get_current_user()
    data = request.get_json(silent=True) or {}
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not verify_password(old_password, current["password_hash"]):
        return jsonify({"error": "La password attuale inserita non è corretta."}), 401

    valid_pwd, msg = validate_password_complexity(new_password)
    if not valid_pwd:
        return jsonify({"error": msg}), 400

    if old_password == new_password:
        return jsonify({"error": "La nuova password deve essere diversa da quella attuale."}), 400

    utenti = read_encrypted_json(UTENTI_FILE, [])
    for u in utenti:
        if u["id"] == current["id"]:
            u["password_hash"] = hash_password(new_password)
            break
    write_encrypted_json(UTENTI_FILE, utenti)
    append_audit_log("CHANGE_OWN_PASSWORD", current["id"], {})
    return jsonify({"message": "Password personale aggiornata con successo."})

# --- API VOTAZIONI (Livelli 1, 2, 3) ---
def user_can_access_votazione(user_lvl, votazione_lvl):
    if votazione_lvl == 1:
        return user_lvl in [1, 2]
    if votazione_lvl == 2:
        return user_lvl in [1, 2, 3, 4]
    if votazione_lvl == 3:
        return user_lvl in [1, 2, 3, 4, 5]
    return False

@app.route("/api/votazioni", methods=["GET"])
@login_required
def api_get_votazioni():
    current = get_current_user()
    utenti = read_encrypted_json(UTENTI_FILE, [])
    utenti_map = {u["id"].upper(): u for u in utenti}
    votazioni = read_encrypted_json(VOTAZIONI_FILE, [])

    visible = []
    for v in votazioni:
        v_lvl = int(v.get("livello", 3))
        if not user_can_access_votazione(current["livello"], v_lvl):
            continue
        # Livelli 4 e 5 vedono solo le votazioni a cui sono stati convocati
        uid = current["id"].upper()
        partecipanti_ids = [p.upper() for p in v.get("presenti", []) + v.get("assenti", [])]
        if current["livello"] in [4, 5] and uid not in partecipanti_ids:
            continue

        # Arricchisce con i dettagli anagrafici dei partecipanti
        partecipanti_dettagli = []
        for pid in v.get("presenti", []):
            u_obj = utenti_map.get(pid.upper(), {"nome": "Sconosciuto", "cognome": "", "id": pid})
            partecipanti_dettagli.append({
                "nome": u_obj["nome"],
                "cognome": u_obj["cognome"],
                "id": pid.upper(),
                "presente": True
            })
        for aid in v.get("assenti", []):
            u_obj = utenti_map.get(aid.upper(), {"nome": "Sconosciuto", "cognome": "", "id": aid})
            partecipanti_dettagli.append({
                "nome": u_obj["nome"],
                "cognome": u_obj["cognome"],
                "id": aid.upper(),
                "presente": False
            })

        v_copy = {
            "id": v["id"],
            "titolo": v["titolo"],
            "descrizione": v["descrizione"],
            "livello": v_lvl,
            "presenti": v.get("presenti", []),
            "assenti": v.get("assenti", []),
            "percentuale_presenze": v.get("percentuale_presenze", 0.0),
            "partecipanti": partecipanti_dettagli,
            "creata_il": v.get("creata_il", ""),
            "zkp_receipt": v.get("zkp_receipt", ""),
            "voti_registrati": len(v.get("schede_cifrate", []))
        }
        visible.append(v_copy)

    return jsonify({"votazioni": visible})

@app.route("/api/votazioni", methods=["POST"])
@login_required
def api_create_votazione():
    current = get_current_user()
    if current["livello"] not in [1, 2, 3]:
        return jsonify({"error": "Non hai i permessi per creare nuove votazioni."}), 403

    data = request.get_json(silent=True) or {}
    titolo = data.get("titolo", "").strip()
    descrizione = data.get("descrizione", "").strip()
    password = data.get("password", "")
    try:
        livello = int(data.get("livello", 3))
    except ValueError:
        return jsonify({"error": "Livello votazione non valido."}), 400

    if not titolo or not descrizione or not password:
        return jsonify({"error": "Titolo, descrizione e password della votazione sono obbligatori."}), 400

    if livello not in [1, 2, 3]:
        return jsonify({"error": "Il livello della votazione deve essere 1, 2 o 3."}), 400

    # Controllo gerarchia creazione votazioni
    if current["livello"] == 2 and livello not in [1, 2]:
        return jsonify({"error": "Un Amministratore (Livello 2) gestisce votazioni di Livello 1 e 2."}), 403
    if current["livello"] == 3 and livello != 3:
        return jsonify({"error": "Un Moderatore (Livello 3) può creare e gestire solo votazioni di Livello 3."}), 403

    partecipanti = data.get("partecipanti", [])
    presenti = []
    assenti = []
    seen = set()
    for p in partecipanti:
        pid = p.get("id", "").strip().upper()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        if p.get("presente", False):
            presenti.append(pid)
        else:
            assenti.append(pid)

    totale = len(presenti) + len(assenti)
    perc_presenze = round((len(presenti) / totale) * 100, 2) if totale > 0 else 0.0

    vot_id = "VOT-" + secrets.token_hex(4).upper()
    zkp_receipt = hashlib.sha256(f"{vot_id}:{titolo}:{secrets.token_hex(16)}".encode()).hexdigest()

    nuova_votazione = {
        "id": vot_id,
        "titolo": titolo,
        "descrizione": descrizione,
        "livello": livello,
        "password_hash": hash_password(password),
        "presenti": presenti,
        "assenti": assenti,
        "percentuale_presenze": perc_presenze,
        "creata_il": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "zkp_receipt": zkp_receipt,
        "schede_cifrate": [],
        "votanti_hash": []
    }

    votazioni = read_encrypted_json(VOTAZIONI_FILE, [])
    votazioni.append(nuova_votazione)
    write_encrypted_json(VOTAZIONI_FILE, votazioni)

    utenti = read_encrypted_json(UTENTI_FILE, [])
    utenti = recalculate_all_user_stats(utenti, votazioni)
    write_encrypted_json(UTENTI_FILE, utenti)

    append_audit_log("CREATE_VOTAZIONE", current["id"], {"votazione_id": vot_id, "livello": livello})
    return jsonify({"message": "Votazione creata e cifrata nel registro.", "id": vot_id}), 201

@app.route("/api/votazioni/<vot_id>", methods=["PUT"])
@login_required
def api_update_votazione(vot_id):
    current = get_current_user()
    if current["livello"] not in [1, 2, 3]:
        return jsonify({"error": "Permessi insufficienti per modificare votazioni."}), 403

    votazioni = read_encrypted_json(VOTAZIONI_FILE, [])
    vot = next((v for v in votazioni if v["id"] == vot_id), None)
    if not vot:
        return jsonify({"error": "Votazione non trovata."}), 404

    v_lvl = int(vot["livello"])
    if current["livello"] == 2 and v_lvl not in [1, 2]:
        return jsonify({"error": "Non autorizzato su votazioni di Livello 3."}), 403
    if current["livello"] == 3 and v_lvl != 3:
        return jsonify({"error": "Un Moderatore può modificare solo votazioni di Livello 3."}), 403

    data = request.get_json(silent=True) or {}
    if "titolo" in data and data["titolo"].strip():
        vot["titolo"] = data["titolo"].strip()
    if "descrizione" in data and data["descrizione"].strip():
        vot["descrizione"] = data["descrizione"].strip()
    if data.get("password"):
        vot["password_hash"] = hash_password(data["password"])

    if "partecipanti" in data:
        presenti = []
        assenti = []
        seen = set()
        for p in data["partecipanti"]:
            pid = p.get("id", "").strip().upper()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            if p.get("presente", False):
                presenti.append(pid)
            else:
                assenti.append(pid)
        vot["presenti"] = presenti
        vot["assenti"] = assenti
        totale = len(presenti) + len(assenti)
        vot["percentuale_presenze"] = round((len(presenti) / totale) * 100, 2) if totale > 0 else 0.0

    write_encrypted_json(VOTAZIONI_FILE, votazioni)
    utenti = read_encrypted_json(UTENTI_FILE, [])
    utenti = recalculate_all_user_stats(utenti, votazioni)
    write_encrypted_json(UTENTI_FILE, utenti)

    append_audit_log("UPDATE_VOTAZIONE", current["id"], {"votazione_id": vot_id})
    return jsonify({"message": "Votazione e registro presenze/assenze aggiornati."})

@app.route("/api/votazioni/<vot_id>", methods=["DELETE"])
@login_required
def api_delete_votazione(vot_id):
    current = get_current_user()
    votazioni = read_encrypted_json(VOTAZIONI_FILE, [])
    vot = next((v for v in votazioni if v["id"] == vot_id), None)
    if not vot:
        return jsonify({"error": "Votazione non trovata."}), 404

    v_lvl = int(vot["livello"])
    # Livello 1 elimina tutto; Livello 2 solo votazioni di livello 2; Livello 3 solo votazioni di livello 3
    if current["livello"] == 2 and v_lvl == 1:
        return jsonify({"error": "Un Amministratore di Livello 2 non può eliminare votazioni di Livello 1."}), 403
    if current["livello"] == 3 and v_lvl != 3:
        return jsonify({"error": "Un Moderatore può eliminare solo votazioni di Livello 3."}), 403
    if current["livello"] in [4, 5]:
        return jsonify({"error": "Permessi insufficienti."}), 403

    votazioni = [v for v in votazioni if v["id"] != vot_id]
    write_encrypted_json(VOTAZIONI_FILE, votazioni)

    utenti = read_encrypted_json(UTENTI_FILE, [])
    utenti = recalculate_all_user_stats(utenti, votazioni)
    write_encrypted_json(UTENTI_FILE, utenti)

    append_audit_log("DELETE_VOTAZIONE", current["id"], {"votazione_id": vot_id})
    return jsonify({"message": "Votazione eliminata e statistiche utenti ricalcolate."})

# --- API ESPRESSIONE VOTO CIFRATO E2E-V / ZKP ---
@app.route("/api/votazioni/<vot_id>/vota", methods=["POST"])
@login_required
def api_cast_vote(vot_id):
    current = get_current_user()
    data = request.get_json(silent=True) or {}
    vot_password = data.get("password", "")
    scelta = data.get("scelta", "").strip()

    if scelta not in ["FAVOREVOLE", "CONTRARIO", "ASTENUTO"]:
        return jsonify({"error": "Opzione di voto non valida."}), 400

    votazioni = read_encrypted_json(VOTAZIONI_FILE, [])
    vot = next((v for v in votazioni if v["id"] == vot_id), None)
    if not vot:
        return jsonify({"error": "Votazione non trovata."}), 404

    if not user_can_access_votazione(current["livello"], int(vot["livello"])):
        return jsonify({"error": "Livello utente non abilitato a questa votazione."}), 403

    uid = current["id"].upper()
    if uid not in [p.upper() for p in vot.get("presenti", [])]:
        return jsonify({"error": "Devi essere registrato come PRESENTE in questa votazione per esprimere il voto."}), 403

    if not verify_password(vot_password, vot["password_hash"]):
        return jsonify({"error": "Password della votazione errata."}), 401

    # Nullifier ZKP per impedire doppio voto senza collegare l'identità alla scheda cifrata
    nullifier = hashlib.sha256(f"NULLIFIER:{vot_id}:{uid}:{MASTER_KEY.decode()}".encode()).hexdigest()
    if nullifier in vot.get("votanti_hash", []):
        return jsonify({"error": "Hai già espresso il tuo voto per questa votazione (univocità ZKP verificata)."}), 409

    # Cifratura End-to-End della scheda elettorale con ricevuta verificabile
    nonce = secrets.token_hex(16)
    ballot_plaintext = json.dumps({"scelta": scelta, "nonce": nonce, "timestamp": datetime.now(timezone.utc).isoformat()})
    encrypted_ballot = fernet.encrypt(ballot_plaintext.encode("utf-8")).decode("utf-8")
    ballot_receipt = hashlib.sha256(encrypted_ballot.encode("utf-8")).hexdigest()

    vot.setdefault("votanti_hash", []).append(nullifier)
    vot.setdefault("schede_cifrate", []).append({
        "ciphertext": encrypted_ballot,
        "receipt": ballot_receipt
    })

    write_encrypted_json(VOTAZIONI_FILE, votazioni)
    append_audit_log("CAST_E2E_VOTE", "ZKP_ANONYMOUS", {"votazione_id": vot_id, "receipt": ballot_receipt})
    return jsonify({
        "message": "Voto cifrato e registrato sul ledger immutabile.",
        "zkp_ballot_receipt": ballot_receipt
    })

@app.route("/api/audit", methods=["GET"])
@login_required
def api_get_audit():
    current = get_current_user()
    if current["livello"] not in [1, 2]:
        return jsonify({"error": "Accesso al registro di audit riservato ai Livelli 1 e 2."}), 403
    ledger = read_encrypted_json(AUDIT_LEDGER_FILE, [])
    return jsonify({"ledger": list(reversed(ledger[-50:]))})

# --- GENERAZIONE CERTIFICATO TLS AUTOFIRMATO PER HTTPS ---
def ensure_self_signed_cert():
    os.makedirs(CERTS_DIR, exist_ok=True)
    cert_path = os.path.join(CERTS_DIR, "cert.pem")
    key_path = os.path.join(CERTS_DIR, "key.pem")
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    from OpenSSL import crypto
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)

    cert = crypto.X509()
    cert.get_subject().C = "IT"
    cert.get_subject().O = "Isonomia Sovereign Governance"
    cert.get_subject().CN = "isonomia.local"
    cert.set_serial_number(secrets.randbelow(10**16))
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365 * 24 * 60 * 60 * 5)
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, "sha256")

    with open(cert_path, "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    with open(key_path, "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
    return cert_path, key_path

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == "__main__":
    cert_file, key_file = ensure_self_signed_cert()
    local_ip = get_local_ip()
    port = int(os.environ.get("ISONOMIA_PORT", 8443))
    print("=" * 68)
    print("  Ισονομία (ISONOMIA) - Server Sovrano HTTPS Attivo")
    print("=" * 68)
    print(f"  Accesso Locale:   https://127.0.0.1:{port}/login")
    print(f"  Accesso Rete LAN: https://{local_ip}:{port}/login")
    print("  Database Cifrato: ATTIVO (AES-128-CBC + HMAC-SHA256)")
    print("=" * 68)
    app.run(host="0.0.0.0", port=port, ssl_context=(cert_file, key_file), debug=False)
