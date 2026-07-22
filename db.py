import firebase_admin
from firebase_admin import credentials, firestore
import bcrypt
import streamlit as st

# --- INIZIALIZZAZIONE DB ---
def init_firebase():
    if not firebase_admin._apps:
        cert_dict = dict(st.secrets["firebase"])
        cert_dict["private_key"] = cert_dict["private_key"].replace('\\n', '\n')
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

db_client = init_firebase()

# --- SETUP INIZIALE (MIGRAZIONE) ---
def setup_iniziale_db():
    if db_client.collection("utenti").document("enzo").get().exists:
        return

    vecchio_doc = db_client.collection("patrimonio_famiglia").document("dati_principali").get()
    vecchi_dati = vecchio_doc.to_dict() if vecchio_doc.exists else {"portafoglio": {}, "prezzi_attuali": {}, "dividendi_annui": {}}

    db_client.collection("mercato").document("prezzi_e_dividendi").set({
        "prezzi_attuali": vecchi_dati.get("prezzi_attuali", {}),
        "dividendi_annui": vecchi_dati.get("dividendi_annui", {})
    })

    mappa_setup = {
        "enzo": {"ruolo": "admin", "nome_portafoglio": "Enzo"},
        "stefania": {"ruolo": "user", "nome_portafoglio": "Stefania"},
        "mamma": {"ruolo": "user", "nome_portafoglio": "Mamma"},
        "claudia": {"ruolo": "user", "nome_portafoglio": "Claudia"}
    }
    
    for user_id, info in mappa_setup.items():
        psw_chiara = st.secrets["passwords"].get(user_id, "1234")
        salt = bcrypt.gensalt()
        psw_hash = bcrypt.hashpw(psw_chiara.encode('utf-8'), salt).decode('utf-8')
        
        db_client.collection("utenti").document(user_id).set({
            "password_hash": psw_hash,
            "ruolo": info["ruolo"],
            "nome_portafoglio": info["nome_portafoglio"],
            "portafoglio": vecchi_dati.get("portafoglio", {}).get(info["nome_portafoglio"], [])
        })

# ⬅️ ESECUZIONE SINGOLA: Python legge questa riga solo al primo avvio del server!
setup_iniziale_db()

# --- AUTENTICAZIONE ---
def verifica_credenziali(user_input, psw_input):
    doc = db_client.collection("utenti").document(user_input).get()
    if doc.exists:
        dati_utente = doc.to_dict()
        hash_salvato = dati_utente.get("password_hash", "").encode('utf-8')
        if bcrypt.checkpw(psw_input.encode('utf-8'), hash_salvato):
            return True, dati_utente
    return False, None

# --- LETTURA DATI ---
def carica_dati_autorizzati(utente, ruolo):
    dati = {"portafoglio": {}, "prezzi_attuali": {}, "dividendi_annui": {}}
    
    doc_mercato = db_client.collection("mercato").document("prezzi_e_dividendi").get()
    if doc_mercato.exists:
        mercato = doc_mercato.to_dict()
        dati["prezzi_attuali"] = mercato.get("prezzi_attuali", {})
        dati["dividendi_annui"] = mercato.get("dividendi_annui", {})
        
    if ruolo == "admin":
        utenti_docs = db_client.collection("utenti").stream()
        for u in utenti_docs:
            u_data = u.to_dict()
            nome_port = u_data.get("nome_portafoglio")
            dati["portafoglio"][nome_port] = u_data.get("portafoglio", [])
    else:
        doc_utente = db_client.collection("utenti").document(utente).get()
        if doc_utente.exists:
            u_data = doc_utente.to_dict()
            nome_port = u_data.get("nome_portafoglio")
            dati["portafoglio"][nome_port] = u_data.get("portafoglio", [])
            
    return dati

# --- TRANSAZIONI ATOMIC (SCRITTURA) ---
@firestore.transactional
def _transazione_acquisto(transaction, user_ref, mercato_ref, nuovo_lotto, titolo, prezzo):
    user_snap = user_ref.get(transaction=transaction)
    mercato_snap = mercato_ref.get(transaction=transaction)
    
    user_dati = user_snap.to_dict() or {}
    portafoglio = user_dati.get("portafoglio", [])
    mercato_dati = mercato_snap.to_dict() if mercato_snap.exists else {"prezzi_attuali": {}, "dividendi_annui": {}}
    
    portafoglio.append(nuovo_lotto)
    
    aggiorna_merc = False
    if titolo not in mercato_dati.get("prezzi_attuali", {}):
        if "prezzi_attuali" not in mercato_dati: mercato_dati["prezzi_attuali"] = {}
        if "dividendi_annui" not in mercato_dati: mercato_dati["dividendi_annui"] = {}
        mercato_dati["prezzi_attuali"][titolo] = prezzo
        mercato_dati["dividendi_annui"][titolo] = 0.0
        aggiorna_merc = True
        
    transaction.update(user_ref, {"portafoglio": portafoglio})
    if aggiorna_merc:
        transaction.set(mercato_ref, mercato_dati, merge=True)
    return True

def registra_acquisto(user_id, nuovo_lotto, titolo, prezzo):
    user_ref = db_client.collection("utenti").document(user_id)
    mercato_ref = db_client.collection("mercato").document("prezzi_e_dividendi")
    transaction = db_client.transaction()
    return _transazione_acquisto(transaction, user_ref, mercato_ref, nuovo_lotto, titolo, prezzo)

@firestore.transactional
def _transazione_vendita(transaction, user_ref, indice):
    user_snap = user_ref.get(transaction=transaction)
    user_dati = user_snap.to_dict() or {}
    portafoglio = user_dati.get("portafoglio", [])
    
    if 0 <= indice < len(portafoglio):
        portafoglio.pop(indice)
        transaction.update(user_ref, {"portafoglio": portafoglio})
        return True
    return False

def registra_vendita(user_id, indice):
    user_ref = db_client.collection("utenti").document(user_id)
    transaction = db_client.transaction()
    return _transazione_vendita(transaction, user_ref, indice)

def salva_mercato(prezzi, dividendi):
    db_client.collection("mercato").document("prezzi_e_dividendi").set({
        "prezzi_attuali": prezzi,
        "dividendi_annui": dividendi
    })
