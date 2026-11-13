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

# --- CONFIGURAZIONI GLOBALI ---
GIORNI_SETTIMANA = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
FASCE_ORARIE = ["Mattina", "Pomeriggio"]

# --- INIZIALIZZAZIONE FIREBASE ---
if not firebase_admin._apps:
    try:
        raw_secrets = st.secrets["FIREBASE_JSON"]
        cred_dict = {
            "type": raw_secrets["type"],
            "project_id": raw_secrets["project_id"],
            "private_key_id": raw_secrets["private_key_id"],
            "private_key": raw_secrets["private_key"].replace("\\n", "\n"),
            "client_email": raw_secrets["client_email"],
            "client_id": raw_secrets["client_id"],
            "auth_uri": raw_secrets["auth_uri"],
            "token_uri": raw_secrets["token_uri"],
            "auth_provider_x509_cert_url": raw_secrets["auth_provider_x509_cert_url"],
            "client_x509_cert_url": raw_secrets["client_x509_cert_url"],
            "universe_domain": raw_secrets.get("universe_domain", "googleapis.com")
        }
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Errore di connessione a Firebase: {e}")
        st.stop()

db = firestore.client()

# --- FUNZIONI DI UTILITÀ DATABASE (FIREBASE) ---
@st.cache_data(ttl=600)
def carica_da_firestore_cached(collezione_nome):
    try:
        docs = list(db.collection(collezione_nome).stream())
        data = {doc.id: doc.to_dict() for doc in docs}
        
        if collezione_nome in ["cani", "volontari"]:
            return data.get("lista", {}).get("elementi", [])
        elif collezione_nome in ["turni", "turni_lpu"]:
            return [doc.to_dict() for doc in docs] if docs else []
        return data if data else {}
    except Exception:
        return None

def carica_da_firestore_live(collezione_nome, default_val):
    res = carica_da_firestore_cached(collezione_nome)
    return res if res is not None else default_val

def salva_su_firestore(collezione_nome, doc_id, data_dict):
    try:
        db.collection(collezione_nome).document(str(doc_id)).set(data_dict)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Errore di salvataggio: {e}")
        return False

def elimina_da_firestore(collezione_nome, doc_id):
    try:
        db.collection(collezione_nome).document(str(doc_id)).delete()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Errore di eliminazione: {e}")
        return False

# --- INIZIALIZZAZIONE SESSION STATE ---
if "cani" not in st.session_state:
    default_cani = ["Marley", "Diego", "Lucky", "Macchia", "Sami", "Bonnie", "Giada", "Nelson", "Amber"]
    cani_caricati = carica_da_firestore_live("cani", default_cani)
    st.session_state.cani = cani_caricati if cani_caricati else default_cani

if "cani_dettagli" not in st.session_state:
    st.session_state.cani_dettagli = carica_da_firestore_live("cani_dettagli", {})

if "volontari_db" not in st.session_state:
    turni_temp = carica_da_firestore_live("turni", [])
    nomi_iniziali = sorted(list(set(t.get("volontario", "").strip() for t in turni_temp if t.get("volontario"))))
    vol_caricati = carica_da_firestore_live("volontari", nomi_iniziali)
    st.session_state.volontari_db = vol_caricati if vol_caricati else nomi_iniziali

if "volontari_permessi" not in st.session_state:
    st.session_state.volontari_permessi = carica_da_firestore_live("volontari_permessi", {})

if "lpu_data" not in st.session_state:
    st.session_state.lpu_data = carica_da_firestore_live("lpu_data", {})

if "cani_archivio" not in st.session_state:
    st.session_state.cani_archivio = carica_da_firestore_live("cani_archivio", {})

if "turni_lpu" not in st.session_state:
    st.session_state.turni_lpu = carica_da_firestore_live("turni_lpu", [])

if "turni" not in st.session_state:
    st.session_state.turni = carica_da_firestore_live("turni", [])

if "note_turni_db" not in st.session_state:
    res_note = carica_da_firestore_live("note_turni", {})
    st.session_state.note_turni_db = res_note if isinstance(res_note, dict) else {}

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# --- LOGICA ABILITAZIONI ROBUSTA (CASE-INSENSITIVE) ---
def ottieni_permessi_volontario(volontario):
    if not volontario:
        return {}
    vol_lower = volontario.strip().lower()
    for k, v in st.session_state.volontari_permessi.items():
        if k.strip().lower() == vol_lower:
            return v
    return {}

def ottieni_cani_abilitati_utente(volontario):
    permessi = ottieni_permessi_volontario(volontario)
    chiusi_ok = [c.strip().lower() for c in permessi.get("cani_chiusi_abilitati", [])]
    gruppo_ok = [c.strip().lower() for c in permessi.get("cani_gruppo_dedicato_abilitati", [])]
    
    abilitati = []
    for c in st.session_state.cani:
        dettagli = st.session_state.cani_dettagli.get(c, {})
        is_chiuso = dettagli.get("cane_chiuso", False)
        is_gruppo = dettagli.get("gruppo_dedicato", False)
        c_lower = c.lower()
        
        if is_chiuso and c_lower not in chiusi_ok:
            continue
        if is_gruppo and c_lower not in gruppo_ok:
            continue
        abilitati.append(c)
    return abilitati

def trova_cani_non_autorizzati(cani_selezionati, volontario):
    permessi = ottieni_permessi_volontario(volontario)
    chiusi_ok = [c.strip().lower() for c in permessi.get("cani_chiusi_abilitati", [])]
    gruppo_ok = [c.strip().lower() for c in permessi.get("cani_gruppo_dedicato_abilitati", [])]
    
    non_autorizzati = []
    for c in cani_selezionati:
        dettagli = st.session_state.cani_dettagli.get(c, {})
        is_chiuso = dettagli.get("cane_chiuso", False)
        is_gruppo = dettagli.get("gruppo_dedicato", False)
        c_lower = c.lower()
        
        if is_chiuso and c_lower not in chiusi_ok:
            non_autorizzati.append(c)
        elif is_gruppo and c_lower not in gruppo_ok:
            non_autorizzati.append(c)
    return non_autorizzati

def valida_e_salva_turno(volontario_selezionato, cani_selezionati):
    non_autorizzati = trova_cani_non_autorizzati(cani_selezionati, volontario_selezionato)
    if non_autorizzati:
        msg = f"⚠️ Non possiedi l'abilitazione per: `{', '.join(non_autorizzati)}`. Seleziona solo i cani autorizzati."
        st.toast(msg, icon="🚨")
        st.error(msg)
        return False
    return True

# --- ORARIO ITALIANO E SETTIMANE ---
tz_italia = pytz.timezone("Europe/Rome")
adesso = datetime.now(tz_italia)
is_weekend_reale = (adesso.weekday() > 4) or (adesso.weekday() == 4 and adesso.hour >= 17)
is_weekend_o_venerdi_sera = is_weekend_reale

def calcola_eta(data_nascita_str):
    if not data_nascita_str or data_nascita_str == "N/D":
        return "N/D"
    try:
        dt = datetime.strptime(data_nascita_str, "%d/%m/%Y").date()
        oggi = adesso.date()
        anni = oggi.year - dt.year
        mesi = oggi.month - dt.month
        if oggi.day < dt.day:
            mesi -= 1
        if mesi < 0:
            anni -= 1
            mesi += 12
        if anni == 0 and mesi == 0:
            return "Cucciolo"
        elif anni == 0:
            return f"{mesi} mesi"
        elif mesi == 0:
            return f"{anni} anni"
        return f"{anni} anni e {mesi} mesi"
    except Exception:
        return "N/D"

def get_info_settimane():
    oggi = adesso
    lunedi_corr = (oggi - timedelta(days=oggi.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    domenica_corr = lunedi_corr + timedelta(days=6)
    lunedi_pros = lunedi_corr + timedelta(days=7)
    domenica_pros = domenica_corr + timedelta(days=7)

    a_c, s_c, _ = lunedi_corr.isocalendar()
    a_p, s_p, _ = lunedi_pros.isocalendar()
    
    return {
        "chiave_corr": f"{a_c}-W{s_c:02d}",
        "chiave_pros": f"{a_p}-W{s_p:02d}",
        "label_corr": f"Settimana dal {lunedi_corr.strftime('%d/%m/%Y')} al {domenica_corr.strftime('%d/%m/%Y')}",
        "label_pros": f"Prossima Settimana dal {lunedi_pros.strftime('%d/%m/%Y')} al {domenica_pros.strftime('%d/%m/%Y')}",
        "lunedi_corrente": lunedi_corr
    }

info_sett = get_info_settimane()
chiave_corr, chiave_pros = info_sett["chiave_corr"], info_sett["chiave_pros"]
label_corr, label_pros = info_sett["label_corr"], info_sett["label_pros"]

def carica_turni_normalizzati():
    turni_grezzi = carica_da_firestore_live("turni", [])
    turni_norm = []
    for t in turni_grezzi:
        s_chiave = t.get("settimana_chiave", chiave_corr)
        try:
            a_s, s_s = s_chiave.split("-W")
            lun_rif = datetime.fromisocalendar(int(a_s), int(s_s), 1).replace(tzinfo=tz_italia)
            dom_rif = lun_rif + timedelta(days=6)
            t["settimana"] = f"Settimana dal {lun_rif.strftime('%d/%m/%Y')} al {dom_rif.strftime('%d/%m/%Y')}"
            t["settimana_chiave"] = s_chiave
        except Exception:
            pass
        turni_norm.append(t)
    return turni_norm

# --- BARRA LATERALE ---
with st.sidebar:
    if os.path.exists("icona.jpg"):
        st.image("icona.jpg", width=80)
    st.title("🐾 Menu Rapido")
    
    if st.button("🔄 Aggiorna Dati"):
        st.cache_data.clear()
        st.success("Dati aggiornati!")
        st.rerun()

    with st.expander("🔍 Cerca i miei turni", expanded=False):
        turni_side = carica_turni_normalizzati()
        nomi_side = sorted(list(set(t.get("volontario", "").strip() for t in turni_side if t.get("volontario"))))
        if nomi_side:
            nome_scelto = st.selectbox("Il tuo nome:", nomi_side, key="sel_miei_turni_side")
            miei_t = [t for t in turni_side if t.get("volontario", "").strip().lower() == nome_scelto.lower()]
            for tp in miei_t:
                cani_s = ", ".join(tp.get("cani_fatti", [])) or "🧹 Pulizie / LPU"
                st.markdown(f"• **{tp.get('settimana')}**<br>📅 {tp.get('giorno')} ({tp.get('fascia')} - {tp.get('orario')})<br>🐾 [{cani_s}]", unsafe_allow_html=True)
                st.markdown("---")

    with st.expander("🎛️ Filtri Panoramica", expanded=False):
        st.selectbox("Filtra per cane:", ["Tutti i cani"] + sorted(st.session_state.cani), key="filtro_cane_side")
        tutti_v = sorted(list(set(t.get("volontario") for t in carica_turni_normalizzati() if t.get("volontario"))))
        st.selectbox("Filtra per volontario:", ["Tutti i volontari"] + tutti_v, key="filtro_vol_side")

    with st.expander("🔒 Area Admin", expanded=False):
        pwd_corretta = st.secrets.get("ADMIN_PASSWORD", "canile2026")
        if not st.session_state.is_admin:
            with st.form("login_admin"):
                pwd = st.text_input("Password:", type="password")
                if st.form_submit_button("Sblocca") and pwd == pwd_corretta:
                    st.session_state.is_admin = True
                    st.rerun()
        else:
            st.success("🔓 Admin attivo")
            sim = st.selectbox("Simulazione:", ["📅 Automatico", "⚠️ Simula Weekend", "🟢 Simula Feriale"])
            if sim == "⚠️ Simula Weekend": is_weekend_o_venerdi_sera = True
            elif sim == "🟢 Simula Feriale": is_weekend_o_venerdi_sera = False
            else: is_weekend_o_venerdi_sera = is_weekend_reale
            
            if st.button("🔒 Esci Admin"):
                st.session_state.is_admin = False
                st.rerun()

# --- INTESTAZIONE E AVVISI ---
st.title("🐾 Turni Canile")

with st.container():
    turni_oggi = [t for t in carica_turni_normalizzati() if t.get("giorno") == GIORNI_SETTIMANA[adesso.weekday()] and t.get("settimana_chiave") == chiave_corr]
    cani_coperti = {c for t in turni_oggi for c in t.get("cani_fatti", [])}
    cani_scoperti = [c for c in st.session_state.cani if c not in cani_coperti and datetime.strptime(st.session_state.cani_dettagli.get(c, {}).get("data_entrata", "01/01/2000"), "%d/%m/%Y").date() <= adesso.date()]
    
    if turni_oggi and cani_scoperti:
        with st.expander("🔔 Avviso del Giorno", expanded=True):
            st.warning(f"⚠️ Cani senza volontari oggi: `{', '.join(cani_scoperti)}`")

# --- NAVIGAZIONE PRINCIPALE ---
if st.session_state.is_admin:
    menu = st.pills("Sezione:", ["📅 Inserisci", "👀 Panoramica", "🐶 Cani", "📊 Statistiche", "📚 Archivio", "👥 Volontari", "🛠️ Gestione LPU (Admin)", "🏡 Archivio Cani Adottati"])
else:
    m_princ = st.pills("Sezione:", ["📅 Inserisci", "👀 Panoramica", "🐶 Cani", "📁 Altro"])
    menu = st.selectbox("Voce:", ["📊 Statistiche", "📚 Archivio Settimane", "🏡 Archivio Cani Adottati"], key="sub_altro") if m_princ == "📁 Altro" else m_princ

st.markdown("---")

if is_weekend_o_venerdi_sera:
    st.warning("⚠️ **Promemoria:** È iniziato il fine settimana! Ricordati di selezionare la **'Prossima Settimana'** per i nuovi turni.")

# ================= SEZIONE INSERISCI =================
if menu == "📅 Inserisci":
    st.header("Gestione Turni")
    
    opz_sett = [label_corr, label_pros] if is_weekend_o_venerdi_sera else [label_corr]
    map_sett = {label_corr: chiave_corr, label_pros: chiave_pros}
    sett_label = st.radio("Settimana:", opz_sett, horizontal=True)
    sett_chiave = map_sett[sett_label]

    vol_reg = sorted(list(set(st.session_state.volontari_db)))
    vol_scelta = st.selectbox("Il tuo Nome e Cognome:", ["-- Seleziona il tuo nome --"] + vol_reg + ["➕ Altro / Nuovo volontario"])
    volontario = st.text_input("Scrivi il tuo nome:").strip() if vol_scelta == "➕ Altro / Nuovo volontario" else (vol_scelta if vol_scelta != "-- Seleziona il tuo nome --" else "")

    st.markdown("---")
    mod_ins = st.radio("Modalità:", ["Turno Singolo", "Inserimento Multiplo"], horizontal=True)
    st.markdown("---")

    if mod_ins == "Turno Singolo":
        c1, c2 = st.columns(2)
        giorno = c1.selectbox("Giorno:", GIORNI_SETTIMANA)
        fascia = c2.selectbox("Fascia:", FASCE_ORARIE)

        def_i, def_f = (time(8, 30), time(12, 0)) if fascia == "Mattina" else (time(14, 30), time(18, 0))
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            ora_i = st.time_input("Da:", value=def_i)
            senza_fine = st.checkbox("Senza orario di fine")
        with col_t2:
            ora_f = st.time_input("A:", value=def_f) if not senza_fine else None
        
        orario = f"Dalle {ora_i.strftime('%H:%M')}" if senza_fine else f"{ora_i.strftime('%H:%M')} - {ora_f.strftime('%H:%M')}"

        cani_abilitati_utente = ottieni_cani_abilitati_utente(volontario)
        
        col_op1, col_op2 = st.columns([1, 1])
        seleziona_tutti = col_op1.checkbox("🐾 Seleziona TUTTI i cani")
        col_op2.caption("💡 Ti ho preselezionato i cani per cui sei abilitato.")

        cani_fatti = st.pills("✅ Cani:", options=st.session_state.cani, default=st.session_state.cani if seleziona_tutti else cani_abilitati_utente, selection_mode="multi")

        non_aut = trova_cani_non_autorizzati(cani_fatti, volontario)
        if non_aut:
            st.error(f"🚨 **ATTENZIONE:** Non possiedi l'abilitazione per: `{', '.join(non_aut)}`!")

        nota = st.text_area("Nota personale (Opzionale):", placeholder="Eventuali annotazioni...")

        if st.button("Registra Turno 🚀", type="primary"):
            if not volontario:
                st.warning("Inserisci il tuo nome.")
            elif not cani_fatti:
                st.error("Seleziona almeno un cane.")
            elif (fascia == "Mattina" and ora_i >= time(14, 0)) or (fascia == "Pomeriggio" and ora_i < time(14, 0)):
                st.error("Orario non coerente con la fascia scelta.")
            elif valida_e_salva_turno(volontario, cani_fatti):
                if volontario not in st.session_state.volontari_db:
                    st.session_state.volontari_db.append(volontario)
                    salva_su_firestore("volontari", "lista", {"elementi": st.session_state.volontari_db})

                doppione = any(t.get("volontario", "").strip().lower() == volontario.lower() and t.get("settimana_chiave") == sett_chiave and t.get("giorno") == giorno and t.get("fascia") == fascia for t in carica_turni_normalizzati())
                if doppione:
                    st.error(f"⚠️ Hai già un turno registrato per {giorno} ({fascia}) in questa settimana!")
                else:
                    id_t = str(datetime.now().timestamp())
                    nuovo_t = {"id": id_t, "settimana": sett_label, "settimana_chiave": sett_chiave, "volontario": volontario, "giorno": giorno, "fascia": fascia, "orario": orario, "cani_fatti": cani_fatti, "note": nota.strip()}
                    salva_su_firestore("turni", id_t, nuovo_t)
                    st.toast("Turno registrato con successo!", icon="🎉")
                    st.rerun()

    else:  # Inserimento Multiplo
        giorni_scelti = [g for g in GIORNI_SETTIMANA if st.checkbox(g, key=f"multi_{g}")]
        fascia_m = st.selectbox("Fascia comune:", FASCE_ORARIE)
        
        col_m1, col_m2 = st.columns(2)
        oi_m = col_m1.time_input("Da:", value=time(8, 30) if fascia_m == "Mattina" else time(14, 30))
        senza_fine_m = col_m1.checkbox("Senza fine (multiplo)")
        of_m = col_m2.time_input("A:", value=time(12, 0) if fascia_m == "Mattina" else time(18, 0)) if not senza_fine_m else None
        orario_m = f"Dalle {oi_m.strftime('%H:%M')}" if senza_fine_m else f"{oi_m.strftime('%H:%M')} - {of_m.strftime('%H:%M')}"

        cani_abilitati_utente_m = ottieni_cani_abilitati_utente(volontario)
        cani_fatti_m = st.pills("✅ Cani gestiti:", options=st.session_state.cani, default=cani_abilitati_utente_m, selection_mode="multi")
        
        non_aut_m = trova_cani_non_autorizzati(cani_fatti_m, volontario)
        if non_aut_m:
            st.error(f"🚨 **ATTENZIONE:** Non possiedi l'abilitazione per: `{', '.join(non_aut_m)}`!")

        nota_m = st.text_area("Nota comune:")

        if st.button("Registra Turni in Blocco 🚀", type="primary"):
            if not volontario or not giorni_scelti or not cani_fatti_m:
                st.error("Compila nome, seleziona almeno un giorno e un cane.")
            elif valida_e_salva_turno(volontario, cani_fatti_m):
                if volontario not in st.session_state.volontari_db:
                    st.session_state.volontari_db.append(volontario)
                    salva_su_firestore("volontari", "lista", {"elementi": st.session_state.volontari_db})
                
                esistenti = carica_turni_normalizzati()
                inseriti = 0
                for g in giorni_scelti:
                    doppione = any(t.get("volontario", "").strip().lower() == volontario.lower() and t.get("settimana_chiave") == sett_chiave and t.get("giorno") == g and t.get("fascia") == fascia_m for t in esistenti)
                    if not doppione:
                        id_t = f"{datetime.now().timestamp()}_{g[:3]}"
                        nuovo_t = {"id": id_t, "settimana": sett_label, "settimana_chiave": sett_chiave, "volontario": volontario, "giorno": g, "fascia": fascia_m, "orario": orario_m, "cani_fatti": cani_fatti_m, "note": nota_m.strip()}
                        salva_su_firestore("turni", id_t, nuovo_t)
                        inseriti += 1
                st.toast(f"Registrati {inseriti} turni in blocco!", icon="🎉")
                st.rerun()

# ================= SEZIONE PANORAMICA =================
elif menu == "👀 Panoramica":
    st.header("Gestione Turni e Copertura")
    mod_vista = st.pills("Vista:", ["📅 Settimana Completa", "🎯 Solo Oggi"], default="🎯 Solo Oggi")
    
    opz_vis = [label_corr, label_pros] if is_weekend_o_venerdi_sera else [label_corr]
    map_vis = {label_corr: chiave_corr, label_pros: chiave_pros}
    sett_vista_label = st.radio("Periodo:", opz_vis, horizontal=True)
    sett_vista_chiave = map_vis[sett_vista_label]

    lun_vista = datetime.fromisocalendar(*map(int, sett_vista_chiave.split("-W")), 1).date()
    turni_attuali = [t for t in carica_turni_normalizzati() if t.get("settimana_chiave") == sett_vista_chiave]

    if st.session_state.get("filtro_cane_side", "Tutti i cani") != "Tutti i cani":
        turni_attuali = [t for t in turni_attuali if st.session_state.filtro_cane_side in t.get("cani_fatti", [])]
    if st.session_state.get("filtro_vol_side", "Tutti i volontari") != "Tutti i volontari":
        turni_attuali = [t for t in turni_attuali if t.get("volontario") == st.session_state.filtro_vol_side]

    giorni_mostrati = [(adesso.weekday(), GIORNI_SETTIMANA[adesso.weekday()])] if mod_vista == "🎯 Solo Oggi" else list(enumerate(GIORNI_SETTIMANA))

    for idx_g, giorno in giorni_mostrati:
        t_giorno = [t for t in turni_attuali if t.get("giorno") == giorno]
        data_g = lun_vista + timedelta(days=idx_g)
        
        st.markdown(f"## 📌 {giorno} ({data_g.strftime('%d/%m/%Y')})")
        col_m, col_p = st.columns(2)

        for col, fascia in zip([col_m, col_p], FASCE_ORARIE):
            with col:
                with st.container(border=True):
                    st.markdown(f"### {'🌅' if fascia == 'Mattina' else '🌇'} {fascia}")
                    t_fascia = sorted([t for t in t_giorno if t.get("fascia") == fascia], key=lambda x: (0 if x.get("id","").startswith("lpu_") else 1))
                    
                    if not t_fascia:
                        st.caption("Nessun volontario.")
                    else:
                        for t in t_fascia:
                            cani_s = ", ".join(t.get("cani_fatti", [])) or "🧹 Pulizie / LPU"
                            st.write(f"• **{t.get('volontario')}** ({t.get('orario')}) 🐾 [{cani_s}]")
                            if t.get("note"): st.markdown(f"> 💬 *{t.get('note')}*")
                            
                            if st.session_state.is_admin and not t.get("id", "").startswith("lpu_"):
                                if st.button("🗑️ Elimina", key=f"del_{t.get('id')}"):
                                    elimina_da_firestore("turni", t.get("id"))
                                    st.success("Eliminato!")
                                    st.rerun()

# ================= SEZIONE CANI =================
elif menu == "🐶 Cani":
    st.header("🐾 Anagrafica Cani")
    if st.session_state.is_admin and st.button("➕ Aggiungi Nuovo Cane", type="primary"):
        @st.dialog("➕ Nuovo Cane")
        def modale_cane():
            nome = st.text_input("Nome:")
            sesso = st.selectbox("Sesso:", ["Maschio", "Femmina"])
            taglia = st.selectbox("Taglia:", ["Piccola", "Media", "Grande"])
            data_ent = st.date_input("Data entrata:", value=adesso.date())
            c_chiuso = st.checkbox("🔒 Cane chiuso")
            g_ded = st.checkbox("👥 Gruppo dedicato")
            if st.button("Salva") and nome.strip():
                n_p = nome.strip()
                if n_p not in st.session_state.cani:
                    st.session_state.cani.append(n_p)
                    salva_su_firestore("cani", "lista", {"elementi": st.session_state.cani})
                    dett = {"sesso": sesso, "taglia": taglia, "data_entrata": data_ent.strftime("%d/%m/%Y"), "cane_chiuso": c_chiuso, "gruppo_dedicato": g_ded}
                    st.session_state.cani_dettagli[n_p] = dett
                    salva_su_firestore("cani_dettagli", n_p, dett)
                    st.success("Salvato!")
                    st.rerun()
        modale_cane()

    for dog in sorted(st.session_state.cani):
        dett = st.session_state.cani_dettagli.get(dog, {})
        with st.container(border=True):
            st.markdown(f"### 🐾 {dog} ({dett.get('sesso', 'N/D')}, {dett.get('taglia', 'N/D')})")
            st.markdown(f"• Entrata: `{dett.get('data_entrata', 'N/D')}`")
            if st.session_state.is_admin and st.button("🗑️ Elimina", key=f"del_c_{dog}"):
                st.session_state.cani.remove(dog)
                salva_su_firestore("cani", "lista", {"elementi": st.session_state.cani})
                elimina_da_firestore("cani_dettagli", dog)
                st.rerun()

# ================= SEZIONE VOLONTARI =================
elif menu == "👥 Volontari":
    st.header("👥 Abilitazioni Volontari")
    if not st.session_state.is_admin:
        st.warning("Area riservata agli admin.")
    else:
        v_lista = sorted(list(set(st.session_state.volontari_db)))
        if v_lista:
            v_sel = st.selectbox("Seleziona Volontario:", v_lista)
            c_chiusi = [c for c in st.session_state.cani if st.session_state.cani_dettagli.get(c, {}).get("cane_chiuso")]
            c_gruppo = [c for c in st.session_state.cani if st.session_state.cani_dettagli.get(c, {}).get("gruppo_dedicato")]
            
            p_corr = ottieni_permessi_volontario(v_sel)
            with st.form("form_perm"):
                scelti_c = st.pills("🔒 Cani chiusi abilitati:", options=c_chiusi, default=[c for c in p_corr.get("cani_chiusi_abilitati", []) if c in c_chiusi], selection_mode="multi")
                scelti_g = st.pills("👥 Gruppo dedicato abilitati:", options=c_gruppo, default=[c for c in p_corr.get("cani_gruppo_dedicato_abilitati", []) if c in c_gruppo], selection_mode="multi")
                if st.form_submit_button("Salva Abilitazioni"):
                    st.session_state.volontari_permessi[v_sel] = {"cani_chiusi_abilitati": scelti_c, "cani_gruppo_dedicato_abilitati": scelti_g}
                    salva_su_firestore("volontari_permessi", v_sel, st.session_state.volontari_permessi[v_sel])
                    st.success("Abilitazioni aggiornate!")
                    st.rerun()

# ================= ALTRE SEZIONI =================
elif menu == "📊 Statistiche":
    st.header("📊 Statistiche Uscite")
    turni_st = carica_turni_normalizzati()
    uscite = {c: sum(1 for t in turni_st for can in t.get("cani_fatti", []) if can == c) for c in st.session_state.cani}
    cols = st.columns(3)
    for idx, (c, cnt) in enumerate(sorted(uscite.items(), key=lambda x: x[1], reverse=True)):
        cols[idx % 3].metric(f"🐾 {c}", f"{cnt} uscite")

elif menu in ["📚 Archivio", "📚 Archivio Settimane"]:
    st.header("📚 Archivio Storico")
    for t in reversed(carica_turni_normalizzati()):
        st.write(f"• **{t.get('settimana')}** | {t.get('giorno')} ({t.get('fascia')}) - **{t.get('volontario')}**: {', '.join(t.get('cani_fatti', [])) or 'Pulizie'}")

elif menu == "🛠️ Gestione LPU (Admin)":
    st.header("🛠️ Gestione LPU")
    if not st.session_state.is_admin:
        st.error("Accesso negato.")
    else:
        lpu_dict = st.session_state.lpu_data
        with st.form("add_lpu"):
            n_lpu = st.text_input("Nome LPU:")
            ore_req = st.number_input("Ore totali:", value=50.0)
            if st.form_submit_button("Salva LPU") and n_lpu.strip():
                lpu_dict[n_lpu.strip()] = {"ore_totali": ore_req, "ore_fatte": 0.0}
                salva_su_firestore("lpu_data", n_lpu.strip(), lpu_dict[n_lpu.strip()])
                st.success("Salvato!")
                st.rerun()
        for k, v in lpu_dict.items():
            st.write(f"• **{k}**: {v['ore_fatte']}h / {v['ore_totali']}h")

elif menu == "🏡 Archivio Cani Adottati":
    st.header("🏡 Cani Adottati")
    arch = carica_da_firestore_live("cani_archivio", {})
    if not arch:
        st.info("Nessun cane in archivio.")
    else:
        for k, v in arch.items():
            with st.container(border=True):
                st.markdown(f"### 🐾 {k} (Adottato il {v.get('data_uscita')})")
