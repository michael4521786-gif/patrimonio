# 🏦 Gestione Patrimonio Familiare

Piattaforma Streamlit per tracciare portafogli azionari familiari con autenticazione multi-utente.

## Prerequisiti
- Python 3.9+
- Firebase project con credentials

## Setup

### 1. Clone e dipendenze
\`\`\`bash
pip install -r requirements.txt
\`\`\`

### 2. Secrets (Streamlit)
Crea `.streamlit/secrets.toml`:
\`\`\`toml
[firebase]
type = "service_account"
project_id = "..."
private_key = "..."
# ... resto delle credenziali Firebase

[passwords]
enzo = "..."
stefania = "..."
mamma = "..."
claudia = "..."

[tax]
capital_gains = 0.26
dividends = 0.26
\`\`\`

### 3. Avvia l'app
\`\`\`bash
streamlit run app.py
\`\`\`

## Architettura

- **Login**: Hash bcrypt per password
- **Database**: Firestore (utenti, portafoglio, prezzi)
- **Prezzi**: Yahoo Finance real-time (admin only)
- **Ruoli**: Admin (vede tutto) / User (vede solo suo portafoglio)