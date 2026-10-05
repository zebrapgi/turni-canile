import streamlit as st

st.set_page_config(page_title="Test Avvio Canile", page_icon="🐶", layout="wide")

st.title("🐾 Test Avvio in Corso")
st.success("L'applicazione si è avviata correttamente!")

if "cani" not in st.session_state:
    st.session_state.cani = ["Marley", "Diego", "Lucky", "Macchia", "Sami", "Bonnie", "Giada", "Nelson", "Amber"]

st.write("Cani registrati nello stato:", st.session_state.cani)
