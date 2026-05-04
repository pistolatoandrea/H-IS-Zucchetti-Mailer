"""
main.py — FastAPI backend per Zucchetti Mailer
"""

import csv
import io
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Annotated

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

APP_PASSWORD       = os.getenv("APP_PASSWORD")
USERNAME           = os.getenv("ZUCCHETTI_USER")
PASSWORD           = os.getenv("ZUCCHETTI_PASS")
COMPANY            = os.getenv("ZUCCHETTI_COMPANY", "012")
BREVO_API_KEY      = os.getenv("BREVO_API_KEY")
BREVO_TEMPLATES_RAW = os.getenv("BREVO_TEMPLATES", "")

COMPANY_SCUOLA = {"012": "H-IS Venezia", "019": "H-IS Vicenza", "020": "H-IS Rosa"}
SCUOLA = COMPANY_SCUOLA.get(COMPANY, f"Azienda {COMPANY}")

# Email CC per scuola (basata sul campo "scuola" di ogni riga CSV)
SCUOLA_CC = {
    "H-IS Venezia": "amministrazione.ve@h-is.com",
    "H-IS Vicenza":  "amministrazione.ve@h-is.com",
    "H-IS Rosa":     "office.rosa@h-is.com",
}

ENDPOINT = (
    "https://h-farm.zucchetti.com:443"
    "/Infinity/servlet/SQLDataProviderServer/SERVLET/zpcg_qscadenzecli"
)

REQUIRED_COLUMNS = {"codice", "nome", "importo", "email1", "email2", "scuola"}

BASE_DIR = Path(__file__).parent
LOG_DIR  = BASE_DIR / "Brevo Log"
CSV_DIR  = BASE_DIR / "output_csv"
LOG_DIR.mkdir(exist_ok=True)
CSV_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# FastAPI setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Zucchetti Mailer")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

def check_password(request: Request):
    token = request.cookies.get("auth_token") or request.headers.get("X-Auth-Token")
    if token != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Non autorizzato")

AuthDep = Annotated[None, Depends(check_password)]

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ---------------------------------------------------------------------------
# Auth endpoint
# ---------------------------------------------------------------------------

@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    if body.get("password") != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Password errata")
    response = JSONResponse({"ok": True})
    response.set_cookie("auth_token", APP_PASSWORD, httponly=True, samesite="strict")
    return response

@app.post("/api/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("auth_token")
    return response

# ---------------------------------------------------------------------------
# 1. Scarica CSV da Zucchetti
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


def fetch_and_parse(company: str = COMPANY) -> list[dict]:
    scuola = COMPANY_SCUOLA.get(company, f"Azienda {company}")
    body = SOAP_TEMPLATE.format(username=USERNAME, password=PASSWORD, company=company)
    resp = requests.post(
        ENDPOINT,
        data=body.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
        timeout=30,
        verify=True,
    )
    resp.raise_for_status()
    resp.encoding = "utf-8"

    root = ET.fromstring(resp.text)
    ns_prefix = ""
    for el in root.iter():
        if el.tag == "item" or el.tag.endswith("}item"):
            if el.tag.startswith("{"):
                ns_prefix = el.tag.split("}")[0] + "}"
            break

    def get(el, tag):
        child = el.find(f"{ns_prefix}{tag}")
        return child.text.strip() if child is not None and child.text else ""

    records = []
    for item in root.iter(f"{ns_prefix}item"):
        raw = get(item, "SASCASCA")
        try:
            importo = float(raw) if raw else 0.0
        except ValueError:
            importo = 0.0
        records.append({
            "codice":  get(item, "SACODSOG"),
            "nome":    get(item, "KSDESCRI"),
            "importo": importo,
            "email1":  get(item, "OFMAIL"),
            "email2":  get(item, "OFEMAIL2"),
            "scuola":  scuola,
        })
    return records


@app.get("/api/scarica-csv")
def scarica_csv(_: AuthDep, company: str = COMPANY):
    company = company if company in COMPANY_SCUOLA else COMPANY
    try:
        records = fetch_and_parse(company)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["codice", "nome", "importo", "email1", "email2", "scuola"],
        delimiter=";",
    )
    writer.writeheader()
    writer.writerows(records)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    scuola_slug = COMPANY_SCUOLA.get(company, company).replace(" ", "_")
    filename = f"scadenze_{scuola_slug}_{timestamp}.csv"

    # salva copia locale
    (CSV_DIR / filename).write_text(output.getvalue(), encoding="utf-8-sig")

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

# ---------------------------------------------------------------------------
# 2. Carica e valida CSV
# ---------------------------------------------------------------------------

@app.post("/api/carica-csv")
async def carica_csv(_: AuthDep, file: UploadFile = File(...)):
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    # Autorileva il separatore: prova ; poi ,
    first_line = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if ";" in first_line else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)

    if not rows:
        raise HTTPException(status_code=400, detail="Il file CSV è vuoto.")

    cols = set(reader.fieldnames or [])
    missing = REQUIRED_COLUMNS - cols
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Colonne mancanti: {', '.join(sorted(missing))}",
        )

    # restituisce anteprima (max 5 righe) + conteggio
    preview = rows[:5]
    return {
        "ok": True,
        "totale_righe": len(rows),
        "colonne": list(reader.fieldnames),
        "anteprima": preview,
        "rows": rows,  # tutte le righe per l'invio successivo
    }

# ---------------------------------------------------------------------------
# 3. Lista template Brevo
# ---------------------------------------------------------------------------

@app.get("/api/templates")
def get_templates(_: AuthDep):
    """
    Legge BREVO_TEMPLATES dal .env nel formato:
        "Nome Leggibile:ID,Altro Template:ID2"
    """
    result = []
    if BREVO_TEMPLATES_RAW:
        for item in BREVO_TEMPLATES_RAW.split(","):
            parts = item.strip().split(":")
            if len(parts) == 2:
                result.append({"nome": parts[0].strip(), "id": int(parts[1].strip())})
    return result


# ---------------------------------------------------------------------------
# 3b. Preview template Brevo
# ---------------------------------------------------------------------------

@app.get("/api/template-preview/{template_id}")
def get_template_preview(_: AuthDep, template_id: int):
    """
    Chiama l'API Brevo per ottenere subject e htmlContent del template,
    poi sostituisce i {{ params.* }} con etichette leggibili per la preview.
    """
    headers = {
        "api-key": BREVO_API_KEY,
        "Authorization": f"Bearer {BREVO_API_KEY}",
        "Accept": "application/json",
    }
    try:
        r = requests.get(
            f"https://api.brevo.com/v3/smtp/templates/{template_id}",
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Brevo error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "nome":    data.get("name", ""),
        "subject": data.get("subject", ""),
        "html":    data.get("htmlContent", ""),
    }

# ---------------------------------------------------------------------------
# 4. Invio mail (streaming per progress live)
# ---------------------------------------------------------------------------

def format_importo(val) -> str:
    # Formato italiano (es. 1.908,22): la virgola decimale impedisce
    # a Brevo di interpretare il valore come float
    try:
        numero = float(str(val).strip().replace(",", "."))
        intero = f"{int(numero):,}".replace(",", ".")
        decimali = f"{numero:.2f}".split(".")[1]
        return f"{intero},{decimali}"
    except (ValueError, TypeError):
        return str(val).strip() if val is not None else ""


def send_one(row: dict, template_id: int) -> dict:
    recipients = [{"email": row["email1"].strip()}]
    if row.get("email2", "").strip():
        recipients.append({"email": row["email2"].strip()})

    # Sender Address & CC: email amministrativa della scuola corrispondente alla riga
    scuola_val = row.get("scuola", "").strip()
    cc_email   = SCUOLA_CC.get(scuola_val)
    cc         = [{"email": cc_email}] if cc_email else []

    payload = {
        "to": recipients,
        "templateId": template_id,
        "params": {
            "nome":    row.get("nome", "").strip(),
            "importo": format_importo(row.get("importo", "")),
            "scuola":  scuola_val,
            "email1":  row.get("email1", "").strip(),
            "email2":  row.get("email2", "").strip(),
        },
    }
    if cc:
        payload["cc"] = cc

    # Debug: stampa il tipo e valore di importo nel payload
    importo_val = payload["params"]["importo"]
    print(f"[debug] importo type={type(importo_val).__name__} value={repr(importo_val)}")
    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        r = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=15,
        )
        if r.status_code in (200, 201):
            return {"status": "ok", "detail": r.json().get("messageId", "")}
        return {"status": "error", "detail": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/api/invia")
async def invia(request: Request, _: AuthDep):
    body = await request.json()
    rows = body.get("rows", [])
    template_id = int(body.get("template_id", 0))

    if not rows:
        raise HTTPException(status_code=400, detail="Nessuna riga da inviare.")
    if not template_id:
        raise HTTPException(status_code=400, detail="Template non selezionato.")

    results = []

    def generate():
        ok = error = skipped = 0
        for i, row in enumerate(rows, start=1):
            email1 = row.get("email1", "").strip()
            if not email1:
                skipped += 1
                entry = {
                    "i": i,
                    "nome": row.get("nome", ""), "email": "-",
                    "status": "skip", "detail": "nessuna email",
                }
                results.append(entry)
                yield f"data: {json.dumps({**entry, 'totale': len(rows)})}\n\n"
                continue

            result = send_one(row, template_id)
            if result["status"] == "ok":
                ok += 1
            else:
                error += 1

            entry = {
                "i": i,
                "nome": row.get("nome", ""), "email": email1,
                "status": result["status"], "detail": result["detail"],
            }
            results.append(entry)
            # Aggiunge totale solo nel payload SSE (non nel log CSV)
            yield f"data: {json.dumps({**entry, 'totale': len(rows)})}\n\n"
            time.sleep(0.3)

        # salva log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"log_{timestamp}.csv"
        with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["i", "nome", "email", "status", "detail"],
                delimiter=";",
            )
            writer.writeheader()
            writer.writerows(results)

        summary = {
            "done": True, "ok": ok, "error": error,
            "skipped": skipped, "log_file": str(log_path.name),
        }
        yield f"data: {json.dumps(summary)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
