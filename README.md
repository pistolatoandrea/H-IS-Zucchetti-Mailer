# 📬 Zucchetti Mailer

Strumento interno per l'ufficio amministrativo di **H-International School** per l'invio massivo e automatizzato di email di sollecito pagamento ai clienti con rate in sospeso.

---

## Indice

- [Panoramica](#panoramica)
- [Funzionalità principali](#funzionalità-principali)
- [Architettura](#architettura)
- [Requisiti](#requisiti)
- [Installazione e avvio (Docker)](#installazione-e-avvio-docker)
- [Configurazione](#configurazione)
- [Flusso operativo](#flusso-operativo)
- [Struttura del progetto](#struttura-del-progetto)
- [Sicurezza](#sicurezza)

---

## Panoramica

Zucchetti Mailer si integra con il gestionale **Zucchetti Infinity** (via SOAP API) e il servizio di email transazionale **Brevo** per automatizzare il processo di sollecito pagamenti verso i genitori degli studenti delle tre sedi H-IS (Venezia, Vicenza, Rosà).

Il sistema è progettato con un approccio **human-in-the-loop**: prima di ogni invio, l'operatore può scaricare, visualizzare e verificare i dati estratti da Zucchetti, assicurandosi che le email vengano inviate ai destinatari corretti e con importi aggiornati.

---

## Funzionalità principali

- **Estrazione dati da Zucchetti** — scarica automaticamente le scadenze clienti via SOAP API per ciascuna sede
- **Caricamento e validazione CSV** — supporta upload manuale di CSV con rilevamento automatico del separatore e validazione delle colonne obbligatorie
- **Anteprima template email** — visualizza subject e contenuto HTML del template Brevo prima dell'invio
- **Invio massivo con progresso live** — invio email tramite Brevo con aggiornamenti in tempo reale via SSE (Server-Sent Events)
- **CC automatico per sede** — ogni email viene inviata in copia all'ufficio amministrativo della sede di competenza
- **Log degli invii** — ogni sessione di invio genera un file CSV di log con esito per ogni destinatario
- **Autenticazione** — accesso protetto da password via cookie di sessione

---

## Architettura

```
┌─────────────────────────────────────────────────────┐
│                    Browser (UI)                     │
│           FastAPI + Jinja2 + HTML/JS                │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼──────────────────────────────┐
│              Backend FastAPI (main.py)              │
│                                                     │
│  ┌─────────────────┐     ┌───────────────────────┐  │
│  │  Zucchetti SOAP │     │     Brevo REST API    │  │
│  │   (scarica CSV) │     │  (template + invio)   │  │
│  └─────────────────┘     └───────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**Stack tecnologico:**

| Componente | Tecnologia |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Templating | Jinja2 |
| Email transazionale | Brevo API v3 |
| Gestionale | Zucchetti Infinity (SOAP) |
| Deploy | Docker |

---

## Requisiti

- [Docker](https://www.docker.com/get-started) installato sulla macchina locale
- Credenziali Zucchetti Infinity (utente, password, codice azienda)
- API Key Brevo e ID dei template email configurati
- File `.env` fornito dal team IT (vedi [Configurazione](#configurazione))

---

## Installazione e avvio (Docker)

Il deploy avviene **esclusivamente in locale** sulle macchine dei membri autorizzati del team amministrativo.

### 1. Clona o scarica il progetto da Github

[H-IS Zucchetti Mailer Repository Github](https://github.com/pistolatoandrea/H-IS-Zucchetti-Mailer)

Code -> Download ZIP

### 2. Crea il file `.env`

Copia il file di esempio e compila le variabili (vedi sezione [Configurazione](#configurazione)):

```bash
cp .env.example .env
```

### 3. Avvia il container

```bash
docker compose up --build
```

L'applicazione sarà disponibile su: **http://localhost:8000**

### 4. Ferma il container

```bash
docker compose down
```

---

## Guida Utenti

Da condividere con gli utenti che dovranno installare e far girare l'applicazione in locale

[Guida Operativa H-IS Mailer](https://docs.google.com/document/d/e/2PACX-1vTkWENJ8ykZN-6Gh3A5VCG7qj09r1uwBKoXrut1KgtWIYW6vXPPqlC0AD9WfEqCbQ/pub)

## Configurazione

Tutte le variabili sensibili sono gestite tramite file `.env` — **non committare mai questo file nel repository**.

| Variabile | Descrizione |
|---|---|
| `APP_PASSWORD` | Password di accesso all'applicazione |
| `ZUCCHETTI_USER` | Username Zucchetti Infinity |
| `ZUCCHETTI_PASS` | Password Zucchetti Infinity |
| `BREVO_API_KEY` | API Key Brevo |
| `BREVO_TEMPLATES` | Lista template nel formato `Nome1:ID1,Nome2:ID2` |

**Esempio `.env`:**

```env
APP_PASSWORD=password_sicura
ZUCCHETTI_USER=utente
ZUCCHETTI_PASS=password
BREVO_API_KEY=xkeysib-...
BREVO_TEMPLATES=Sollecito Rata:42,Secondo Sollecito:43
```

---

## Flusso operativo

```
1. Login con Password
       │
       ▼
2. Seleziona sede → Scarica CSV da Zucchetti
       │
       ▼
3. Carica CSV manuale
       │
       ▼
4. Verifica anteprima dati e template email
       │
       ▼
5. Seleziona template Brevo → Avvia invio
       │
       ▼
6. Monitora progresso in tempo reale (SSE)
       │
       ▼
7. Consulta log CSV generato in /Brevo Log/
```

---

## Struttura del progetto

```
cartella-principale/
├── Avvio.command
├── Guida_Zucchetti_Mailer.docx
├── Readme.md
└── H-IS-Zucchetti-Mailer-main/           <-- Cartella contenente tutti i file tecnici
    ├── Dockerfile
    ├── docker-compose.yml
    ├── render.yaml
    ├── main.py
    ├── requirements.txt
    ├── .env
    ├── .env.example
    ├── templates/
    ├── static/
    ├── Brevo Log/
    └── output_csv/
```

---

## Sicurezza

- Il deploy è **locale**: l'applicazione non è esposta su internet
- L'accesso è protetto da **password applicativa** trasmessa come cookie `httponly`
- Le credenziali sono gestite esclusivamente tramite variabili d'ambiente nel file `.env`
- Il file `.env` **non deve mai essere condiviso** via email o repository — viene distribuito dal team IT tramite canale sicuro
- I log degli invii e i CSV estratti restano **sulla macchina locale** dell'operatore

---

*Progetto interno — H-International School*