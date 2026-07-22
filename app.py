import streamlit as st
import json
import pandas as pd
import plotly.express as px
import yfinance as yf
import firebase_admin
from firebase_admin import credentials, firestore
import os
import logging

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURAZIONE PAGINA E INIEZIONE CSS/HTML ---
st.set_page_config(page_title="Wealth Management", page_icon="🏦", layout="wide")

st.markdown("""
<style>
/* Riquadri dei totali (Metric Cards) */
div[data-testid="stMetric"] {
    background-color: #1E293B;
    border-radius: 12px;
    padding: 15px 20px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    border-left: 5px solid #3B82F6;
    transition: transform 0.2s ease-in-out;
}
div[data-testid="stMetric"]:hover {
    transform: scale(1.02);
}
/* Intestazioni Tabelle */
th {
    background-color: #0F172A !important;
    color: #94A3B8 !important;
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)

# --- CREDENZIALI DI ACCESSO BLINDATE ---
UTENTI = {
    "enzo": {"psw": st.secrets["passwords"]["enzo"], "ruolo": "admin", "nome_portafoglio": "Enzo"},
    "stefania": {"psw": st.secrets["passwords"]["stefania"], "ruolo": "user", "nome_portafoglio": "Stefania"},
    "mamma": {"psw": st.secrets["passwords"]["mamma"], "ruolo": "user", "nome_portafoglio": "Mamma"},
    "claudia": {"psw": st.secrets["passwords"]["claudia"], "ruolo": "user", "nome_portafoglio": "Claudia"}
}

# --- ORDINE TABS DESIDERATO ---
ORDINE_FAMIGLIA = ["Enzo", "Stefania", "Mamma", "Claudia"]

# --- TITOLI VALIDI (SOURCE OF TRUTH) ---
TITOLI_VALIDI = ["ENI", "LEONARDO", "FERRAGAMO"]

# --- LOGHI AZIENDALI ---
LOGHI_AZIENDE = {
    "ENI": "https://www.google.com/s2/favicons?domain=eni.com&sz=128#.png",
    "LEONARDO": "https://www.google.com/s2/favicons?domain=leonardo.com&sz=128#.png",
    "FERRAGAMO": "https://www.google.com/s2/favicons?domain=ferragamo.com&sz=128#.png"
}

# --- GESTIONE SESSIONE LOGIN ---
if "utente" not in st.session_state:
    st.session_state["utente"] = None
    st.session_state["ruolo"] = None
    st.session_state["nome_portafoglio"] = None

def esegui_login():
    user_input = st.session_state.user_input.lower()
    psw_input = st.session_state.psw_input
    
    if user_input in UTENTI and UTENTI[user_input]["psw"] == psw_input:
        st.session_state["utente"] = user_input
        st.session_state["ruolo"] = UTENTI[user_input]["ruolo"]
        st.session_state["nome_portafoglio"] = UTENTI[user_input]["nome_portafoglio"]
        logger.info(f"✅ Login riuscito: {user_input}")
    else:
        st.error("Credenziali errate.")
        logger.warning(f"❌ Login fallito: {user_input}")

def esegui_logout():
    st.session_state["utente"] = None
    st.session_state["ruolo"] = None
    st.session_state["nome_portafoglio"] = None
    logger.info("Logout eseguito")

# --- SCHERMATA DI LOGIN BLOCCANTE ---
if not st.session_state["utente"]:
    st.title("🏦 Piattaforma Gestione Patrimonio")
    st.markdown("Inserisci le credenziali per accedere al tuo portafoglio sicuro.")
    with st.form("login_form"):
        st.text_input("Utente", key="user_input")
        st.text_input("Password", type="password", key="psw_input")
        st.form_submit_button("Accedi", on_click=esegui_login)
    st.stop()

# ==========================================
# DA QUI IN POI IL CODICE GIRA SOLO SE LOGGATI
# ==========================================

# --- CONNESSIONE A FIREBASE ---
if not firebase_admin._apps:
    cert_dict = dict(st.secrets["firebase"])
    cert_dict["private_key"] = cert_dict["private_key"].replace('\\n', '\n')
    cred = credentials.Certificate(cert_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()
FILE_DATI = 'dati_portafoglio.json'
TASSAZIONE = 0.26

def get_ticker_yahoo(nome_titolo):
    mappa_fissa = {"ENI": "ENI.MI", "LEONARDO": "LDO.MI", "FERRAGAMO": "SFER.MI"}
    if nome_titolo in mappa_fissa:
        return mappa_fissa[nome_titolo]
    if "." not in nome_titolo:
        return f"{nome_titolo}.MI"
    return nome_titolo

def format_ita(valore, decimali=2):
    if decimali == 0:
        str_val = f"{int(valore):,}"
    else:
        str_val = f"{float(valore):,.{decimali}f}"
    return str_val.replace(',', 'X').replace('.', ',').replace('X', '.')

def carica_dati():
    doc_ref = db.collection("patrimonio_famiglia").document("dati_principali")
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    else:
        st.warning("Inizializzazione database online in corso... Ricarica tra 5 secondi.")
        with open(FILE_DATI, 'r') as f:
            dati_locali = json.load(f)
            doc_ref.set(dati_locali)
            return dati_locali

def salva_dati(dati):
    db.collection("patrimonio_famiglia").document("dati_principali").set(dati)

dati = carica_dati()

if dati["dividendi_annui"].get("Leonardo", 0) != 0.63:
    dati["dividendi_annui"]["Leonardo"] = 0.63
    salva_dati(dati)

# --- SIDEBAR (VISIBILE A TUTTI) ---
st.sidebar.title(f"Ciao {st.session_state['nome_portafoglio']}")

foto_profilo = f"{st.session_state['utente']}.jpg"
if os.path.exists(foto_profilo):
    st.sidebar.image(foto_profilo, use_container_width=True)

st.sidebar.button("🚪 Esci (Logout)", on_click=esegui_logout)
st.sidebar.divider()

# --- FUNZIONI AMMINISTRATORE ---
if st.session_state["ruolo"] == "admin":
    st.sidebar.subheader("🌐 Sincronizzazione Borsa")
    if st.sidebar.button("📥 Scarica Prezzi in Tempo Reale"):
        with st.spinner("Connessione a Yahoo Finance in corso..."):
            # ✅ FIX: Usa TITOLI_VALIDI (source of truth) invece di dati["prezzi_attuali"].keys()
            prezzi_aggiornati = {}
            errori = []
            
            for nome_titolo in TITOLI_VALIDI:
                ticker = get_ticker_yahoo(nome_titolo)
                try:
                    stock = yf.Ticker(ticker)
                    dati_storici = stock.history(period="1d")
                    if not dati_storici.empty:
                        prezzo_reale = float(dati_storici['Close'].iloc[-1])
                        prezzi_aggiornati[nome_titolo] = round(prezzo_reale, 2)
                        st.sidebar.success(f"✅ {nome_titolo}: €{round(prezzo_reale, 2)}")
                        logger.info(f"✅ Prezzo scaricato: {nome_titolo} = €{round(prezzo_reale, 2)}")
                    else:
                        errori.append(f"{nome_titolo}: nessun dato")
                        st.sidebar.warning(f"⚠️ {nome_titolo}: nessun dato disponibile")
                        logger.warning(f"⚠️ Nessun dato per {ticker}")
                        
                except ConnectionError as e:
                    errori.append(f"{nome_titolo}: errore connessione")
                    st.sidebar.error(f"🔴 {nome_titolo}: errore connessione a Yahoo Finance")
                    logger.error(f"ConnectionError per {ticker}: {e}")
                    
                except ValueError as e:
                    errori.append(f"{nome_titolo}: ticker non trovato")
                    st.sidebar.warning(f"⚠️ {nome_titolo}: ticker non trovato ({ticker})")
                    logger.warning(f"ValueError per {ticker}: {e}")
                    
                except Exception as e:
                    errori.append(f"{nome_titolo}: {str(e)}")
                    st.sidebar.error(f"🔴 {nome_titolo}: {str(e)}")
                    logger.error(f"Errore sconosciuto per {ticker}: {e}")
            
            # Aggiorna i prezzi nel database
            if prezzi_aggiornati:
                dati["prezzi_attuali"].update(prezzi_aggiornati)
                salva_dati(dati)
                st.sidebar.success(f"✅ Prezzi sincronizzati con successo! ({len(prezzi_aggiornati)} titoli)")
                logger.info(f"✅ Sincronizzazione completata: {len(prezzi_aggiornati)} titoli aggiornati")
            
            if errori:
                st.sidebar.warning(f"⚠️ Errori durante l'aggiornamento:\n" + "\n".join(errori))
            
            st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("🛒 Registra Acquisto")
    with st.sidebar.form("form_acquisto"):
        membro_acquisto = st.selectbox("Chi acquista?", ORDINE_FAMIGLIA)
        titolo_acquisto = st.selectbox("Nome Titolo", TITOLI_VALIDI, key="select_titolo")
        qta_acquisto = st.number_input("Quantità", min_value=1, value=100, step=1)
        prezzo_acquisto = st.number_input("Prezzo di carico (€)", min_value=0.001, value=10.00, step=0.01, format="%.3f")
        submit_acquisto = st.form_submit_button("Conferma Acquisto")
        if submit_acquisto and titolo_acquisto:
            if membro_acquisto not in dati["portafoglio"]: dati["portafoglio"][membro_acquisto] = []
            nuovo_lotto = {"titolo": titolo_acquisto, "quantita": qta_acquisto, "prezzo_carico": prezzo_acquisto}
            dati["portafoglio"][membro_acquisto].append(nuovo_lotto)
            if titolo_acquisto not in dati["prezzi_attuali"]:
                dati["prezzi_attuali"][titolo_acquisto] = prezzo_acquisto
            if titolo_acquisto not in dati["dividendi_annui"]:
                dati["dividendi_annui"][titolo_acquisto] = 0.0
            salva_dati(dati)
            st.sidebar.success(f"✅ Acquisto registrato: {titolo_acquisto}")
            logger.info(f"✅ Acquisto: {membro_acquisto} - {titolo_acquisto} x{qta_acquisto}")
            st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("📉 Registra Vendita")
    membro_vendita = st.sidebar.selectbox("Chi vende?", ORDINE_FAMIGLIA, key="sel_vendita")
    if membro_vendita and membro_vendita in dati["portafoglio"]:
        lotti = dati["portafoglio"][membro_vendita]
        if lotti:
            opzioni_lotti = [f"{i} - {l['titolo']} ({l['quantita']} az. a {format_ita(l['prezzo_carico'], 3)}€)" for i, l in enumerate(lotti)]
            lotto_scelto = st.sidebar.selectbox("Seleziona lotto", opzioni_lotti, key="sel_lotto_vendita")
            if st.sidebar.button("Conferma Vendita (Elimina)"):
                indice = int(lotto_scelto.split(" - ")[0])
                titolo_venduto = dati["portafoglio"][membro_vendita][indice]["titolo"]
                dati["portafoglio"][membro_vendita].pop(indice)
                salva_dati(dati)
                st.sidebar.success(f"✅ Vendita registrata: {titolo_venduto}")
                logger.info(f"✅ Vendita: {membro_vendita} - {titolo_venduto}")
                st.rerun()
        else:
            st.sidebar.info("Nessun titolo.")

# --- LOGICA DI VISUALIZZAZIONE DATI ---
portafoglio_visibile = dati["portafoglio"] if st.session_state["ruolo"] == "admin" else {st.session_state["nome_portafoglio"]: dati["portafoglio"][st.session_state["nome_portafoglio"]]}

totale_investito = 0
totale_attuale = 0
dividendi_annui_lordi = 0
dati_grafico_distribuzione = []

for membro, lotti in portafoglio_visibile.items():
    for lotto in lotti:
        titolo = lotto["titolo"]
        quantita = lotto["quantita"]
        prezzo_carico = lotto["prezzo_carico"]
        prezzo_attuale = dati["prezzi_attuali"].get(titolo, lotto["prezzo_carico"])
        div_per_azione = dati["dividendi_annui"].get(titolo, 0)
        
        investito = quantita * prezzo_carico
        attuale = quantita * prezzo_attuale
        div_totale = quantita * div_per_azione
        
        totale_investito += investito
        totale_attuale += attuale
        dividendi_annui_lordi += div_totale
        
        dati_grafico_distribuzione.append({"Titolo": titolo, "Valore": attuale})

plusvalenza_lorda = totale_attuale - totale_investito
plusvalenza_netta = plusvalenza_lorda * (1 - TASSAZIONE) if plusvalenza_lorda > 0 else plusvalenza_lorda
dividendi_annui_netti = dividendi_annui_lordi * (1 - TASSAZIONE)

# --- DASHBOARD UI ---
titolo_dash = "📊 Dashboard Patrimonio Familiare" if st.session_state["ruolo"] == "admin" else "📊 Il Tuo Portafoglio Personale"
st.title(titolo_dash)

col1, col2, col3, col4 = st.columns(4)
segno_kpi = "+" if plusvalenza_netta > 0 else ""
col1.metric("Valore Attuale", f"{format_ita(totale_attuale)} €", f"{segno_kpi}{format_ita(plusvalenza_netta)} € (Netto)")
col2.metric("Capitale Investito", f"{format_ita(totale_investito)} €")
col3.metric("Plusvalenza Lorda", f"{format_ita(plusvalenza_lorda)} €", f"{segno_kpi}{format_ita(plusvalenza_lorda/totale_investito*100 if totale_investito else 0)}%")
col4.metric("Dividendi Annui Netti", f"{format_ita(dividendi_annui_netti)} €")

st.divider()

if st.session_state["ruolo"] == "admin":
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("Distribuzione Globale per Titolo")
        if dati_grafico_distribuzione:
            df_dist = pd.DataFrame(dati_grafico_distribuzione).groupby("Titolo").sum().reset_index()
            df_dist['Testo_Hover'] = df_dist['Valore'].apply(lambda x: f"{format_ita(x)} €")
            colori_distinti = ['#3B82F6', '#F59E0B', '#10B981', '#8B5CF6', '#EC4899']
            fig_pie = px.pie(df_dist, values='Valore', names='Titolo', hole=0.4, color_discrete_sequence=colori_distinti, custom_data=['Testo_Hover'])
            pull_array = [0.02] * len(df_dist)
            fig_pie.update_traces(pull=pull_array, hovertemplate="<b>%{label}</b><br>Valore: %{customdata[0]}<extra></extra>", marker=dict(line=dict(color='#0E1117', width=2)))
            fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#FAFAFA'))
            st.plotly_chart(fig_pie, use_container_width=True)

    with col_chart2:
        st.subheader("Rapporto Rischio/Rendimento")
        df_bar = pd.DataFrame({"Categoria": ["Investito", "Valore Attuale"], "Importo (€)": [totale_investito, totale_attuale], "Testo": [f"{format_ita(totale_investito)} €", f"{format_ita(totale_attuale)} €"]})
        colori_barre = ['#64748B', '#10B981'] 
        fig_bar = px.bar(df_bar, x="Categoria", y="Importo (€)", color="Categoria", text="Testo", color_discrete_sequence=colori_barre)
        fig_bar.update_traces(width=0.3, textposition='outside', hovertemplate="<b>%{x}</b><br>%{text}<extra></extra>")
        fig_bar.update_layout(showlegend=False, height=600, margin=dict(t=30, b=30), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#FAFAFA'))
        fig_bar.update_yaxes(visible=False)
        st.plotly_chart(fig_bar, use_container_width=True)
    st.divider()

if st.session_state["ruolo"] == "admin":
    st.subheader("👥 Dettaglio per Componente della Famiglia")
    membri_da_mostrare = [m for m in ORDINE_FAMIGLIA if m in portafoglio_visibile]
    tabs = st.tabs(membri_da_mostrare)
else:
    st.subheader("I Tuoi Titoli")
    membri_da_mostrare = [st.session_state["nome_portafoglio"]]
    tabs = [st.container()]

# --- FUNZIONE PER I COLORI DEI SEMAFORI ---
def colora_valori(val):
    if isinstance(val, str):
        if val.startswith('+'):
            return 'color: #10B981; font-weight: bold;' # Verde Smeraldo
        elif val.startswith('-'):
            return 'color: #EF4444; font-weight: bold;' # Rosso Acceso
    return ''

for i, membro in enumerate(membri_da_mostrare):
    with tabs[i]:
        lotti = portafoglio_visibile[membro]
        if not lotti:
            st.info("Nessun titolo in portafoglio attualmente.")
            continue
            
        righe = []
        tot_azioni = 0
        tot_membro_inv = 0
        tot_membro_att = 0
        tot_plus_netta = 0
        tot_div_annuo = 0
        tot_div_trimestrale = 0
        
        for lotto in lotti:
            titolo = lotto["titolo"]
            q = lotto["quantita"]
            pc = lotto["prezzo_carico"]
            pa = dati["prezzi_attuali"].get(titolo, lotto["prezzo_carico"])
            
            inv = q * pc
            att = q * pa
            plus = att - inv
            plus_netta = plus * (1 - TASSAZIONE) if plus > 0 else plus
            div_annuo_netto = (q * dati["dividendi_annui"].get(titolo, 0)) * (1 - TASSAZIONE)
            
            valore_trimestrale = div_annuo_netto / 4 if titolo.upper().strip() == "ENI" else 0
            str_trimestrale = f"{format_ita(valore_trimestrale, 2)} €" if valore_trimestrale > 0 else "-"
            
            segno = "+" if plus_netta > 0 else ""
            
            tot_azioni += q
            tot_membro_inv += inv
            tot_membro_att += att
            tot_plus_netta += plus_netta
            tot_div_annuo += div_annuo_netto
            tot_div_trimestrale += valore_trimestrale
            
            righe.append({
                "Logo": LOGHI_AZIENDE.get(titolo.upper().strip(), ""),
                "Titolo": titolo, 
                "Azioni": format_ita(q, 0), 
                "Prezzo Carico (€)": format_ita(pc, 3),
                "Prezzo Mercato (€)": format_ita(pa, 2), 
                "Investito (€)": format_ita(inv, 2),
                "Valore Attuale (€)": format_ita(att, 2), 
                "Plus/Minus Netta (€)": f"{segno}{format_ita(plus_netta, 2)}",
                "Div. Annuo Netto": f"{format_ita(div_annuo_netto, 2)} €", 
                "Div. Trimestrale Netto": str_trimestrale
            })
        
        segno_tot = "+" if tot_plus_netta > 0 else ""
        str_tot_trimestrale = f"{format_ita(tot_div_trimestrale, 2)} €" if tot_div_trimestrale > 0 else "-"
        
        righe.append({
            "Logo": "",
            "Titolo": "TOTALE", 
            "Azioni": format_ita(tot_azioni, 0), 
            "Prezzo Carico (€)": "-",
            "Prezzo Mercato (€)": "-", 
            "Investito (€)": format_ita(tot_membro_inv, 2),
            "Valore Attuale (€)": format_ita(tot_membro_att, 2), 
            "Plus/Minus Netta (€)": f"{segno_tot}{format_ita(tot_plus_netta, 2)}",
            "Div. Annuo Netto": f"{format_ita(tot_div_annuo, 2)} €", 
            "Div. Trimestrale Netto": str_tot_trimestrale
        })
        
        df = pd.DataFrame(righe)
        
        # Applichiamo il colore verde/rosso ai testi dei profitti e perdite
        styled_df = df.style.map(colora_valori, subset=['Plus/Minus Netta (€)'])
        
        st.dataframe(
            styled_df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Logo": st.column_config.ImageColumn("Logo", width="small")
            }
        )
