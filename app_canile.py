import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

st.set_page_config(page_title="Gestione Turni Canile", page_icon="🐶", layout="wide")

st.title("🐾 Gestione Turni Canile - Test Connessione")

# Inizializzazione protetta di Firebase
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        cred_dict = {
            "type": st.secrets["type"],
            "project_id": st.secrets["project_id"],
            "private_key_id": st.secrets["private_key_id"],
            "private_key": st.secrets["private_key"].replace("\\n", "\n"),
            "client_email": st.secrets["client_email"],
            "client_id": st.secrets["client_id"],
            "auth_uri": st.secrets["auth_uri"],
            "token_uri": st.secrets["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["client_x509_cert_url"],
            "universe_domain": st.secrets["universe_domain"]
        }
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

try:
    db = init_firebase()
    st.success("Connessione a Firestore stabilita con successo!")
    
    # Test lettura collezione cani
    docs = list(db.collection("cani").stream())
    data = {doc.id: doc.to_dict() for doc in docs}
    st.write("Dati letti da Firestore:", data)
    
except Exception as e:
    st.error(f"Errore durante la connessione o la lettura: {e}")
