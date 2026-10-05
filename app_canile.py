import streamlit as st

st.set_page_config(page_title="Test Avvio", page_icon="🧪")

st.title("🧪 Test di Diagnostica Streamlit")
st.success("Se vedi questo messaggio, Streamlit Cloud e GitHub funzionano correttamente!")

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    st.write("Librerie Firebase importate con successo.")
    
    if "FIREBASE_JSON" in st.secrets:
        st.write("Segreto FIREBASE_JSON trovato correttamente nei Settings di Streamlit Cloud.")
    else:
      st.error("ERRORE: Il segreto FIREBASE_JSON non è configurato nei Settings di Streamlit Cloud!")
        
except Exception as e:
    st.error(f"Errore riscontrato: {e}")
