"""
invia_mail.py
-------------
Legge un CSV di scadenze (prodotto da zucchetti_scadenze.py e manipolato
dall'utente) e invia una mail transazionale via Brevo per ogni riga,
usando un template salvato su Brevo.

Utilizzo:
    python3 invia_mail.py <percorso_csv>

Esempio:
    python3 invia_mail.py output_csv/scadenze_clienti_20260320.csv

Dipendenze: requests, python-dotenv
    pip install requests python-dotenv

Variabili d'ambiente richieste nel file .env:
    BREVO_API_KEY      -> API key Brevo (Settings > API Keys)
    BREVO_TEMPLATE_ID  -> ID numerico del template su Brevo
    BREVO_SENDER_EMAIL -> indirizzo mittente verificato su Brevo
    BREVO_SENDER_NAME  -> nome mittente (es. "H-IS Segreteria")
"""

import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

load_dotenv()

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

BREVO_API_KEY      = os.getenv("BREVO_API_KEY")
BREVO_TEMPLATE_ID  = int(os.getenv("BREVO_TEMPLATE_ID", "0"))
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL")
BREVO_SENDER_NAME  = os.getenv("BREVO_SENDER_NAME", "Segreteria")

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"

# Pausa tra un invio e l'altro (secondi) — evita rate limit Brevo
SEND_DELAY = 0.3

# ---------------------------------------------------------------------------
# Validazione configurazione
# ---------------------------------------------------------------------------

def check_config():
    missing = []
    if not BREVO_API_KEY:
        missing.append("BREVO_API_KEY")
    if not BREVO_TEMPLATE_ID:
        missing.append("BREVO_TEMPLATE_ID")
    if not BREVO_SENDER_EMAIL:
        missing.append("BREVO_SENDER_EMAIL")
    if missing:
        raise SystemExit(
            f"[Config Error] Variabili mancanti nel .env: {', '.join(missing)}"
        )

# ---------------------------------------------------------------------------
# Lettura CSV
# ---------------------------------------------------------------------------

def load_csv(path: Path) -> list[dict]:
    """
    Legge il CSV e restituisce la lista di righe come dizionari.
    Salta le righe senza almeno email1 valorizzata (con log).
    """
    rows = []
    skipped = 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for i, row in enumerate(reader, start=2):  # start=2: riga 1 è header
            email1 = row.get("email1", "").strip()
            if not email1:
                print(f"  [skip] riga {i} — '{row.get('nome', '?')}': nessuna email, ignorata.")
                skipped += 1
                continue
            rows.append(row)

    print(f"  {len(rows)} righe caricate, {skipped} saltate (nessuna email).")
    return rows

# ---------------------------------------------------------------------------
# Costruzione destinatari
# ---------------------------------------------------------------------------

def build_recipients(row: dict) -> list[dict]:
    """
    Restituisce la lista destinatari per Brevo nel formato:
        [{"email": "a@b.com"}, {"email": "c@d.com"}]
    email2 viene aggiunta solo se valorizzata.
    """
    recipients = [{"email": row["email1"].strip()}]
    email2 = row.get("email2", "").strip()
    if email2:
        recipients.append({"email": email2})
    return recipients

# ---------------------------------------------------------------------------
# Formattazione importo
# ---------------------------------------------------------------------------

def format_importo(raw: str) -> str:
    """
    Converte "1908.22" in "1.908,22" per la visualizzazione italiana.
    """
    try:
        value = float(raw)
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return raw

# ---------------------------------------------------------------------------
# Invio singola mail
# ---------------------------------------------------------------------------

def send_mail(row: dict, dry_run: bool = False) -> dict:
    """
    Invia la mail per una riga. Restituisce un dict con esito:
        {"nome": ..., "email": ..., "status": "ok"|"error", "detail": ...}
    Se dry_run=True stampa il payload senza inviare.
    """
    recipients = build_recipients(row)

    payload = {
        "sender": {
            "email": BREVO_SENDER_EMAIL,
            "name":  BREVO_SENDER_NAME,
        },
        "to": recipients,
        "templateId": BREVO_TEMPLATE_ID,
        "params": {
            "nome":    row.get("nome", "").strip(),
            "importo": format_importo(row.get("importo", "")),
            "scuola":  row.get("scuola", "").strip(),
            "email1":  row.get("email1", "").strip(),
            "email2":  row.get("email2", "").strip(),
        },
    }

    if dry_run:
        print(f"  [dry-run] {row.get('nome')} → {[r['email'] for r in recipients]}")
        print(f"            params: {json.dumps(payload['params'], ensure_ascii=False)}")
        return {"nome": row.get("nome"), "email": recipients[0]["email"],
                "status": "dry-run", "detail": ""}

    headers = {
        "api-key":      BREVO_API_KEY,
        "Content-Type": "application/json",
        "Accept":       "application/json",
    }

    try:
        resp = requests.post(BREVO_ENDPOINT, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            return {"nome": row.get("nome"), "email": recipients[0]["email"],
                    "status": "ok", "detail": resp.json().get("messageId", "")}
        else:
            return {"nome": row.get("nome"), "email": recipients[0]["email"],
                    "status": "error", "detail": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except requests.exceptions.RequestException as e:
        return {"nome": row.get("nome"), "email": recipients[0]["email"],
                "status": "error", "detail": str(e)}

# ---------------------------------------------------------------------------
# Salvataggio log
# ---------------------------------------------------------------------------

def save_log(results: list[dict], csv_path: Path):
    """
    Salva un file di log CSV nella stessa cartella del CSV di input,
    con suffisso _log_<timestamp>.csv
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = csv_path.parent / "Brevo Log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{csv_path.stem}_log_{timestamp}.csv"

    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["nome", "email", "status", "detail"],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\n  Log salvato: {log_path.resolve()}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    check_config()

    # --- Argomento: path CSV ---
    if len(sys.argv) < 2:
        raise SystemExit(
            "Utilizzo: python3 invia_mail.py <percorso_csv> [--dry-run]\n"
            "Esempio:  python3 invia_mail.py output_csv/scadenze_clienti_20260320.csv"
        )

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        raise SystemExit(f"[Errore] File non trovato: {csv_path}")

    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("*** MODALITA' DRY-RUN: nessuna mail verrà inviata ***\n")

    # --- Caricamento ---
    print(f"-> Lettura CSV: {csv_path}")
    rows = load_csv(csv_path)

    if not rows:
        raise SystemExit("Nessuna riga valida trovata nel CSV. Uscita.")

    # --- Invio ---
    print(f"\n-> Invio mail (template ID: {BREVO_TEMPLATE_ID})...")
    results = []
    ok = error = 0

    for i, row in enumerate(rows, start=1):
        result = send_mail(row, dry_run=dry_run)
        results.append(result)

        status_icon = "OK" if result["status"] in ("ok", "dry-run") else "ERRORE"
        print(f"  [{i}/{len(rows)}] {status_icon} — {result['nome']} → {result['email']}")
        if result["status"] == "error":
            print(f"           {result['detail']}")
            error += 1
        else:
            ok += 1

        if not dry_run:
            time.sleep(SEND_DELAY)

    # --- Riepilogo ---
    print(f"\n-> Riepilogo: {ok} inviate, {error} errori su {len(rows)} righe totali.")

    # --- Log ---
    save_log(results, csv_path)


if __name__ == "__main__":
    main()