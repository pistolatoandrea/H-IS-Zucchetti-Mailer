#!/bin/bash

# Vai nella cartella dove si trova questo file
cd "$(dirname "$0")"

# Entra nella cartella del progetto
cd "H-IS-Zucchetti-Mailer-main" || { 
  echo "❌ Cartella 'H-IS-Zucchetti-Mailer-main' non trovata."; 
  read -p "Premi Invio per chiudere..."; 
  exit 1; 
}

# Controlla che Docker sia avviato
if ! docker info > /dev/null 2>&1; then
  echo "❌ Docker non è avviato. Apri Docker Desktop e riprova."
  read -p "Premi Invio per chiudere..."
  exit 1
fi

# Controlla che esista il file .env
if [ ! -f ".env" ]; then
  echo "❌ File .env non trovato nella cartella 'zucchetti-mailer'."
  read -p "Premi Invio per chiudere..."
  exit 1
fi

echo "🚀 Avvio dell'app in corso..."
docker compose up --build -d

echo ""
echo "✅ App avviata! Aprila nel browser:"
echo "👉 http://localhost:8000"
echo ""

# Apri automaticamente il browser
open http://localhost:8000

echo "Per fermare l'app, esegui: docker compose down"
read -p "Premi Invio per chiudere questa finestra..."