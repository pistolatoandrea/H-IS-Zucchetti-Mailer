"""
zucchetti_scadenze.py
---------------------
Chiama il web service SOAP Zucchetti Infinity per le scadenze clienti,
parsa la risposta XML e la esporta in CSV.

Dipendenze: requests, python-dotenv
    pip install requests python-dotenv

Variabili d'ambiente richieste (file .env oppure env di sistema):
    ZUCCHETTI_USER     -> username Zucchetti
    ZUCCHETTI_PASS     -> password Zucchetti
    ZUCCHETTI_COMPANY  -> codice azienda
"""

import os
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

load_dotenv()

USERNAME = os.getenv("ZUCCHETTI_USER")
PASSWORD = os.getenv("ZUCCHETTI_PASS")
COMPANY  = "012" #inserire codice company

COMPANY_SCUOLA = {
    "012": "H-IS Venezia",
    "019": "H-IS Vicenza",
    "020": "H-IS Rosa",
}
SCUOLA = COMPANY_SCUOLA.get(COMPANY, f"Azienda {COMPANY}")

ENDPOINT = (
    "https://h-farm.zucchetti.com:443"
    "/Infinity/servlet/SQLDataProviderServer"
    "/SERVLET/zpcg_qscadenzecli"
)

HEADERS = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": "",   # obbligatorio in SOAP 1.1
}

# ---------------------------------------------------------------------------
# SOAP request
# ---------------------------------------------------------------------------

SOAP_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:zpcg="http://zpcg_qscadenzecli.ws.localhost/">
  <soapenv:Header/>
  <soapenv:Body>
    <zpcg:zpcg_qscadenzecli_TabularQuery>
      <zpcg:m_UserName>{username}</zpcg:m_UserName>
      <zpcg:m_Password>{password}</zpcg:m_Password>
      <zpcg:m_Company>{company}</zpcg:m_Company>
    </zpcg:zpcg_qscadenzecli_TabularQuery>
  </soapenv:Body>
</soapenv:Envelope>"""


def fetch_scadenze() -> str:
    if not USERNAME or not PASSWORD:
        raise ValueError(
            "Credenziali mancanti. "
            "Imposta ZUCCHETTI_USER e ZUCCHETTI_PASS nel file .env"
        )

    body = SOAP_TEMPLATE.format(
        username=USERNAME,
        password=PASSWORD,
        company=COMPANY,
    )

    session = requests.Session()

    try:
        response = session.post(
            ENDPOINT,
            data=body.encode("utf-8"),
            headers=HEADERS,
            timeout=30,
            verify=True,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text

    except requests.exceptions.SSLError as e:
        raise SystemExit(f"[SSL Error] Certificato non valido.\n{e}")
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(f"[Connection Error] Impossibile raggiungere l'endpoint.\n{e}")
    except requests.exceptions.HTTPError as e:
        raise SystemExit(
            f"[HTTP {response.status_code}] Risposta di errore dal server.\n"
            f"{response.text[:500]}"
        )

# ---------------------------------------------------------------------------
# Parsing XML
# ---------------------------------------------------------------------------

def parse_response(xml_text: str) -> list[dict]:
    """
    Parsa la risposta SOAP e restituisce una lista di dizionari.

    Strategia namespace: ElementTree rappresenta i tag con namespace come
    "{http://...}tagname". Rileviamo il prefisso automaticamente cercando
    il primo tag che finisce con 'item', poi usiamo lo stesso prefisso
    per trovare i tag figlio di ogni record.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise SystemExit(f"[Parse Error] La risposta non e' XML valido.\n{e}")

    # Rilevamento automatico del namespace
    ns_prefix = ""
    for el in root.iter():
        tag = el.tag
        if tag == "item" or tag.endswith("}item"):
            if tag.startswith("{"):
                ns_prefix = tag.split("}")[0] + "}"
            break

    item_tag = f"{ns_prefix}item"
    items = list(root.iter(item_tag))

    print(f"  [debug] namespace rilevato : '{ns_prefix}'")
    print(f"  [debug] item tag cercato   : '{item_tag}'")
    print(f"  [debug] item trovati       : {len(items)}")

    def get(el, tag: str) -> str:
        child = el.find(f"{ns_prefix}{tag}")
        return child.text.strip() if child is not None and child.text else ""

    records = []
    for item in items:
        raw_importo = get(item, "SASCASCA")
        try:
            importo = float(raw_importo) if raw_importo else 0.0
        except ValueError:
            importo = 0.0

        records.append({
            "codice":  get(item, "SACODSOG"),
            "nome":    get(item, "KSDESCRI"),
            "importo": importo,
            "email1":  get(item, "OFMAIL"),
            "email2":  get(item, "OFEMAIL2"),
            "scuola":  SCUOLA,
        })

    return records

# ---------------------------------------------------------------------------
# Esportazione CSV
# ---------------------------------------------------------------------------

CSV_FIELDS = ["codice", "nome", "importo", "email1", "email2", "scuola"]


def export_csv(records: list[dict], output_path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=CSV_FIELDS,
            delimiter=";",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(records)

    return output_path

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("-> Chiamata SOAP in corso...")
    xml_text = fetch_scadenze()
    print("  Risposta ricevuta.")

    print("-> Parsing XML...")
    records = parse_response(xml_text)
    print(f"  {len(records)} record trovati.")

    total = sum(r["importo"] for r in records)
    print(f"  Totale importi: EUR {total:,.2f}\n")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_dir = Path(__file__).parent
    output_file = script_dir / "output_csv" / f"scadenze_clienti_{SCUOLA}_{timestamp}.csv"

    print(f"-> Esportazione CSV: {output_file}")
    export_csv(records, output_file)
    print(f"  File scritto: {output_file.resolve()}")


if __name__ == "__main__":
    main()