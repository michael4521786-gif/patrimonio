import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import os
import bcrypt
import logging
import db
import time

# --- CONFIGURAZIONE LOGGING ---
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- CONFIGURAZIONE PAGINA E INIEZIONE CSS ---
st.set_page_config(page_title="Wealth Management", page_icon="🏦", layout="wide")

st.markdown("""
<style>
div[data-testid="stMetric"] {
    background-color: rgba(130, 150, 180, 0.15);
    border-radius: 12px;
    padding: 15px 20px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    border-left: 5px solid #3B82F6;
    transition: transform 0.2s ease-in-out;
}
div[data-testid="stMetric"]:hover {
    transform: scale(1.02);
}
th {
    background-color: rgba(130, 150, 180, 0.2) !important;
    color: inherit !important;
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)

# --- MAPPE UTILI E CONFIGURAZIONE FISCALE ---
ORDINE_FAMIGLIA = ["Enzo", "Stefania", "Mamma", "Claudia"]
ID_UTENTI = {"Enzo": "enzo", "Stefania": "stefania", "Mamma": "mamma", "Claudia": "claudia"}
LOGHI_AZIENDE = {
    "ENI": "https://www.google.com/s2/favicons?domain=eni.com&sz=128#.png",
    "LEONARDO": "https://www.google.com/s2/favicons?domain=leonardo.com&sz=128#.png",
    "FERRAGAMO": "https://www.google.com/s2/favicons?domain=ferragamo.com&sz=128#.png"
}
TITOLI_VALIDI = ["ENI", "LEONARDO", "FERRAGAMO"]

ALIQUOTE_TASSE = {
    "plusvalenza": float(st.secrets.get("tax", {}).get("capital_gains", 0.26)),
    "dividendi": float(st.secrets.get("tax", {}).get("dividends", 0.26)),
}

# --- GESTIONE SESSIONE ---
if "utente" not in st.session_state:
    st.session_state["utente"] = None
    st.session_state["ruolo"] = None
    st.session_state["nome_portafoglio"] = None

# --- LOGICA DI LOGIN ---
def esegui_login():
    user_input = st.session_state.user_input.lower()
    psw_input = st.session_state.psw_input
    
    successo, dati_utente = db.verifica_credenziali(user_input, psw_input)
    
    if successo:
        st.session_state["utente"] = user_input
        st.session_state["ruolo"] = dati_utente["ruolo"]
        st.session_state["nome_portafoglio"] = dati_utente["nome_portafoglio"]
        logger.info(f"Login effettuato con successo: {user_input}")
    else:
        logger.warning(f"Tentativo di login fallito per utente: {user_input}")
        st.error("Credenziali errate o utente inesistente.")

def esegui_logout():
    st.session_state["utente"] = None
    st.session_state["ruolo"] = None
    st.session_state["nome_portafoglio"] = None

# --- SCHERMATA DI LOGIN BLOCCANTE ---
if not st.session_state["utente"]:
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col_spacer_sx, col_centro, col_spacer_dx = st.columns([1, 1.2, 1])
    
    with col_centro:
        st.markdown("<div style='text-align: center; font-size: 70px; color: #3B82F6;'>🏦</div>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center; margin-bottom: 25px; font-family: sans-serif;'>Gestione Patrimonio</h3>", unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            st.text_input("Nome utente", key="user_input")
            st.text_input("Password", type="password", key="psw_input")
            st.form_submit_button("Login", on_click=esegui_login, type="primary", use_container_width=True)
            
    st.stop()

# --- RECUPERO DATI AUTORIZZATI ---
@st.cache_data(ttl=60)
def carica_dati_autorizzati_cached(utente, ruolo):
    return db.carica_dati_autorizzati(utente, ruolo)

dati = carica_dati_autorizzati_cached(st.session_state["utente"], st.session_state["ruolo"])

# --- FUNZIONI DI SUPPORTO ---
def get_ticker_alpha(nome_titolo):
    mappa_fissa = {"ENI": "ENI.MI", "LEONARDO": "LDO.MI", "FERRAGAMO": "SFER.MI"}
    return mappa_fissa.get(nome_titolo, f"{nome_titolo}.MI" if "." not in nome_titolo else nome_titolo)

def format_ita(valore, decimali=2):
    str_val = f"{int(valore):,}" if decimali == 0 else f"{float(valore):,.{decimali}f}"
    return str_val.replace(',', 'X').replace('.', ',').replace('X', '.')

def scarica_prezzo_alpha_vantage(ticker):
    api_key = st.secrets.get("alphavantage", {}).get("key", "demo")
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            quote = data.get("Global Quote", {})
            prezzo_str = quote.get("05. price")
            
            if prezzo_str:
                prezzo = float(prezzo_str)
                if prezzo > 0:
                    return round(prezzo, 2)
                    
        logger.warning(f"Impossibile leggere il prezzo per {ticker} da Alpha Vantage.")
    except Exception as e:
        logger.error(f"Errore di connessione ad Alpha Vantage per {ticker}: {e}")
        
    return None

# --- SIDEBAR CON SCUDO ARALDICO ---
st.sidebar.title(f"Ciao {st.session_state['nome_portafoglio']}")

iniziale = st.session_state["nome_portafoglio"][0].upper()
st.sidebar.markdown(f"""
    <div style="
        width: 90px; 
        height: 100px; 
        border-radius: 12px 12px 45px 45px;
        background: linear-gradient(135deg, #7A0016 0%, #3B0008 100%);
        border: 4px solid #D4AF37;
        color: #FDF5E6;
        display: flex; 
        align-items: center; 
        justify-content: center; 
        font-size: 55px; 
        font-family: 'Times New Roman', Times, serif;
        font-weight: bold;
        margin-bottom: 20px;
        box-shadow: 0 6px 12px rgba(0,0,0,0.5), inset 0 0 15px rgba(0,0,0,0.7);
        text-shadow: 3px 3px 6px rgba(0,0,0,0.8);
    ">
        {iniziale}
    </div>
""", unsafe_allow_html=True)

st.sidebar.button("🚪 Esci (Logout)", on_click=esegui_logout)
st.sidebar.divider()

# --- FUNZIONI AMMINISTRATORE ---
if st.session_state["ruolo"] == "admin":
    st.sidebar.subheader("🌐 Sincronizzazione Borsa")
    if st.sidebar.button("📥 Scarica Prezzi in Tempo Reale"):
        with st.spinner("⏳ Scaricamento prezzi da Alpha Vantage..."):
            prezzi_aggiornati = {}
            titoli_aggiornati = []
            errori = []
            
            for nome_titolo in TITOLI_VALIDI:
                ticker = get_ticker_alpha(nome_titolo)
                logger.info(f"Scaricamento {nome_titolo} ({ticker}) via Alpha Vantage...")
                
                prezzo = scarica_prezzo_alpha_vantage(ticker)
                
                if prezzo is not None and prezzo > 0:
                    prezzi_aggiornati[nome_titolo] = prezzo
                    titoli_aggiornati.append(nome_titolo)
                    st.sidebar.success(f"✅ {nome_titolo}: €{prezzo:.2f}")
                else:
                    errori.append(nome_titolo)
                    st.sidebar.warning(f"⚠️ {nome_titolo}: prezzo non disponibile")
                
                time.sleep(1)
            
            if titoli_aggiornati:
                dati["prezzi_attuali"].update(prezzi_aggiornati)
                db.salva_mercato(dati["prezzi_attuali"], dati["dividendi_annui"])
                st.sidebar.success(f"✅ Sincronizzati {len(titoli_aggiornati)}/{len(TITOLI_VALIDI)} titoli!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.sidebar.error("❌ Impossibile scaricare i prezzi. Verifica l'API key di Alpha Vantage nei secrets.")

    st.sidebar.divider()
    st.sidebar.subheader("🛒 Registra Acquisto")
    with st.sidebar.form("form_acquisto"):
        membro_acquisto = st.selectbox("Chi acquista?", ORDINE_FAMIGLIA)
        titolo_acquisto = st.selectbox("Nome Titolo", TITOLI_VALIDI)
        qta_acquisto = st.number_input("Quantità", min_value=1, value=100, step=1)
        prezzo_acquisto = st.number_input("Prezzo di carico (€)", min_value=0.001, value=10.00, step=0.01, format="%.3f")
        submit_acquisto = st.form_submit_button("Conferma Acquisto")
        
        if submit_acquisto and titolo_acquisto:
            user_id = ID_UTENTI.get(membro_acquisto)
            if user_id:
                nuovo_lotto = {"titolo": titolo_acquisto, "quantita": qta_acquisto, "prezzo_carico": prezzo_acquisto}
                try:
                    db.registra_acquisto(user_id, nuovo_lotto, titolo_acquisto, prezzo_acquisto)
                    st.success("Acquisto registrato con successo! ✅")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    logger.error(f"Transazione acquisto fallita: {e}")
                    st.error(f"Transazione fallita: {e}")

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
                user_id = ID_UTENTI.get(membro_vendita)
                if user_id:
                    try:
                        success = db.registra_vendita(user_id, indice)
                        if success:
                            st.success("Vendita completata! ✅")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Errore: Impossibile trovare il lotto.")
                    except Exception as e:
                        logger.error(f"Transazione vendita fallita: {e}")
                        st.error(f"Transazione fallita: {e}")
        else:
            st.sidebar.info("Nessun titolo in portafoglio.")

# --- LOGICA DI VISUALIZZAZIONE DATI ---
totale_investito = 0
totale_attuale = 0
dividendi_annui_lordi = 0
dati_grafico_distribuzione = []

for membro, lotti in dati["portafoglio"].items():
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
plusvalenza_netta = plusvalenza_lorda * (1 - ALIQUOTE_TASSE["plusvalenza"]) if plusvalenza_lorda > 0 else plusvalenza_lorda
dividendi_annui_netti = dividendi_annui_lordi * (1 - ALIQUOTE_TASSE["dividendi"])

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
            fig_pie.update_traces(pull=[0.02]*len(df_dist), hovertemplate="<b>%{label}</b><br>Valore: %{customdata[0]}<extra></extra>", marker=dict(line=dict(color='#0E1117', width=2)))
            fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_pie, use_container_width=True)

    with col_chart2:
        st.subheader("Rapporto Rischio/Rendimento")
        df_bar = pd.DataFrame({"Categoria": ["Investito", "Valore Attuale"], "Importo (€)": [totale_investito, totale_attuale], "Testo": [f"{format_ita(totale_investito)} €", f"{format_ita(totale_attuale)} €"]})
        fig_bar = px.bar(df_bar, x="Categoria", y="Importo (€)", color="Categoria", text="Testo", color_discrete_sequence=['#64748B', '#10B981'])
        fig_bar.update_traces(width=0.3, textposition='outside', hovertemplate="<b>%{x}</b><br>%{text}<extra></extra>")
        fig_bar.update_layout(showlegend=False, height=600, margin=dict(t=30, b=30), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        fig_bar.update_yaxes(visible=False)
        st.plotly_chart(fig_bar, use_container_width=True)
    st.divider()

if st.session_state["ruolo"] == "admin":
    st.subheader("👥 Dettaglio per Componente della Famiglia")
    membri_da_mostrare = [m for m in ORDINE_FAMIGLIA if m in dati["portafoglio"]]
    tabs = st.tabs(membri_da_mostrare)
else:
    if st.session_state["utente"] in ["stefania", "claudia"]:
        st.markdown("### I Tuoi Titoli <span style='font-size: 16px; font-weight: 400; color: gray;'>[Nota: l'investimento iniziale è già al netto della Tobin Tax dello 0,20%]</span>", unsafe_allow_html=True)
    else:
        st.subheader("I Tuoi Titoli")
        
    membri_da_mostrare = [st.session_state["nome_portafoglio"]]
    tabs = [st.container()]

def colora_valori(val):
    if isinstance(val, str):
        if val.startswith('+'): return 'color: #10B981; font-weight: bold;'
        elif val.startswith('-'): return 'color: #EF4444; font-weight: bold;'
    return ''

for i, membro in enumerate(membri_da_mostrare):
    with tabs[i]:
        lotti = dati["portafoglio"].get(membro, [])
        if not lotti:
            st.info("Nessun titolo in portafoglio attualmente.")
            continue
            
        righe = []
        tot_azioni = tot_membro_inv = tot_membro_att = tot_plus_netta = tot_div_annuo = tot_div_trimestrale = 0
        
        for lotto in lotti:
            titolo = lotto["titolo"]
            q = lotto["quantita"]
            pc = lotto["prezzo_carico"]
            pa = dati["prezzi_attuali"].get(titolo, lotto["prezzo_carico"])
            
            inv = q * pc
            att = q * pa
            plus = att - inv
            plus_netta = plus * (1 - ALIQUOTE_TASSE["plusvalenza"]) if plus > 0 else plus
            div_annuo_netto = (q * dati["dividendi_annui"].get(titolo, 0)) * (1 - ALIQUOTE_TASSE["dividendi"])
            
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
                "Titolo": titolo, "Azioni": format_ita(q, 0), "Prezzo Carico (€)": format_ita(pc, 3),
                "Prezzo Mercato (€)": format_ita(pa, 2), "Investito (€)": format_ita(inv, 2),
                "Valore Attuale (€)": format_ita(att, 2), "Plus/Minus Netta (€)": f"{segno}{format_ita(plus_netta, 2)}",
                "Div. Annuo Netto": f"{format_ita(div_annuo_netto, 2)} €", "Div. Trimestrale Netto": str_trimestrale
            })
        
        segno_tot = "+" if tot_plus_netta > 0 else ""
        str_tot_trimestrale = f"{format_ita(tot_div_trimestrale, 2)} €" if tot_div_trimestrale > 0 else "-"
        
        righe.append({
            "Logo": "", "Titolo": "TOTALE", "Azioni": format_ita(tot_azioni, 0), "Prezzo Carico (€)": "-",
            "Prezzo Mercato (€)": "-", "Investito (€)": format_ita(tot_membro_inv, 2),
            "Valore Attuale (€)": format_ita(tot_membro_att, 2), "Plus/Minus Netta (€)": f"{segno_tot}{format_ita(tot_plus_netta, 2)}",
            "Div. Annuo Netto": f"{format_ita(tot_div_annuo, 2)} €", "Div. Trimestrale Netto": str_tot_trimestrale
        })
        
        df = pd.DataFrame(righe)
        styled_df = df.style.map(colora_valori, subset=['Plus/Minus Netta (€)'])
        st.dataframe(styled_df, use_container_width=True, hide_index=True, column_config={"Logo": st.column_config.ImageColumn("Logo", width="small")})
