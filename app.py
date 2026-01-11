import streamlit as st
import os
import google.generativeai as genai
from dotenv import load_dotenv
from pypdf import PdfReader # Librăria nouă pentru PDF-uri

# 1. Configurare
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ Cheia API lipsește!")
    st.stop()

genai.configure(api_key=api_key)

# Folosim modelul Flash simplu, fără tools momentan (pentru stabilitate maximă)
# Gemini 2.5 are context uriaș, deci putem încărca PDF-uri mari direct în el.
try:
    model = genai.GenerativeModel('models/gemini-2.5-flash')
except:
    model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="Piping Assistant AI", page_icon="🔧", layout="wide")

# --- ZONA LATERALĂ (Setup Proiect) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3093/3093466.png", width=50)
    st.title("🎛️ Panou Proiect")
    st.markdown("---")
    
    # Selector Proiect
    proiect_activ = st.selectbox("Proiect Activ:", ["General", "Rafinărie Brazi", "Conductă Gaz"])
    
    st.info(f"Context: **{proiect_activ}**")
    st.markdown("---")
    
    # UPLOAD PDF (Creierul Aplicației)
    st.subheader("📄 Documentație Tehnică")
    uploaded_file = st.file_uploader("Încarcă Caiet de Sarcini / Standard", type="pdf")
    
    # Procesarea PDF-ului
    if uploaded_file is not None:
        if "pdf_text" not in st.session_state:
            st.session_state.pdf_text = ""
            
        with st.spinner("Citesc documentul..."):
            try:
                reader = PdfReader(uploaded_file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                
                # Salvăm textul în memorie
                st.session_state.pdf_text = text
                st.success(f"✅ Document încărcat! ({len(reader.pages)} pagini)")
            except Exception as e:
                st.error(f"Eroare la citire: {e}")
    
    if st.button("🗑️ Șterge Memoria"):
        st.session_state.pdf_text = ""
        st.session_state.messages = []
        st.rerun()

# --- ZONA PRINCIPALĂ ---
st.title("🔧 Piping Assistant Pro")

if "pdf_text" in st.session_state and st.session_state.pdf_text:
    st.caption(f"🧠 Memorie activă: Document încărcat pentru {proiect_activ}")
else:
    st.caption("⚠️ Niciun document încărcat. Răspund din cunoștințe generale.")

# Istoric Chat
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input Utilizator
if prompt := st.chat_input("Întreabă ceva din documentul încărcat..."):
    
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Analizez specificațiile..."):
            try:
                # Construim Prompt-ul FINAL (Context + Document + Întrebare)
                # Aici e secretul: Îi dăm tot textul PDF-ului să îl "vadă"
                pdf_context = st.session_state.get("pdf_text", "")
                
                final_prompt = (
                    f"Ești un Expert Piping Engineer. \n"
                    f"CONTEXT PROIECT: {proiect_activ}\n"
                    f"DOCUMENTAȚIE ÎNCĂRCATĂ:\n {pdf_context[:500000]} \n" # Limită de siguranță, dar 2.5 duce mult mai mult
                    f"--------------------------------\n"
                    f"ÎNTREBAREA UTILIZATORULUI: {prompt}\n"
                    f"Răspunde tehnic, citând secțiuni din document dacă este posibil."
                )
                
                response = model.generate_content(final_prompt)
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
            except Exception as e:
                st.error(f"Eroare: {e}")