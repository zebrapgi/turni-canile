from datetime import datetime, timedelta, time
import os
import json
import pandas as pd
import pytz
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

st.set_page_config(
    page_title="Gestione Turni Canile", page_icon="🐶", layout="wide"
)

# Tag aggiornati con versione forzata (?v=10) per aggirare la cache testarda di iOS
st.markdown(
    """
    <head>
        <link rel="manifest" href="manifest.json">
        <link rel="apple-touch-icon" href="https://github.com/lallag/turni-canile/blob/main/icona.jpg?raw=true&v=10">
    </head>
""",
    unsafe_allow_html=True,
)

# --- INIZIALIZZAZIONE FIREBASE FIRESTORE SICURA ---
if not firebase_admin._apps:
    try:
        firebase_json_str = st.secrets["FIREBASE_JSON"]
        cred_dict = json.loads(firebase_json_str)
        
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Errore di connessione a Firebase: {e}")
        st.stop()

db = firestore.client()

# --- FUNZIONI DI GESTIONE DATABASE FIRESTORE ---
def carica_da_firestore(collezione_nome, default_val):
    try:
        docs = list(db.collection(collezione_nome).stream())
        data = {doc.id: doc.to_dict() for doc in docs}
        
        if collezione_nome == "cani":
            if "lista" in data:
                return data["lista"].get("elementi", default_val)
            return default_val
        elif collezione_nome == "lpu_data":
            return data if data else default_val
        elif collezione_nome == "turni" or collezione_nome == "turni_lpu":
            lista = [doc.to_dict() for doc in docs]
            return lista if lista else default_val
        return default_val
    except Exception as e:
        st.error(f"Errore di caricamento: {e}")
        return default_val

def salva_su_firestore(collezione_nome, doc_id, data_dict):
    try:
        db.collection(collezione_nome).document(str(doc_id)).set(data_dict)
        return True
    except Exception as e:
        st.error(f"Errore di salvataggio su Firebase: {e}")
        return False

def elimina_da_firestore(collezione_nome, doc_id):
    try:
        db.collection(collezione_nome).document(str(doc_id)).delete()
        return True
    except Exception as e:
        st.error(f"Errore di eliminazione: {e}")
        return False

# Inizializzazione stato con Firebase
if "cani" not in st.session_state:
    cani_caricati = carica_da_firestore("cani", None)
    if cani_caricati and isinstance(cani_caricati, list):
        st.session_state.cani = cani_caricati
    else:
        default_cani = [
            "Marley", "Diego", "Lucky", "Macchia", "Sami", "Bonnie", "Giada", "Nelson", "Amber"
        ]
        st.session_state.cani = default_cani
        db.collection("cani").document("lista").set({"elementi": default_cani})

if "lpu_data" not in st.session_state:
    lpu_caricati = list(db.collection("lpu_data").stream())
    lpu_dict = {doc.id: doc.to_dict() for doc in lpu_caricati}
    st.session_state.lpu_data = lpu_dict if lpu_dict else {}

if "turni_lpu" not in st.session_state:
    turni_lpu_docs = list(db.collection("turni_lpu").stream())
    st.session_state.turni_lpu = [doc.to_dict() for doc in turni_lpu_docs]

if "turni" not in st.session_state:
    turni_docs = list(db.collection("turni").stream())
    st.session_state.turni = [doc.to_dict() for doc in turni_docs]

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# --- GESTIONE ORARIO ITALIANO ESATTO ---
tz_italia = pytz.timezone("Europe/Rome")
adesso = datetime.now(tz_italia)
giorno_settimana = adesso.weekday()
ora_attuale = adesso.hour

is_weekend_reale = (giorno_settimana > 4) or (
    giorno_settimana == 4 and ora_attuale >= 17
)
is_weekend_o_venerdi_sera = is_weekend_reale

# --- BARRA LATERALE (SIDEBAR) ---
with st.sidebar:
    if os.path.exists("icona.jpg"):
        st.image("icona.jpg", width=80)
    
    st.title("🐾 Menu Rapido")
    
    with st.expander("🔍 Cerca i miei turni", expanded=False):
        turni_esistenti_side = carica_da_firestore("turni", [])
        nomi_side = sorted(list(set(t.get("volontario", "").strip() for t in turni_esistenti_side if t.get("volontario"))))
        
        if not nomi_side:
            st.info("Nessun turno registrato nel sistema.")
        else:
            nome_cercato_side = st.selectbox("Seleziona il tuo nome:", nomi_side, key="selettore_miei_turni_sidebar")
            turni_pers_side = [t for t in turni_esistenti_side if t.get("volontario", "").strip().lower() == nome_cercato_side.lower()]
            
            if not turni_pers_side:
                st.write("Nessun turno trovato.")
            else:
                for tp in turni_pers_side:
                    cani_str = ", ".join(tp.get("cani_fatti", []))
                    if cani_str:
                        dettaglio_str = f"🐾 [{cani_str}]"
                    else:
                        dettaglio_str = "🧹 *Pulizie / LPU*"
                    st.markdown(f"• **{tp.get('settimana')}**<br>📅 {tp.get('giorno')} ({tp.get('fascia')})<br>⏰ {tp.get('orario')}<br>{dettaglio_str}", unsafe_allow_html=True)
                    st.markdown("---")

    st.markdown("---")

    with st.expander("🎛️ Filtra Panoramica", expanded=False):
        tutti_i_cani_presenti = sorted(list(st.session_state.cani))
        filtro_cane = st.selectbox("Filtra per cane:", ["Tutti i cani"] + tutti_i_cani_presenti, key="filtro_cane_side")
        
        turni_temp = carica_da_firestore("turni", [])
        tutti_i_volontari = sorted(list(set(t.get("volontario") for t in turni_temp if t.get("volontario"))))
        filtro_volontario = st.selectbox("Filtra per volontario:", ["Tutti i volontari"] + tutti_i_volontari, key="filtro_vol_side")

    st.markdown("---")

    with st.expander("🔒 Area Admin", expanded=False):
        ADMIN_PASSWORD_CORRETTA = st.secrets.get("ADMIN_PASSWORD", "canile2026")
        if not st.session_state.is_admin:
            with st.form("form_login_admin_side"):
                pwd_input = st.text_input("Password:", type="password", key="pwd_side")
                btn_login = st.form_submit_button("Sblocca")
                if btn_login:
                    if pwd_input == ADMIN_PASSWORD_CORRETTA:
                        st.session_state.is_admin = True
                        st.success("Sbloccato!")
                        st.rerun()
                    else:
                        st.error("Errata.")
        else:
            st.success("🔓 Admin attivo")
            scelta_simulazione = st.selectbox(
                "Simulazione:",
                [
                    "📅 Automatico",
                    "⚠️ Simula Weekend",
                    "🟢 Simula Feriale",
                ],
                key="selettore_simulazione_side",
            )

            if scelta_simulazione == "⚠️ Simula Weekend":
                is_weekend_o_venerdi_sera = True
            elif scelta_simulazione == "🟢 Simula Feriale":
                is_weekend_o_venerdi_sera = False
            else:
                is_weekend_o_venerdi_sera = is_weekend_reale

            if st.button("🔒 Esci Admin", key="esci_admin_side"):
                st.session_state.is_admin = False
                st.rerun()

# --- FUNZIONE INTERVALLI SETTIMANE ---
def get_intervalli_settimane():
    oggi = datetime.now(tz_italia)
    lunedi_corrente = oggi - timedelta(days=oggi.weekday())
    domenica_corrente = lunedi_corrente + timedelta(days=6)

    lunedi_prossimo = lunedi_corrente + timedelta(days=7)
    domenica_prossima = domenica_corrente + timedelta(days=7)

    fmt = "%d/%m/%Y"
    str_corr = f"Settimana Corrente ({lunedi_corrente.strftime(fmt)} - {domenica_corrente.strftime(fmt)})"
    str_pros = f"Prossima Settimana ({lunedi_prossimo.strftime(fmt)} - {domenica_prossima.strftime(fmt)})"

    return str_corr, str_pros

label_corr, label_pros = get_intervalli_settimane()

# --- INTESTAZIONE PRINCIPALE ---
st.title("🐾 Turni Canile")

with st.container():
    turni_notifiche = carica_da_firestore("turni", [])
    
    giorni_map_ita = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    giorno_oggi_str = giorni_map_ita[adesso.weekday()]
    
    turni_oggi = [
        t for t in turni_notifiche 
        if t.get("giorno") == giorno_oggi_str and t.get("settimana") == label_corr
    ]
    
    cani_coperti_oggi = set()
    for t in turni_oggi:
        for c in t.get("cani_fatti", []):
            cani_coperti_oggi.add(c)
            
    cani_scoperti_oggi = [c for c in st.session_state.cani if c not in cani_coperti_oggi]

    if len(turni_oggi) > 0 and cani_scoperti_oggi:
        with st.expander("🔔 Avvisi Canile del Giorno", expanded=True):
            st.warning(f"⚠️ **Attenzione ({giorno_oggi_str}):** Ci sono cani senza volontari assegnati oggi: `{', '.join(cani_scoperti_oggi)}`")

# --- MENU PRINCIPALE IN ALTO ---
opzioni_base = [
    "📅 Inserisci",
    "👀 Panoramica",
    "🐶 Cani",
    "📊 Statistiche",
    "📚 Archivio",
]

if st.session_state.is_admin:
    opzioni_menu = opzioni_base + ["🛠️ Gestione LPU (Admin)"]
else:
    opzioni_menu = opzioni_base

menu = st.pills("Seleziona sezione:", opzioni_menu, default=opzioni_menu[0])
st.markdown("---")

if is_weekend_o_venerdi_sera:
    st.warning(
        "⚠️ **Promemoria Canile:** È iniziato il fine settimana! Ricordati di"
        " selezionare la **'Prossima Settimana'** qui sotto per inserire i tuoi"
        " turni per la settimana che sta per arrivare."
    )

def get_lista_volontari():
    turni_esistenti = carica_da_firestore("turni", [])
    nomi = set()
    for t in turni_esistenti:
        nome = t.get("volontario", "").strip()
        if nome:
            nomi.add(nome)
    return sorted(list(nomi))

def get_cani_frequenti_volontario(nome_volontario):
    if not nome_volontario or nome_volontario == "➕ Altro / Nuovo volontario" or nome_volontario == "-- Seleziona il tuo nome --":
        return []
    
    turni_esistenti = carica_da_firestore("turni", [])
    conteggio_cani = {}
    
    for t in turni_esistenti:
        if t.get("volontario", "").strip().lower() == nome_volontario.strip().lower():
            for c in t.get("cani_fatti", []):
                if c in st.session_state.cani:
                    conteggio_cani[c] = conteggio_cani.get(c, 0) + 1
                    
    cani_ordinati = sorted(conteggio_cani.items(), key=lambda x: x[1], reverse=True)
    return [c[0] for c in cani_ordinati if c[1] >= 1]

if menu == "📅 Inserisci":
    st.header("Gestione Turni")

    if is_weekend_o_venerdi_sera:
        opzioni_settimana = [label_corr, label_pros]
    else:
        opzioni_settimana = [label_corr]

    settimana_scelta = st.radio(
        "Per quale settimana vuoi inserire il turno?",
        opzioni_settimana,
        horizontal=True,
    )

    volontari_registrati = get_lista_volontari()

    st.markdown("### 👤 1. Il tuo Nome")
    scelte_volontario = ["-- Seleziona il tuo nome --"] + volontari_registrati + ["➕ Altro / Nuovo volontario"]
    
    scelta_volontario_dropdown = st.selectbox("Seleziona o inserisci il tuo Nome e Cognome:", scelte_volontario, key="selettore_nome_principale")
    
    volontario_finale = ""
    if scelta_volontario_dropdown == "➕ Altro / Nuovo volontario":
        volontario_nuovo_input = st.text_input("Scrivi qui il tuo Nome e Cognome:", key="input_nuovo_volontario_libero")
        volontario_finale = volontario_nuovo_input.strip()
    elif scelta_volontario_dropdown != "-- Seleziona il tuo nome --":
        volontario_finale = scelta_volontario_dropdown

    st.markdown("---")

    with st.form("form_turno"):
        st.markdown("### 🕒 2. Dettagli Turno e Cani")
        col1, col2 = st.columns(2)

        with col1:
            giorno = st.selectbox(
                "Giorno della settimana:",
                [
                    "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica",
                ],
            )
            fascia = st.selectbox("Fascia oraria:", ["Mattina", "Pomeriggio"], key="selettore_fascia_form")

        with col2:
            st.markdown(f"**Orario per {fascia}:**")
            
            if fascia == "Mattina":
                default_inizio = time(8, 30)
                default_fine = time(12, 0)
            else:
                default_inizio = time(14, 30)
                default_fine = time(18, 0)

            col_ora1, col_ora2 = st.columns(2)
            with col_ora1:
                ora_inizio = st.time_input("Da:", value=default_inizio, key=f"ora_inizio_{fascia.lower()}")
            
            senza_fine = st.checkbox("Senza orario di fine (da quest'ora in poi)")

            with col_ora2:
                if not senza_fine:
                    ora_fine = st.time_input("A:", value=default_fine, key=f"ora_fine_{fascia.lower()}")
                else:
                    st.markdown("<br><i>Nessun limite</i>", unsafe_allow_html=True)
            
            if senza_fine:
                orario = f"Dalle {ora_inizio.strftime('%H:%M')}"
            else:
                orario = f"{ora_inizio.strftime('%H:%M')} - {ora_fine.strftime('%H:%M')}"

            note = st.text_area("Note aggiuntive (opzionale):")

        cani_suggeriti = get_cani_frequenti_volontario(volontario_finale)

        col_cani_op1, col_cani_op2 = st.columns([1, 1])
        with col_cani_op1:
            seleziona_tutti = st.checkbox("🐾 Seleziona TUTTI i cani")
        with col_cani_op2:
            if cani_suggeriti:
                st.caption(f"💡 Suggerimento abitudini: {', '.join(cani_suggeriti)}")

        if seleziona_tutti:
            cani_fatti = st.multiselect(
                "✅ Cani che sei autorizzato a gestire (obbligatorio selezionarne almeno uno):",
                st.session_state.cani,
                default=st.session_state.cani,
            )
        elif cani_suggeriti:
            cani_fatti = st.multiselect(
                "✅ Cani che sei autorizzato a gestire (obbligatorio selezionarne almeno uno):",
                st.session_state.cani,
                default=cani_suggeriti
            )
        else:
            cani_fatti = st.multiselect(
                "✅ Cani che sei autorizzato a gestire (obbligatorio selezionarne almeno uno):", 
                st.session_state.cani
            )

        submit_button = st.form_submit_button(label="Registra Turno 🚀")

        if submit_button:
            ora_limite_divisione = time(14, 0)
            errore_fascia = False
            
            if fascia == "Mattina" and ora_inizio >= ora_limite_divisione:
                st.error("❌ **Errore:** Hai scelto la fascia **Mattina**, ma l'orario di inizio è pomeridiano (dalle 14:00 in poi).")
                errore_fascia = True
            elif fascia == "Pomeriggio" and ora_inizio < ora_limite_divisione:
                st.error("❌ **Errore:** Hai scelto la fascia **Pomeriggio**, ma l'orario di inizio è mattutino (prima delle 14:00).")
                errore_fascia = True

            if not errore_fascia:
                if not volontario_finale:
                    st.warning("⚠️ Per favore, seleziona il tuo nome dal menu a tendina o scrivi il tuo nome e cognome nell'apposita casella in alto prima di registrare.")
                elif not cani_fatti:
                    st.error("❌ **Errore:** Devi selezionare almeno un cane per poter registrare il turno!")
                else:
                    lista_turni = carica_da_firestore("turni", [])
                    
                    volontario_normalizzato = volontario_finale.strip().lower()
                    doppione_trovato = any(
                        t.get("volontario", "").strip().lower() == volontario_normalizzato and
                        t.get("settimana") == settimana_scelta and
                        t.get("giorno") == giorno and
                        t.get("fascia") == fascia
                        for t in lista_turni
                    )

                    if doppione_trovato:
                        st.error(f"⚠️ **Attenzione:** {volontario_finale} risulta già registrato per {giorno} ({fascia}) in questa settimana!")
                    else:
                        id_turno = str(datetime.now().timestamp())
                        nuovo_turno = {
                            "id": id_turno,
                            "settimana": settimana_scelta,
                            "volontario": volontario_finale,
                            "giorno": giorno,
                            "fascia": fascia,
                            "orario": orario,
                            "cani_fatti": cani_fatti,
                            "note": note,
                        }
                        try:
                            db.collection("turni").document(id_turno).set(nuovo_turno)
                            st.toast(f"Turno registrato con successo per {volontario_finale}!", icon="🎉")
                            st.rerun()
                        except Exception as e:
                            st.error(f"ERRORE DI SCRITTURA FIREBASE: {e}")

elif menu == "👀 Panoramica":
    st.header("Gestione Turni e Copertura")

    turni_attuali = carica_da_firestore("turni", [])

    if is_weekend_o_venerdi_sera:
        scelte_visualizzazione = [label_corr, label_pros]
    else:
        scelte_visualizzazione = [label_corr]

    settimana_vista = st.radio(
        "Seleziona la settimana da visualizzare:",
        scelte_visualizzazione,
        horizontal=True,
    )

    turni_filtrati = [
        t for t in turni_attuali if t.get("settimana") == settimana_vista
    ]

    if st.session_state.get("filtro_cane_side", "Tutti i cani") != "Tutti i cani":
        cane_scelto = st.session_state["filtro_cane_side"]
        turni_filtrati = [t for t in turni_filtrati if cane_scelto in t.get("cani_fatti", [])]
        st.info(f"🔍 Filtro attivo nella sidebar per il cane: **{cane_scelto}**")

    if st.session_state.get("filtro_vol_side", "Tutti i volontari") != "Tutti i volontari":
        vol_scelto = st.session_state["filtro_vol_side"]
        turni_filtrati = [t for t in turni_filtrati if t.get("volontario") == vol_scelto]
        st.info(f"🔍 Filtro attivo nella sidebar per il volontario: **{vol_scelto}**")

    if not turni_filtrati:
        st.info("Nessun turno trovato con i filtri selezionati per questo periodo.")
    else:
        giorni_settimana = [
            "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica",
        ]

        for giorno in giorni_settimana:
            turni_giorno = [t for t in turni_filtrati if t["giorno"] == giorno]
            if not turni_giorno and (st.session_state.get("filtro_cane_side", "Tutti i cani") != "Tutti i cani" or st.session_state.get("filtro_vol_side", "Tutti i volontari") != "Tutti i volontari"):
                continue
                
            st.markdown(f"## 📌 {giorno}")

            col_m, col_p = st.columns(2)

            def mostra_fascia_calendario(fascia_nome, col_container):
                with col_container:
                    with st.container(border=True):
                        icona_fascia = "🌅" if fascia_nome == "Mattina" else "🌇"
                        st.markdown(f"### {icona_fascia} {fascia_nome}")
                        
                        turni_fascia = [
                            t for t in turni_giorno if t["fascia"] == fascia_nome
                        ]

                        if not turni_fascia:
                            st.caption("Nessun volontario registrato.")
                            st.markdown("**Cani scoperti:**")
                            for c in sorted(st.session_state.cani):
                                st.error(f"❌ {c}")
                        else:
                            st.markdown("**Volontari presenti:**")
                            for t in turni_fascia:
                                cani_str = ", ".join(t["cani_fatti"]) if t.get("cani_fatti") else ""
                                if cani_str:
                                    dettaglio_mostra = f"🐾 [{cani_str}]"
                                else:
                                    dettaglio_mostra = "🧹 *Pulizie / LPU*"

                                st.write(
                                    f"• **{t['volontario']}** ({t['orario']}) {dettaglio_mostra}"
                                )
                                if t["note"]:
                                    st.caption(f"Note: {t['note']}")

                                if st.session_state.is_admin:
                                    col_mod, col_del = st.columns(2)
                                    with col_mod:
                                        if not t['id'].startswith("lpu_"):
                                            if st.button(
                                                f"✏️ Modifica ({t['volontario']})",
                                                key=f"mod_btn_{giorno}_{fascia_nome}_{t['id']}",
                                            ):
                                                st.session_state[f"editing_{t['id']}"] = not st.session_state.get(f"editing_{t['id']}", False)
                                                st.rerun()
                                        else:
                                            st.caption("*(Modifica LPU nella tab dedicata)*")
                                    
                                    with col_del:
                                        with st.popover(f"🗑️ Elimina ({t['volontario']})"):
                                            st.write("Sei sicuro di voler eliminare questo turno?")
                                            if st.button("Conferma Eliminazione 🛑", key=f"conf_del_{t['id']}"):
                                                if t['id'].startswith("lpu_"):
                                                    original_lpu_id = t['id'].replace("lpu_", "")
                                                    tutti_lpu = carica_da_firestore("turni_lpu", [])
                                                    lpu_trovato = next((item for item in tutti_lpu if item.get("id") == original_lpu_id), None)
                                                    
                                                    if lpu_trovato:
                                                        nome_lp = lpu_trovato.get("lpu")
                                                        ore_storno = lpu_trovato.get("ore", 0.0)
                                                        if nome_lp in st.session_state.lpu_data:
                                                            st.session_state.lpu_data[nome_lp]["ore_fatte"] = max(
                                                                0.0, st.session_state.lpu_data[nome_lp]["ore_fatte"] - ore_storno
                                                            )
                                                            salva_su_firestore("lpu_data", nome_lp, st.session_state.lpu_data[nome_lp])
                                                        
                                                        elimina_da_firestore("turni_lpu", original_lpu_id)

                                                elimina_da_firestore("turni", t['id'])
                                                if f"editing_{t['id']}" in st.session_state:
                                                    del st.session_state[f"editing_{t['id']}"]
                                                st.success("Turno eliminato!")
                                                st.rerun()

                                    if not t['id'].startswith("lpu_") and st.session_state.get(f"editing_{t['id']}", False):
                                        with st.form(key=f"form_mod_{t['id']}"):
                                            st.subheader(f"Modifica Turno di {t['volontario']}")
                                            
                                            col_m1, col_m2 = st.columns(2)
                                            with col_m1:
                                                m_inizio = st.time_input("Ora Inizio:", value=time(8, 30), key=f"min_{t['id']}")
                                            with col_m2:
                                                m_fine = st.time_input("Ora Fine:", value=time(12, 0), key=f"mfin_{t['id']}")
                                            
                                            nuovo_orario = f"{m_inizio.strftime('%H:%M')} - {m_fine.strftime('%H:%M')}"
                                            nuove_note = st.text_area("Note:", value=t.get("note", ""), key=f"note_mod_{t['id']}")
                                            
                                            nuovi_cani = st.multiselect(
                                                "Cani gestiti:",
                                                st.session_state.cani,
                                                default=[c for c in t.get("cani_fatti", []) if c in st.session_state.cani],
                                                key=f"cani_mod_{t['id']}"
                                            )
                                            btn_salva_mod = st.form_submit_button("Salva Modifiche ✅")
                                            if btn_salva_mod:
                                                if not nuovi_cani:
                                                    st.error("Errore: seleziona almeno un cane.")
                                                else:
                                                    t_aggiornato = {
                                                        "id": t["id"],
                                                        "settimana": t["settimana"],
                                                        "volontario": t["volontario"],
                                                        "giorno": t["giorno"],
                                                        "fascia": t["fascia"],
                                                        "orario": nuovo_orario,
                                                        "cani_fatti": nuovi_cani,
                                                        "note": nuove_note
                                                    }
                                                    salva_su_firestore("turni", t["id"], t_aggiornato)
                                                    st.session_state[f"editing_{t['id']}"] = False
                                                    st.success("Turno modificato con successo!")
                                                    st.rerun()

                            st.markdown("---")
                            st.markdown("**Cani scoperti:**")
                            cani_coperti = set()
                            for t in turni_fascia:
                                for c in t.get("cani_fatti", []):
                                    cani_coperti.add(c)

                            cani_scoperti = [
                                c for c in st.session_state.cani if c not in cani_coperti
                            ]

                            if cani_scoperti:
                                for c in sorted(cani_scoperti):
                                    st.error(f"❌ {c}")
                            else:
                                st.success("Tutti i cani sono coperti!")

            with col_m:
                mostra_fascia_calendario("Mattina", col_m)
            with col_p:
                mostra_fascia_calendario("Pomeriggio", col_p)

            st.markdown("---")

elif menu == "🐶 Cani":
    st.header("Gestione Anagrafica Cani")

    if not st.session_state.is_admin:
        st.warning(
            "🔒 Questa sezione è protetta. Apri l'area 'Admin' nella barra"
            " laterale a sinistra per inserire la password."
        )
        st.subheader("Lista attuale dei cani in canile:")
        for dog in st.session_state.cani:
            st.write(f"🐾 **{dog}**")
    else:
        st.markdown("Aggiungi o rimuovi i cani presenti in canile (Modalità Admin attiva).")

        new_dog = st.text_input("Nome del nuovo cane:")
        if st.button("Aggiungi Cane"):
            if new_dog.strip() and new_dog not in st.session_state.cani:
                st.session_state.cani.append(new_dog.strip())
                db.collection("cani").document("lista").set({"elementi": st.session_state.cani})
                st.success(f"Cane '{new_dog}' aggiunto con successo!")
                st.rerun()
            elif new_dog in st.session_state.cani:
                st.warning("Questo cane è già presente nella lista.")

        st.subheader("Lista attuale dei cani in canile:")
        for dog in st.session_state.cani:
            col_d1, col_d2 = st.columns([4, 1])
            with col_d1:
                st.write(f"🐾 **{dog}**")
            with col_d2:
                with st.popover("Elimina"):
                    st.write(f"Confermi l'eliminazione di {dog}?")
                    if st.button("Sì, elimina", key=f"conf_del_dog_{dog}"):
                        st.session_state.cani.remove(dog)
                        db.collection("cani").document("lista").set({"elementi": st.session_state.cani})
                        st.success(f"Cane '{dog}' eliminato.")
                        st.rerun()

elif menu == "📊 Statistiche":
    st.header("📊 Statistiche Uscite Cani")
    
    tutti_i_turni = carica_da_firestore("turni", [])
    tutte_le_settimane = sorted(
        list(set(t.get("settimana") for t in tutti_i_turni))
    )

    if label_corr not in tutte_le_settimane:
        tutte_le_settimane.insert(0, label_corr)
    if label_pros not in tutte_le_settimane and is_weekend_o_venerdi_sera:
        tutte_le_settimane.append(label_pros)

    settimana_stat = st.selectbox(
        "Seleziona settimana da analizzare:", tutte_le_settimane
    )

    turni_stat = [
        t for t in tutti_i_turni if t.get("settimana") == settimana_stat
    ]

    uscite_per_cane = {cane: 0 for cane in st.session_state.cani}
    giorni_settimana = [
        "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"
    ]

    for giorno in giorni_settimana:
        for fascia in ["Mattina", "Pomeriggio"]:
            turni_fascia = [
                t for t in turni_stat
                if t.get("giorno") == giorno and t.get("fascia") == fascia
            ]
            cani_in_questa_fascia = set()
            for t in turni_fascia:
                for c in t.get("cani_fatti", []):
                    cani_in_questa_fascia.add(c)

            for c in cani_in_questa_fascia:
                if c in uscite_per_cane:
                    uscite_per_cane[c] += 1

    if not st.session_state.cani:
        st.info("Nessun cane registrato nel sistema.")
    else:
        st.markdown("---")
        st.subheader("🎯 Riepilogo Uscite")
        cols = st.columns(3)

        lista_cani_ordinata = sorted(
            uscite_per_cane.items(), key=lambda x: x[1], reverse=True
        )

        for idx, (cane, conteggio) in enumerate(lista_cani_ordinata):
            col_corrente = cols[idx % 3]
            with col_corrente:
                st.metric(label=f"🐾 {cane}", value=f"{conteggio} uscite")

        st.markdown("---")
        col_grafico, col_tabella = st.columns([1.5, 1])

        with col_grafico:
            st.subheader("📈 Grafico a Barre")
            if sum(uscite_per_cane.values()) == 0:
                st.info("Nessuna uscita registrata per i cani in questa settimana.")
            else:
                df_stat = pd.DataFrame(
                    list(uscite_per_cane.items()),
                    columns=["Cane", "Numero Uscite"],
                ).set_index("Cane")
                st.bar_chart(df_stat)

        with col_tabella:
            st.subheader("📋 Tabella Dati")
            df_tabella = pd.DataFrame(
                list(uscite_per_cane.items()), columns=["Cane", "Uscite"]
            ).sort_values(by="Uscite", ascending=False).reset_index(drop=True)
            st.dataframe(df_tabella, use_container_width=True)

elif menu == "📚 Archivio":
    st.header("📚 Archivio Storico delle Settimane Passate")
    
    tutti_i_turni = carica_da_firestore("turni", [])
    tutte_le_settimane = sorted(
        list(set(t.get("settimana") for t in tutti_i_turni))
    )
    settimane_storiche = sorted(
        [s for s in tutte_le_settimane if s != label_corr and s != label_pros],
        reverse=True
    )

    settimane_disponibili = (
        settimane_storiche if settimane_storiche else tutte_le_settimane
    )

    if not settimane_disponibili:
        st.info("Nessun dato presente nell'archivio storico.")
    else:
        storico_scelto = st.selectbox(
            "Seleziona la settimana dall'archivio:", settimane_disponibili
        )

        turni_storico = [
            t for t in tutti_i_turni if t.get("settimana") == storico_scelto
        ]

        giorni_settimana = [
            "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"
        ]

        for giorno in giorni_settimana:
            st.markdown(f"## 📌 {giorno}")
            turni_giorno = [t for t in turni_storico if t["giorno"] == giorno]
            col_m, col_p = st.columns(2)

            def mostra_fascia_storica(fascia_nome, col_container):
                with col_container:
                    with st.container(border=True):
                        st.markdown(f"### ☀️ {fascia_nome}")
                        turni_fascia = [
                            t for t in turni_giorno if t["fascia"] == fascia_nome
                        ]

                        if not turni_fascia:
                            st.caption("Nessun volontario registrato in questa fascia.")
                        else:
                            st.markdown("**Volontari presenti:**")
                            for t in turni_fascia:
                                cani_str = ", ".join(t["cani_fatti"]) if t.get("cani_fatti") else "🧹 Pulizie / LPU"
                                st.write(
                                    f"• **{t['volontario']}** ({t['orario']}) - {cani_str}"
                                )
                                if t["note"]:
                                    st.caption(f"Note: {t['note']}")

            with col_m:
                mostra_fascia_storica("Mattina", col_m)
            with col_p:
                mostra_fascia_storica("Pomeriggio", col_p)

            st.markdown("---")

elif menu == "🛠️ Gestione LPU (Admin)":
    st.header("🛠️ Gestione Lavori Socialmente Utili (LPU)")

    if not st.session_state.is_admin:
        st.error("Area riservata esclusivamente agli amministratori.")
    else:
        st.markdown(
            "Gestisci il personale LPU, inserisci e modifica i turni con"
            " relative ore e monitora il monte ore totale e mancante."
        )

        tab_lpu_anagrafica, tab_lpu_inserisci, tab_lpu_storico = st.tabs(
            [
                "📋 Monte Ore & Ore Mancanti",
                "➕ Assegna Turno LPU",
                "📚 Storico & Modifica Turni LPU",
            ]
        )

        with tab_lpu_anagrafica:
            st.subheader("➕ Aggiungi o Configura un LPU")
            with st.form("form_aggiungi_lpu"):
                nome_lpu = st.text_input("Nome e Cognome LPU:")
                ore_totali_obbligatorie = st.number_input(
                    "Monte ore totale richiesto:",
                    min_value=1.0,
                    value=50.0,
                    step=1.0,
                )

                btn_salva_lpu = st.form_submit_button("Crea / Salva LPU 📝")
                if btn_salva_lpu:
                    if not nome_lpu.strip():
                        st.error("Inserisci un nome valido.")
                    else:
                        nome_pulito = nome_lpu.strip()
                        if nome_pulito not in st.session_state.lpu_data:
                            st.session_state.lpu_data[nome_pulito] = {
                                "ore_totali": float(ore_totali_obbligatorie),
                                "ore_fatte": 0.0,
                            }
                        else:
                            st.session_state.lpu_data[nome_pulito][
                                "ore_totali"
                            ] = float(ore_totali_obbligatorie)

                        salva_su_firestore("lpu_data", nome_pulito, st.session_state.lpu_data[nome_pulito])
                        st.success(f"LPU '{nome_lpu}' salvato con successo!")
                        st.rerun()

            st.markdown("---")
            st.subheader("📋 Monitoraggio Ore LPU (Fatte e Mancanti)")

            lpu_dict = st.session_state.lpu_data
            if not lpu_dict:
                st.info("Nessun LPU registrato nel sistema.")
            else:
                dati_tabella_lpu = []
                for nome, info in lpu_dict.items():
                    tot = info.get("ore_totali", 0.0)
                    fatte = info.get("ore_fatte", 0.0)
                    mancanti = max(0.0, tot - fatte)

                    dati_tabella_lpu.append(
                        {
                            "Nome LPU": nome,
                            "Ore Totali": tot,
                            "Ore Fatte": fatte,
                            "Ore Mancanti": mancanti,
                        }
                    )

                df_lpu = pd.DataFrame(dati_tabella_lpu)
                st.dataframe(df_lpu, use_container_width=True)

                st.markdown("### 🗑️ Gestione LPU")
                for nome in list(lpu_dict.keys()):
                    col_del_lpu, col_btn_lpu = st.columns([3, 1])
                    with col_del_lpu:
                        st.write(
                            f"• **{nome}** (Fatte:"
                            f" {lpu_dict[nome]['ore_fatte']}h / Totali:"
                            f" {lpu_dict[nome]['ore_totali']}h)"
                        )
                    with col_btn_lpu:
                        if st.button("Elimina 🗑️", key=f"btn_del_lpu_{nome}"):
                            del lpu_dict[nome]
                            elimina_da_firestore("lpu_data", nome)
                            st.success("LPU rimosso.")
                            st.rerun()

        with tab_lpu_inserisci:
            st.subheader("📅 Registra un Turno per LPU")
            lpu_nomi_disponibili = list(st.session_state.lpu_data.keys())

            if not lpu_nomi_disponibili:
                st.warning(
                    "Prima devi registrare almeno un LPU nella scheda 'Monte"
                    " Ore & Ore Mancanti'."
                )
            else:
                with st.form("form_turno_lpu"):
                    lpu_scelto = st.selectbox(
                        "Seleziona LPU:", lpu_nomi_disponibili
                    )
                    settimana_lpu = st.selectbox(
                        "Settimana:", [label_corr, label_pros]
                    )
                    giorno_lpu = st.selectbox(
                        "Giorno:",
                        [
                            "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica",
                        ],
                        key="g_lpu",
                    )
                    fascia_lpu = st.selectbox(
                        "Fascia:", ["Mattina", "Pomeriggio"], key="f_lpu"
                    )

                    col_ol1, col_ol2 = st.columns(2)
                    with col_ol1:
                        ora_i_lpu = st.time_input(
                            "Ora Inizio:", value=time(8, 30), key="oi_lpu"
                        )
                    with col_ol2:
                        ora_f_lpu = st.time_input(
                            "Ora Fine:", value=time(12, 0), key="of_lpu"
                        )

                    orario_lpu_str = (
                        f"{ora_i_lpu.strftime('%H:%M')} -"
                        f" {ora_f_lpu.strftime('%H:%M')}"
                    )
                    ore_svolte_val = st.number_input(
                        "Quante ore di lavoro aggiungere al monte ore?",
                        min_value=0.5,
                        value=3.5,
                        step=0.5,
                    )

                    nota_lpu = st.text_area("Note / Attività di pulizia:", value="Pulizie generali struttura", key="note_lpu_in")

                    btn_registra_turno_lpu = st.form_submit_button(
                        "Assegna Turno e Aggiorna Ore 🚀"
                    )
                    if btn_registra_turno_lpu:
                        id_univoco = str(datetime.now().timestamp())
                        nuovo_t_lpu = {
                            "id": id_univoco,
                            "lpu": lpu_scelto,
                            "settimana": settimana_lpu,
                            "giorno": giorno_lpu,
                            "fascia": fascia_lpu,
                            "orario": orario_lpu_str,
                            "ore": float(ore_svolte_val),
                            "note": nota_lpu,
                        }
                        st.session_state.turni_lpu.append(nuovo_t_lpu)
                        salva_su_firestore("turni_lpu", id_univoco, nuovo_t_lpu)

                        st.session_state.lpu_data[lpu_scelto][
                            "ore_fatte"
                        ] += float(ore_svolte_val)
                        salva_su_firestore("lpu_data", lpu_scelto, st.session_state.lpu_data[lpu_scelto])

                        turno_generale_equivalente = {
                            "id": f"lpu_{id_univoco}",
                            "settimana": settimana_lpu,
                            "volontario": f"{lpu_scelto} (LPU)",
                            "giorno": giorno_lpu,
                            "fascia": fascia_lpu,
                            "orario": orario_lpu_str,
                            "cani_fatti": [],
                            "note": (
                                f"[LPU - Pulizie / {ore_svolte_val}h] {nota_lpu}"
                            ),
                        }
                        salva_su_firestore("turni", f"lpu_{id_univoco}", turno_generale_equivalente)

                        st.success(
                            f"Turno registrato per {lpu_scelto}! Aggiunte"
                            f" {ore_svolte_val} ore."
                        )
                        st.rerun()

        with tab_lpu_storico:
            st.subheader("📚 Storico, Modifica ed Eliminazione Turni LPU")
            tutti_turni_lpu = carica_da_firestore("turni_lpu", [])

            if not tutti_turni_lpu:
                st.info("Nessun turno LPU registrato.")
            else:
                for tl in reversed(tutti_turni_lpu):
                    st.markdown(
                        f"• **{tl.get('lpu')}** - {tl.get('settimana')} | 📅"
                        f" {tl.get('giorno')} ({tl.get('fascia')} -"
                        f" {tl.get('orario')}) | ⏱️ **{tl.get('ore')} ore** | 🧹 *Pulizie struttura*"
                    )
                    if tl.get("note"):
                        st.caption(f"Note: {tl.get('note')}")

                    col_m_lpu, col_d_lpu = st.columns(2)
                    with col_m_lpu:
                        if st.button(
                            "✏️ Modifica Ore/Dettagli",
                            key=f"edit_lpu_btn_{tl['id']}",
                        ):
                            st.session_state[f"editing_lpu_{tl['id']}"] = (
                                not st.session_state.get(
                                    f"editing_lpu_{tl['id']}", False
                                )
                            )
                            st.rerun()
                    with col_d_lpu:
                        if st.button(
                            "🗑️ Elimina Turno LPU", key=f"del_lpu_turno_{tl['id']}"
                        ):
                            nome_lpu_riferimento = tl.get("lpu")
                            ore_da_stornare = tl.get("ore", 0.0)

                            if nome_lpu_riferimento in st.session_state.lpu_data:
                                st.session_state.lpu_data[
                                    nome_lpu_riferimento
                                    ]["ore_fatte"] = max(
                                    0.0,
                                    st.session_state.lpu_data[
                                        nome_lpu_riferimento
                                    ]["ore_fatte"]
                                    - ore_da_stornare,
                                )
                                salva_su_firestore(
                                    "lpu_data", nome_lpu_riferimento, st.session_state.lpu_data[nome_lpu_riferimento]
                                )

                            elimina_da_firestore("turni_lpu", tl['id'])
                            elimina_da_firestore("turni", f"lpu_{tl['id']}")

                            st.success(
                                "Turno LPU eliminato, ore stornate e rimosso dalla panoramica con successo!"
                            )
                            st.rerun()

                    if st.session_state.get(f"editing_lpu_{tl['id']}", False):
                        with st.form(key=f"form_mod_lpu_turno_{tl['id']}"):
                            st.subheader(f"Modifica Turno di {tl.get('lpu')}")
                            nuove_ore_val = st.number_input(
                                "Nuovo monte ore:",
                                min_value=0.5,
                                value=float(tl.get("ore", 3.5)),
                                step=0.5,
                                key=f"n_ore_{tl['id']}",
                            )
                            nuove_note_val = st.text_area(
                                "Note:",
                                value=tl.get("note", ""),
                                key=f"n_note_{tl['id']}",
                            )

                            btn_salva_mod_lpu = st.form_submit_button(
                                "Salva Modifiche LPU ✅"
                            )
                            if btn_salva_mod_lpu:
                                vecchie_ore = tl.get("ore", 0.0)
                                differenza_ore = nuove_ore_val - vecchie_ore

                                tl_aggiornato = {
                                    "id": tl["id"],
                                    "lpu": tl["lpu"],
                                    "settimana": tl["settimana"],
                                    "giorno": tl["giorno"],
                                    "fascia": tl["fascia"],
                                    "orario": tl["orario"],
                                    "ore": float(nuove_ore_val),
                                    "note": nuove_note_val
                                }
                                salva_su_firestore("turni_lpu", tl["id"], tl_aggiornato)

                                nome_lpu_riferimento = tl.get("lpu")
                                if (
                                    nome_lpu_riferimento
                                    in st.session_state.lpu_data
                                ):
                                    st.session_state.lpu_data[
                                        nome_lpu_riferimento
                                    ]["ore_fatte"] = max(
                                        0.0,
                                        st.session_state.lpu_data[
                                            nome_lpu_riferimento
                                        ]["ore_fatte"]
                                        + differenza_ore,
                                    )
                                    salva_su_firestore(
                                        "lpu_data", nome_lpu_riferimento, st.session_state.lpu_data[nome_lpu_riferimento]
                                    )

                                turno_gen_esistente = db.collection("turni").document(f"lpu_{tl['id']}").get().to_dict()
                                if turno_gen_esistente:
                                    turno_gen_esistente["note"] = f"[LPU - Pulizie / {nuove_ore_val}h] {nuove_note_val}"
                                    salva_su_firestore("turni", f"lpu_{tl['id']}", turno_gen_esistente)

                                st.session_state[
                                    f"editing_lpu_{tl['id']}"
                                ] = False
                                st.success(
                                    "Turno LPU modificato con successo!"
                                )
                                st.rerun()

                    st.markdown("---")
