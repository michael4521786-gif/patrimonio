import firebase_admin
from firebase_admin import credentials, firestore
import bcrypt
import streamlit as st
import logging

logger = logging.getLogger(__name__)

# --- INIZIALIZZAZIONE FIREBASE ---
def init_firebase():
    """Inizializza Firebase (singleton pattern)"""
    if not firebase_admin._apps:
        cert_dict = dict(st.secrets["firebase"])
        cert_dict["private_key"] = cert_dict["private_key"].replace('\\n', '\n')
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_firebase()

# --- SETUP INIZIALE DATABASE ---
def setup_iniziale_db():
    """Migrazione e setup automatico al primo avvio"""
    try:
        if db.collection("utenti").document("enzo").get().exists:
            logger.info("Database già inizializzato")
            return
    except:
        pass
    
    logger.info("Inizializzazione database...")
    
    # Crea collection mercato con prezzi iniziali
    db.collection("mercato").document("prezzi_e_dividendi").set({
        "prezzi_attuali": {"ENI": 0.0, "LEONARDO": 0.0, "FERRAGAMO": 0.0},
        "dividendi_annui": {"ENI": 0.0, "LEONARDO": 0.0, "FERRAGAMO": 0.0}
    })
    
    # Setup utenti con password hashate
    mappa_setup = {
        "enzo": {"ruolo": "admin", "nome_portafoglio": "Enzo"},
        "stefania": {"ruolo": "user", "nome_portafoglio": "Stefania"},
        "mamma": {"ruolo": "user", "nome_portafoglio": "Mamma"},
        "claudia": {"ruolo": "user", "nome_portafoglio": "Claudia"}
    }
    
    for user_id, info in mappa_setup.items():
        psw_chiara = st.secrets.get("passwords", {}).get(user_id, "1234")
        salt = bcrypt.gensalt()
        psw_hash = bcrypt.hashpw(psw_chiara.encode('utf-8'), salt).decode('utf-8')
        
        db.collection("utenti").document(user_id).set({
            "password_hash": psw_hash,
            "ruolo": info["ruolo"],
            "nome_portafoglio": info["nome_portafoglio"],
            "portafoglio": []
        })
        logger.info(f"✅ Utente creato: {user_id} ({info['nome_portafoglio']})")

# Esecuzione singola al caricamento del modulo
try:
    setup_iniziale_db()
except Exception as e:
    logger.error(f"Errore setup database: {e}")

# --- AUTENTICAZIONE ---
def verifica_credenziali(user_input, psw_input):
    """
    Verifica le credenziali dell'utente con bcrypt
    Ritorna: (successo: bool, dati_utente: dict)
    """
    try:
        doc = db.collection("utenti").document(user_input).get()
        
        if not doc.exists:
            logger.warning(f"❌ Login fallito: utente '{user_input}' non trovato")
            return False, {}
        
        dati_utente = doc.to_dict()
        hash_salvato = dati_utente.get("password_hash", "").encode('utf-8')
        psw_bytes = psw_input.encode('utf-8')
        
        if bcrypt.checkpw(psw_bytes, hash_salvato):
            logger.info(f"✅ Login riuscito: {user_input}")
            return True, dati_utente
        else:
            logger.warning(f"❌ Login fallito: password errata per '{user_input}'")
            return False, {}
    
    except Exception as e:
        logger.error(f"Errore verifica credenziali: {e}")
        return False, {}

# --- CARICAMENTO DATI CON AUTORIZZAZIONE ---
def carica_dati_autorizzati(utente, ruolo):
    """
    Carica i dati con autorizzazione basata su ruolo
    - Admin: vede TUTTO (tutti i portafogli + prezzi + dividendi)
    - User: vede SOLO il suo portafoglio + prezzi comuni
    """
    dati = {"portafoglio": {}, "prezzi_attuali": {}, "dividendi_annui": {}}
    
    try:
        # Carica prezzi e dividendi (accessibili a tutti)
        doc_mercato = db.collection("mercato").document("prezzi_e_dividendi").get()
        if doc_mercato.exists:
            mercato = doc_mercato.to_dict()
            dati["prezzi_attuali"] = mercato.get("prezzi_attuali", {})
            dati["dividendi_annui"] = mercato.get("dividendi_annui", {})
        
        # Carica portafoglio in base al ruolo
        if ruolo == "admin":
            # Admin vede TUTTI i portafogli
            utenti_docs = db.collection("utenti").stream()
            for u in utenti_docs:
                u_data = u.to_dict()
                nome_port = u_data.get("nome_portafoglio")
                if nome_port:
                    dati["portafoglio"][nome_port] = u_data.get("portafoglio", [])
        else:
            # User vede solo il SUO portafoglio
            doc_utente = db.collection("utenti").document(utente).get()
            if doc_utente.exists:
                u_data = doc_utente.to_dict()
                nome_port = u_data.get("nome_portafoglio")
                if nome_port:
                    dati["portafoglio"][nome_port] = u_data.get("portafoglio", [])
        
        logger.info(f"✅ Dati caricati per {utente} (ruolo: {ruolo})")
        return dati
    
    except Exception as e:
        logger.error(f"Errore carica dati: {e}")
        return dati

# --- TRANSAZIONI ATOMIC (ACID) ---
@firestore.transactional
def _transazione_acquisto(transaction, user_ref, mercato_ref, nuovo_lotto, titolo, prezzo):
    """
    Transazione ATOMIC per l'acquisto di un titolo
    Garantisce ACID: Atomicity, Consistency, Isolation, Durability
    """
    user_snap = user_ref.get(transaction=transaction)
    mercato_snap = mercato_ref.get(transaction=transaction)
    
    user_dati = user_snap.to_dict() or {}
    portafoglio = user_dati.get("portafoglio", [])
    mercato_dati = mercato_snap.to_dict() if mercato_snap.exists else {"prezzi_attuali": {}, "dividendi_annui": {}}
    
    # Aggiungi il nuovo lotto
    portafoglio.append(nuovo_lotto)
    
    # Inizializza strutture se necessario
    if "prezzi_attuali" not in mercato_dati:
        mercato_dati["prezzi_attuali"] = {}
    if "dividendi_annui" not in mercato_dati:
        mercato_dati["dividendi_annui"] = {}
    
    # Aggiungi il titolo al mercato se non esiste
    if titolo not in mercato_dati["prezzi_attuali"]:
        mercato_dati["prezzi_attuali"][titolo] = prezzo
        mercato_dati["dividendi_annui"][titolo] = 0.0
    
    # ATOMIC: aggiorna CONTEMPORANEAMENTE (tutto o niente)
    transaction.update(user_ref, {"portafoglio": portafoglio})
    transaction.set(mercato_ref, mercato_dati, merge=True)
    
    logger.info(f"✅ Transazione acquisto: {titolo} x{nuovo_lotto['quantita']}")
    return True

@firestore.transactional
def _transazione_vendita(transaction, user_ref, indice):
    """
    Transazione ATOMIC per la vendita (rimozione) di un titolo
    """
    user_snap = user_ref.get(transaction=transaction)
    user_dati = user_snap.to_dict() or {}
    portafoglio = user_dati.get("portafoglio", [])
    
    if 0 <= indice < len(portafoglio):
        titolo_venduto = portafoglio[indice]["titolo"]
        portafoglio.pop(indice)
        transaction.update(user_ref, {"portafoglio": portafoglio})
        logger.info(f"✅ Transazione vendita: {titolo_venduto}")
        return True
    
    logger.warning(f"❌ Vendita fallita: indice {indice} non valido")
    return False

# --- OPERAZIONI PUBBLICHE ---
def registra_acquisto(user_id, nuovo_lotto, titolo, prezzo):
    """Registra un acquisto in modo ATOMIC"""
    try:
        user_ref = db.collection("utenti").document(user_id)
        mercato_ref = db.collection("mercato").document("prezzi_e_dividendi")
        transaction = db.transaction()
        _transazione_acquisto(transaction, user_ref, mercato_ref, nuovo_lotto, titolo, prezzo)
    except Exception as e:
        logger.error(f"❌ Errore registrazione acquisto: {e}")
        raise

def registra_vendita(user_id, indice):
    """Registra una vendita in modo ATOMIC"""
    try:
        user_ref = db.collection("utenti").document(user_id)
        transaction = db.transaction()
        return _transazione_vendita(transaction, user_ref, indice)
    except Exception as e:
        logger.error(f"❌ Errore registrazione vendita: {e}")
        raise

def salva_mercato(prezzi, dividendi):
    """Salva i prezzi e dividendi attuali nel database"""
    try:
        db.collection("mercato").document("prezzi_e_dividendi").set({
            "prezzi_attuali": prezzi,
            "dividendi_annui": dividendi
        })
        logger.info(f"✅ Mercato aggiornato: {len(prezzi)} titoli")
    except Exception as e:
        logger.error(f"❌ Errore salvataggio mercato: {e}")
        raise
