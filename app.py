import streamlit as st
import os
import io
import time
import requests
from dotenv import load_dotenv
from pypdf import PdfReader
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from streamlit_lottie import st_lottie
from duckduckgo_search import DDGS

# --- 1. CONFIGURATION ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ API Key missing!")
    st.stop()

genai.configure(api_key=api_key)

SERVICE_ACCOUNT_FILE = 'service_account.json' 
SCOPES = ['https://www.googleapis.com/auth/drive'] 

st.set_page_config(page_title="Piping Agent Pro", page_icon="🔍", layout="wide")

# --- 2. BACKEND FUNCTIONS ---

def authenticate_drive():
    if not os.path.exists(SERVICE_ACCOUNT_FILE): return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return build('drive', 'v3', credentials=creds)
    except: return None

# --- TOOL 1: LIBRARY SEARCH (Găsește fișierele) ---
def tool_search_library(keyword: str):
    """
    SEARCHES the Google Drive Library for filenames matching the keyword.
    USE THIS FIRST to check if a file exists (e.g., 'Do you have ASME B16.11?').
    Returns a list of matching filenames.
    """
    print(f"--- TOOL: Searching Library for '{keyword}' ---")
    service = authenticate_drive()
    if not service: return "Error: Drive connection failed."
    
    # Cautam recursiv in toate folderele (Drive face asta default)
    q = f"name contains '{keyword}' and mimeType = 'application/pdf' and trashed=false"
    try:
        results = service.files().list(
            q=q, 
            pageSize=20, # Returnam primele 20 rezultate gasite
            fields="files(id, name)"
        ).execute()
        
        files = results.get('files', [])
        if not files:
            return f"No files found matching '{keyword}' in the library."
        
        file_list_str = "\n".join([f"- {f['name']}" for f in files])
        return f"FOUND {len(files)} FILES matching '{keyword}':\n{file_list_str}\n\n(Ask me to READ one of these specifically.)"
    except Exception as e:
        return f"Search Error: {e}"

# --- TOOL 2: DRIVE READER (Citește conținutul) ---
def tool_read_document(exact_filename: str):
    """
    READS the content of a specific PDF file found by the search tool.
    MANDATORY: Provide the exact filename from the search results.
    """
    print(f"--- TOOL: Reading content of '{exact_filename}' ---")
    service = authenticate_drive()
    if not service: return "Error: Drive connection failed."
    
    q = f"name = '{exact_filename}' and mimeType = 'application/pdf' and trashed=false"
    results = service.files().list(q=q, pageSize=1, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    if not files:
        # Fallback la contains daca numele nu e exact
        q = f"name contains '{exact_filename}' and mimeType = 'application/pdf' and trashed=false"
        results = service.files().list(q=q, pageSize=1, fields="files(id, name)").execute()
        files = results.get('files', [])
        
    if not files: return "File not found."
    
    target = files[0]
    try:
        request = service.files().get_media(fileId=target['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        
        fh.seek(0)
        reader = PdfReader(fh)
        text = ""
        for i, page in enumerate(reader.pages[:40]): # Limita 40 pagini
            text += f"\n[DOC: {target['name']} | PAGE: {i+1}]\n{page.extract_text()}\n"
            
        if "loaded_docs" not in st.session_state: st.session_state.loaded_docs = []
        if target['name'] not in st.session_state.loaded_docs:
            st.session_state.loaded_docs.append(target['name'])
            
        return f"SUCCESS. Content of '{target['name']}':\n{text[:100000]}"
    except Exception as e:
        return f"Read Error: {e}"

# --- TOOL 3: WEB SEARCH ---
def tool_search_web(query: str):
    """Searches the internet (DuckDuckGo) for images/prices/info."""
    try:
        results = DDGS().text(query, max_results=5)
        if not results: return "No web results."
        summary = ""
        for r in results:
            summary += f"- {r['title']}: {r['href']}\n"
        return summary
    except Exception as e:
        return f"Web Error: {e}"

# --- UPLOAD FUNCTION ---
def upload_to_drive(uploaded_file):
    service = authenticate_drive()
    if not service: return False, "Auth Error"
    try:
        q = "mimeType='application/vnd.google-apps.folder' and name='PIPING_LIBRARY' and trashed=false"
        res = service.files().list(q=q, fields="files(id)").execute()
        folders = res.get('files', [])
        parent_id = folders[0]['id'] if folders else None
        
        file_metadata = {'name': uploaded_file.name}
        if parent_id: file_metadata['parents'] = [parent_id]
            
        media = MediaIoBaseUpload(uploaded_file, mimetype='application/pdf')
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return True, "OK"
    except Exception as e:
        return False, str(e)

# --- 3. AUTO-DETECT MODEL ---
tools_list = [tool_search_library, tool_read_document, tool_search_web]

def get_working_model():
    try:
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in available: 
            if "flash" in m and "1.5" in m: return m
        for m in available: 
            if "pro" in m and "1.5" in m: return m
        if available: return available[0]
    except: pass
    return None

valid_model_name = get_working_model()
if not valid_model_name:
    st.error("❌ No Gemini models found.")
    st.stop()

model = genai.GenerativeModel(valid_model_name, tools=tools_list)

# --- 4. SESSION STATE ---
if "messages" not in st.session_state: st.session_state.messages = []
if "loaded_docs" not in st.session_state: st.session_state.loaded_docs = []
if "chat_session" not in st.session_state: 
    st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)

# --- 5. SIDEBAR ---
with st.sidebar:
    lottie_url = "https://lottie.host/5a837012-78d1-4389-9e8a-86695b77ce80/H5pZqg1XlI.json"
    try:
        r = requests.get(lottie_url)
        if r.status_code == 200: st_lottie(r.json(), height=120, key="anim")
    except: pass

    st.title("🧠 Brain Center")
    st.success(f"Engine: `{valid_model_name}`")
    
    st.markdown("---")
    st.subheader("📂 Active Docs")
    if st.session_state.loaded_docs:
        for d in st.session_state.loaded_docs: st.caption(f"✅ {d}")
    else: st.caption("Memory empty.")
    
    st.markdown("---")
    uploaded_file = st.file_uploader("Upload to Library", type=['pdf'])
    if uploaded_file and st.button("💾 Save"):
        with st.spinner("Uploading..."):
            s, m = upload_to_drive(uploaded_file)
            if s: st.success("Saved!"); time.sleep(1); st.rerun()
            else: st.error(f"Error: {m}")
            
    if st.button("🗑️ Reset"):
        st.session_state.messages = []
        st.session_state.loaded_docs = []
        st.session_state.chat_session = model.start_chat(enable_automatic_function_calling=True)
        st.rerun()

# --- 6. CHAT UI ---
st.title("🔎 Piping Agent v13.1 (Deep Search)")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ex: 'Ai standardul ASME B16.11?' sau 'Ce scrie în el?'"):
    with st.chat_message("user"): st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Searching..."):
            try:
                system = (
                    "You are an Expert Piping Engineer.\n"
                    "TOOLS:\n"
                    "1. `tool_search_library`: USE THIS FIRST whenever asking 'do you have this file?'. It searches the entire Drive.\n"
                    "2. `tool_read_document`: Use this ONLY after finding the exact filename with search.\n"
                    "3. `tool_search_web`: For external info.\n"
                    "RULES:\n"
                    "- Do NOT assume you know what files exist. Always use `tool_search_library`.\n"
                    "- Answer in the user's language.\n"
                )
                response = st.session_state.chat_session.send_message(f"{system}\n\nUSER: {prompt}")
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                if len(st.session_state.loaded_docs) > 0: st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")