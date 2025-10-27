import os
import time
from typing import List, Dict, Any
import json
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
import google.generativeai as genai
import requests

# --------- Carregar variáveis de ambiente ---------
load_dotenv()

# --------- Credenciais do Google Service Account ---------
# Usando JSON direto do Streamlit Secrets
try:
    service_account_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = json.dumps(service_account_info)
except KeyError:
    st.error("A chave 'GOOGLE_SERVICE_ACCOUNT_JSON' não foi encontrada em st.secrets.")
    st.stop()

# --------- Função para pegar segredos (prioriza st.secrets) ---------
def secret_get(key: str, default: str | None = None):
    return st.secrets.get(key, os.getenv(key, default))  # type: ignore[attr-defined]

# --------- Chaves da API ---------
API_KEY = secret_get("GEMINI_API_KEY") or secret_get("GOOGLE_API_KEY")
DEFAULT_MODEL = secret_get("GEMINI_MODEL", "gemini-2.0-flash-exp")
DEFAULT_TEMPERATURE = float(secret_get("GEMINI_TEMPERATURE", "0.7"))
ABACUS_API_KEY = secret_get("ABACUS_API_KEY")
ABACUS_MODEL = secret_get("ABACUS_MODEL", "gemini-2.0-flash-exp")
GOOGLE_DRIVE_FOLDER_ID = secret_get("GOOGLE_DRIVE_FOLDER_ID", "")

# --------- Importa serviço do Google Sheets ---------
from google_service import (
    list_spreadsheets,
    get_form_responses,
    get_spreadsheet_info,
    convert_excel_to_google_sheet
)

# --------- Carregar variáveis de ambiente ---------
load_dotenv()

# Carrega segredos (prioriza st.secrets quando disponível)
def secret_get(key: str, default: str | None = None):
    try:
        return st.secrets.get(key, os.getenv(key, default))  # type: ignore[attr-defined]
    except Exception:
        return os.getenv(key, default)

# Disponibiliza credenciais do Google via env para google_service.py
for _k in ("GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SERVICE_ACCOUNT_FILE"):
    try:
        if _k in st.secrets:  # type: ignore[attr-defined]
            os.environ[_k] = str(st.secrets[_k])  # type: ignore[index]
    except Exception:
        pass

API_KEY = secret_get("GEMINI_API_KEY") or secret_get("GOOGLE_API_KEY")
DEFAULT_MODEL = secret_get("GEMINI_MODEL", "gemini-2.0-flash-exp")
DEFAULT_TEMPERATURE = float(secret_get("GEMINI_TEMPERATURE", "0.7"))
ABACUS_API_KEY = secret_get("ABACUS_API_KEY")
ABACUS_MODEL = secret_get("ABACUS_MODEL", "gemini-2.0-flash-exp")
ABACUS_URL = "https://routellm.abacus.ai/v1/chat/completions"

# OBS: Passaremos a listar todo o Drive, sem filtrar por pasta específica
DRIVE_FOLDER_ID = None
SHEETS_FOLDER_ID = None

# --------- Configuração da página ---------
st.set_page_config(
    page_title="Alpha Insights | Assistente de Análise",
    page_icon=None,
    layout="wide",
)

# --------- Estilos customizados - Design Minimalista ---------
st.markdown(
    """
    <style>
    /* ========== IMPORTAÇÃO DE FONTES ========== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* ========== VARIÁVEIS GLOBAIS ========== */
    :root {
        --primary-blue: #3B82F6;
        --light-blue: #DBEAFE;
        --bg-gray: #F9FAFB;
        --text-dark: #111827;
        --text-gray: #6B7280;
        --text-light: #9CA3AF;
        --border-color: #E5E7EB;
        --white: #FFFFFF;
        --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.05);
        --shadow-sm: 0 2px 4px rgba(0, 0, 0, 0.06);
        --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.08);
        --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.10);
    }
    
    /* ========== LAYOUT BASE ========== */
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    .stApp {
        background: #FAFAFA;
    }
    
    .main .block-container { 
        padding: 2rem 3rem;
        max-width: 1000px;
        margin: 0 auto;
    }
    
    /* ========== HIDDEN ELEMENTS (mantém menu oculto, cabeçalho visível p/ toggle) ========== */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    /* header visível para permitir o botão de alternar a sidebar */
    
    /* ========== AJUSTES DEFAULTS ========== */
    section[data-testid="stSidebar"] + section {background: transparent;}
    [data-testid="stSidebarCollapseButton"] { display: inline-flex !important; opacity: 1 !important; }
    
    /* ========== SIDEBAR ========== */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #FFFFFF 0%, #F3F8FF 100%) !important;
        border-right: 1px solid var(--border-color);
        box-shadow: 2px 0 8px rgba(0, 0, 0, 0.03);
        width: 320px !important;
        min-width: 320px !important;
        max-width: 360px !important;
    }
    
    [data-testid="stSidebar"] > div:first-child {
        background: transparent;
        padding: 2rem 1.25rem 1.5rem;
    }
    
    /* ========== SIDEBAR COMPONENTS ========== */
    .sidebar-section {
        background: transparent;
        padding: 1rem 0;
        margin-bottom: 0.75rem;
    }
    
    .sidebar-title {
        font-size: 0.7rem;
        font-weight: 600;
        color: var(--text-gray);
        margin-bottom: 1rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid var(--border-color);
    }
    
    /* ========== CABEÇALHO PRINCIPAL ========== */
    .main-header {
        background: transparent;
        padding: 1.5rem 0 2rem;
        margin-bottom: 1.5rem;
        text-align: center;
        border-bottom: 1px solid var(--border-color);
    }
    
    .app-title { 
        font-size: 1.75rem;
        font-weight: 600;
        color: var(--text-dark);
        margin: 0;
        letter-spacing: -0.02em;
        line-height: 1.2;
    }
    
    .app-subtitle { 
        color: var(--text-gray);
        margin-top: 0.5rem;
        font-size: 0.875rem;
        font-weight: 400;
        line-height: 1.5;
    }
    
    /* ========== AVATAR ALPHY ========== */
    .alphy-wrap {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.75rem;
        margin-bottom: 0.75rem;
    }

    .alphy-avatar {
        width: 56px;
        height: 56px;
        border-radius: 12px;
        background: linear-gradient(180deg, #EFF6FF 0%, #E0EAFF 100%);
        border: 1px solid #DBEAFE;
        box-shadow: var(--shadow-sm);
        display: grid;
        place-items: center;
        animation: float 6s ease-in-out infinite;
    }

    .alphy-avatar svg {
        width: 34px;
        height: 34px;
    }

    @keyframes float {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-4px); }
    }

    /* ========== CHAT CONTAINER ========== */
    .chat-container {
        background: transparent;
        padding: 0;
        margin-bottom: 1.5rem;
        min-height: 400px;
    }
    
    /* ========== MENSAGENS DO CHAT ========== */
    .assistant-bubble { 
        background: rgba(59, 130, 246, 0.08);
        color: var(--text-dark);
        padding: 0.75rem 1rem 0.95rem;
        border-radius: 16px;
        margin-bottom: 1rem;
        border: 1px solid rgba(59, 130, 246, 0.25);
        box-shadow: var(--shadow-xs);
        animation: slideIn 0.3s ease-out;
        line-height: 1.7;
        max-width: 85%;
        backdrop-filter: blur(6px);
        -webkit-backdrop-filter: blur(6px);
    }
    
    .user-bubble { 
        background: rgba(255, 255, 255, 0.75);
        color: var(--text-dark);
        padding: 0.75rem 1rem 0.95rem;
        border-radius: 16px;
        margin-bottom: 1rem;
        border: 1px solid var(--border-color);
        box-shadow: var(--shadow-xs);
        animation: slideIn 0.3s ease-out;
        margin-left: auto;
        max-width: 75%;
        line-height: 1.7;
        backdrop-filter: blur(6px);
        -webkit-backdrop-filter: blur(6px);
    }
    
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(12px) scale(0.98);
        }
        to {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }
    
    /* ========== CHIPS DE IDENTIFICAÇÃO ========== */
    .name-chip {
        display: inline-block;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        padding: 0.2rem 0.5rem;
        border-radius: 999px;
        margin-bottom: 0.35rem;
        border: 1px solid var(--border-color);
        background: rgba(255,255,255,0.7);
        color: #374151;
        backdrop-filter: blur(4px);
        -webkit-backdrop-filter: blur(4px);
    }
    .name-chip.alphy {
        background: rgba(59, 130, 246, 0.12);
        border-color: rgba(59, 130, 246, 0.35);
        color: #1D4ED8;
    }
    .name-chip.user {
        background: rgba(255,255,255,0.6);
    }
    
    /* ========== BOTÕES ========== */
    .stButton > button {
        background: var(--white);
        color: #4B5563;
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 0.625rem 0.875rem;
        font-weight: 500;
        font-size: 0.8rem;
        transition: all 0.2s ease;
        box-shadow: var(--shadow-xs);
        text-align: left;
    }
    
    .stButton > button:hover {
        background: #EFF6FF;
        border-color: var(--primary-blue);
        color: var(--primary-blue);
        box-shadow: var(--shadow-sm);
        transform: translateX(2px);
    }
    
    .stButton > button:active {
        transform: translateX(0);
        box-shadow: var(--shadow-xs);
    }
    
    /* Botões de ação (Reload/Limpar) */
    .stButton > button[kind="primary"] {
        background: var(--primary-blue);
        color: white;
        border-color: var(--primary-blue);
    }
    
    .stButton > button[kind="primary"]:hover {
        background: #2563EB;
        border-color: #2563EB;
        transform: translateY(-1px);
    }
    
    /* ========== BOTÕES DE COMANDO ========== */
    .command-btn {
        display: block;
        width: 100%;
        background: rgba(59, 130, 246, 0.06);
        border: 1px solid rgba(59, 130, 246, 0.18);
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        font-size: 0.8rem;
        font-weight: 600;
        color: #1E40AF;
        text-align: left;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: var(--shadow-xs);
        backdrop-filter: blur(4px);
        -webkit-backdrop-filter: blur(4px);
    }
    
    .command-btn:hover {
        background: rgba(59, 130, 246, 0.12);
        border-color: var(--primary-blue);
        color: var(--primary-blue);
        transform: translateX(2px);
    }
    
    .command-btn:active {
        transform: translateX(0);
    }
    
    .command-btn::before {
        content: '▸';
        margin-right: 0.5rem;
        opacity: 0.6;
    }
    
    /* ========== INPUT DE CHAT ========== */
    .stChatInputContainer {
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        border: 1px solid rgba(59, 130, 246, 0.18);
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.10);
        padding: 0.5rem;
        margin-top: 1.5rem;
    }
    
    .stChatInput > div {
        background: transparent !important;
    }
    
    .stChatInput textarea {
        background: var(--white) !important;
        border: none !important;
        border-radius: 8px !important;
        color: var(--text-dark) !important;
        font-size: 0.9rem;
        padding: 0.75rem 1rem !important;
        line-height: 1.5 !important;
    }
    
    .stChatInput textarea:focus {
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
    }
    
    .stChatInput textarea::placeholder {
        color: var(--text-light);
    }
    
    /* ========== MARKDOWN CUSTOMIZADO ========== */
    [data-testid="stMarkdownContainer"] p {
        line-height: 1.75;
        font-size: 0.925rem;
        color: var(--text-dark);
        margin-bottom: 0.75rem;
    }
    
    [data-testid="stMarkdownContainer"] ul {
        padding-left: 1.5rem;
        margin: 0.5rem 0;
    }
    
    [data-testid="stMarkdownContainer"] li {
        margin-bottom: 0.625rem;
        line-height: 1.65;
        color: var(--text-gray);
    }
    
    [data-testid="stMarkdownContainer"] code {
        background: var(--light-blue);
        color: var(--primary-blue);
        padding: 0.2rem 0.5rem;
        border-radius: 6px;
        font-size: 0.875rem;
        font-weight: 500;
        border: 1px solid rgba(59, 130, 246, 0.15);
    }
    
    [data-testid="stMarkdownContainer"] strong {
        font-weight: 600;
        color: var(--text-dark);
    }
    
    /* ========== SPINNERS & LOADING ========== */
    .stSpinner > div {
        border-color: var(--border-color);
        border-top-color: var(--primary-blue);
    }
    
    /* ========== ALERTAS ========== */
    .stSuccess, .stError, .stInfo, .stWarning {
        background: var(--white) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
        box-shadow: var(--shadow-xs) !important;
    }
    
    /* ========== RODAPÉ ========== */
    .footer {
        text-align: right;
        padding: 2rem 0 1rem;
        color: var(--text-light);
        font-size: 0.8rem;
        font-weight: 400;
        margin-top: 3rem;
    }
    
    /* ========== DIVISORES ========== */
    hr {
        border: none;
        height: 1px;
        background: var(--border-color);
        margin: 1.5rem 0;
    }
    
    /* ========== SCROLLBAR CUSTOMIZADA ========== */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--bg-gray);
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--border-color);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: var(--text-light);
    }
    
    /* ========== MODO ESCURO ========== */
    @media (prefers-color-scheme: dark) {
        :root {
            --bg-gray: #111827;
            --white: #1F2937;
            --text-dark: #F9FAFB;
            --text-gray: #D1D5DB;
            --text-light: #9CA3AF;
            --border-color: #374151;
        }
        
        .stApp {
            background: #0F172A;
        }
        
        [data-testid="stSidebar"] {
            background: #1F2937 !important;
            border-right-color: #374151;
        }
        
        .assistant-bubble {
            background: rgba(59, 130, 246, 0.12);
            border-color: rgba(59, 130, 246, 0.25);
        }
    }
    
    /* ========== RESPONSIVIDADE ========== */
    @media (max-width: 768px) {
        .main .block-container {
            padding: 1rem;
        }
        
        .main-header {
            padding: 1.5rem;
        }
        
        .app-title {
            font-size: 1.8rem;
        }
        
        .app-subtitle {
            font-size: 1rem;
        }
        
        .user-bubble {
            max-width: 100%;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------- Tema (claro/escuro) ---------
if 'theme' not in st.session_state:
    st.session_state.theme = 'light'

# Botão único no topo direito (fora da sidebar)
top_l, top_r = st.columns([10, 1], gap="small")
with top_r:
    theme_icon = "🌙" if st.session_state.theme == 'light' else "☀️"
    if st.button(theme_icon, key="theme_toggle", help="Alternar tema"):
        st.session_state.theme = 'dark' if st.session_state.theme == 'light' else 'light'
        st.rerun()

# Overrides de CSS para modo escuro (sem JS, usando variáveis)
if st.session_state.theme == 'dark':
    st.markdown(
        """
        <style>
        :root {
            --bg-gray: #111827;
            --white: #1F2937;
            --text-dark: #F9FAFB;
            --text-gray: #D1D5DB;
            --text-light: #9CA3AF;
            --border-color: #374151;
        }
        .stApp { background: #0F172A; }
        [data-testid="stSidebar"] { background: #1F2937 !important; border-right-color: #374151; }
        .assistant-bubble { background: rgba(59, 130, 246, 0.12); border-color: rgba(59, 130, 246, 0.25); color: #F9FAFB; }
        .user-bubble { background: rgba(31,41,55,0.8); border-color: #374151; color: #F9FAFB; }
        .stChatInputContainer { background: rgba(31,41,55,0.7); border-color: rgba(59,130,246,0.3); }
        .stButton > button { background: rgba(31,41,55,0.9); border-color: #374151; color: #D1D5DB; }
        .name-chip { background: rgba(31,41,55,0.8); border-color: #374151; color: #D1D5DB; }
        .name-chip.alphy { background: rgba(59,130,246,0.15); border-color: rgba(59,130,246,0.35); color: #93C5FD; }
        </style>
        """,
        unsafe_allow_html=True,
    )

# --------- Inicializar histórico ---------
if "history" not in st.session_state:
    st.session_state.history = []

if "google_sheets_cache" not in st.session_state:
    st.session_state.google_sheets_cache = None

# Estado do campo de entrada do chat
if 'chat_input' not in st.session_state:
    st.session_state.chat_input = ""

# --------- Funções auxiliares ---------

def get_google_sheets_context() -> str:
    """Carrega contexto das planilhas do Google Drive da pasta específica"""
    if st.session_state.google_sheets_cache:
        return st.session_state.google_sheets_cache
    
    try:
        # Busca planilhas em todo o Drive (sem pasta específica) e inclui Excel
        sheets = list_spreadsheets(include_excel=True)
        if not sheets:
            return ""
        
        context = f"\n\n**Planilhas disponíveis no Google Drive:**\n"
        for sheet in sheets[:20]:  # Limita a 20 planilhas
            label = ""
            mt = sheet.get('mimeType')
            if mt and mt != 'application/vnd.google-apps.spreadsheet':
                label = " [Excel]"
            context += f"- {sheet['name']}{label} (ID: {sheet['id']})\n"
        
        st.session_state.google_sheets_cache = context
        return context
    except Exception as e:
        st.error(f"Erro ao carregar planilhas do Drive: {e}")
        return ""

def process_special_commands(prompt: str) -> tuple[bool, str]:
    """
    Processa comandos especiais do usuário.
    Retorna (comando_processado, resposta)
    """
    prompt_lower = prompt.lower().strip()
    
    # Comando: listar planilhas/planilhas
    if any(word in prompt_lower for word in ["liste os planilhas", "listar planilhas", "mostrar planilhas", "planilhas disponíveis"]):
        try:
            sheets = list_spreadsheets(include_excel=True)
            if not sheets:
                return True, "Nenhuma planilha encontrada no Google Drive."
            
            response = f"**Encontrei {len(sheets)} planilha(s) no Google Drive:**\n\n"
            for i, sheet in enumerate(sheets, 1):
                label = ""
                mt = sheet.get('mimeType')
                if mt and mt != 'application/vnd.google-apps.spreadsheet':
                    label = " [Excel]"
                response += f"{i}. **{sheet['name']}**{label}\n"
                response += f"   - ID: `{sheet['id']}`\n"
                response += f"   - Modificado: {sheet.get('modifiedTime', 'N/A')}\n\n"
            
            st.info(f"Planilhas do Google Drive carregadas - {len(sheets)} encontrada(s)")
            return True, response
        except Exception as e:
            return True, f"Erro ao listar planilhas: {str(e)}"
    
    # Comando: mostrar respostas de um planilha
    if "respostas do planilha" in prompt_lower or "respostas da planilha" in prompt_lower:
        try:
            # Tenta extrair ID da planilha do prompt
            sheets = list_spreadsheets(include_excel=True)
            if not sheets:
                return True, "Nenhuma planilha encontrada no Google Drive. Verifique as permissões."
            
            # Seleciona preferencialmente uma Planilha Google; se vier Excel, converte
            google_sheets = [s for s in sheets if s.get('mimeType') == 'application/vnd.google-apps.spreadsheet']
            candidate = google_sheets[0] if google_sheets else sheets[0]
            sheet_id = candidate['id']
            sheet_name = candidate['name']
            mime = candidate.get('mimeType')
            
            if mime and mime != 'application/vnd.google-apps.spreadsheet':
                try:
                    converted = convert_excel_to_google_sheet(sheet_id, new_title=f"{sheet_name} (convertido)")
                    sheet_id = converted['id']
                    sheet_name = converted.get('name', sheet_name)
                except Exception as ce:
                    return True, f"Arquivo Excel detectado e falha ao converter automaticamente: {ce}"
            
            responses = get_form_responses(sheet_id)
            
            if not responses:
                return True, f"Nenhuma resposta encontrada na planilha '{sheet_name}'."
            
            response = f"**Respostas do planilha '{sheet_name}':**\n\n"
            response += f"Total de respostas: **{len(responses)}**\n\n"
            
            # Mostra as primeiras 3 respostas
            for i, resp in enumerate(responses[:3], 1):
                response += f"**Resposta {i}:**\n"
                for key, value in resp.items():
                    response += f"- {key}: {value}\n"
                response += "\n"
            
            if len(responses) > 3:
                response += f"_... e mais {len(responses) - 3} resposta(s)._"
            
            st.success(f"{len(responses)} resposta(s) retornada(s) com sucesso")
            return True, response
        except Exception as e:
            return True, f"Erro ao buscar respostas: {str(e)}"
    
    return False, ""

def call_abacus_streaming(messages: List[Dict[str, str]]):
    """Chama a API Abacus.ai com streaming"""
    headers = {
        "Authorization": f"Bearer {ABACUS_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": ABACUS_MODEL,
        "messages": messages,
        "temperature": DEFAULT_TEMPERATURE,
        "stream": True,
    }
    
    try:
        response = requests.post(ABACUS_URL, headers=headers, json=payload, stream=True, timeout=60)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if not line:
                continue
            
            line = line.decode("utf-8")
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue
    
    except requests.exceptions.RequestException as e:
        yield f"\n\n**Erro na API:** {str(e)}"

# --------- Interface ---------

# Sidebar com configurações (estilo compacto e moderno)
with st.sidebar:
    # Logo e título (sem emojis)
    st.markdown(
        """
        <div style="text-align: center; padding: 1.25rem 0 1.5rem;">
            <div class="alphy-wrap">
                <div class="alphy-avatar">
                    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="14" y="18" width="36" height="28" rx="8" fill="#FFFFFF" stroke="#93C5FD"/>
                        <circle cx="26" cy="32" r="4" fill="#2563EB"/>
                        <circle cx="38" cy="32" r="4" fill="#2563EB"/>
                        <rect x="28" y="10" width="8" height="6" rx="2" fill="#3B82F6"/>
                    </svg>
                </div>
            </div>
            <div style="font-size: 1.1rem; font-weight: 600; color: #111827;">Alpha Insights</div>
            <div style="font-size: 0.75rem; color: #6B7280; margin-top: 0.25rem;">Assistente de Análise</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    
    # Seção: Ações Rápidas
    st.markdown('<div class="sidebar-title">AÇÕES RÁPIDAS</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Reload", use_container_width=True, key="reload_btn"):
            st.session_state.google_sheets_cache = None
            ctx = get_google_sheets_context()
            # conta planilhas no contexto
            count = ctx.count("(ID:") if ctx else 0
            st.success(f"Atualizado • {count} planilhas")
    
    with col2:
        if st.button("Limpar", use_container_width=True, key="clear_btn"):
            st.session_state.history = []
            st.rerun()
    
    st.markdown("---")
    
    # Seção: Comandos Rápidos
    st.markdown('<div class="sidebar-title">COMANDOS RÁPIDOS</div>', unsafe_allow_html=True)
    
    # Inicializa session state para prefill da entrada
    if 'prefill_command' not in st.session_state:
        st.session_state.prefill_command = None
    
    comandos = [
        "Receita total do mês",
        "Vendas por produto",
        "Relatório de desempenho",
        "Comparar meses",
        "Liste as planilhas disponíveis",
        "Mostre as respostas da planilha"
    ]
    
    for idx, comando in enumerate(comandos):
        if st.button(comando, key=f"cmd_{idx}", use_container_width=True):
            # Preenche o campo de entrada SEM enviar
            st.session_state.prefill_command = comando + " "
            st.session_state.chat_input = st.session_state.prefill_command
            st.rerun()
    
    # Espaçador
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    
    # Contador de mensagens (sem emojis)
    msg_count = len(st.session_state.history)
    st.markdown(
        f"""
        <div style=\"text-align: center; font-size: 0.7rem; color: #9CA3AF; padding: 0.75rem 0;\">{msg_count} mensagens no histórico</div>
        """,
        unsafe_allow_html=True,
    )

# Container do chat (sem header grande)
st.markdown('<div class="chat-container">', unsafe_allow_html=True)

# Exibir histórico do chat
if st.session_state.history:
    for msg in st.session_state.history:
        role = msg["role"]
        content = msg["content"]
        
        if role == "assistant":
            st.markdown(f'''
                <div class="assistant-bubble">
                    <div class="name-chip alphy">Alphy</div>
                    <div style="display: block;">{content}</div>
                </div>
            ''', unsafe_allow_html=True)
        else:
            st.markdown(f'''
                <div class="user-bubble">
                    <div class="name-chip user">Você</div>
                    <div style="display: block;">{content}</div>
                </div>
            ''', unsafe_allow_html=True)
else:
    # Mensagem de boas-vindas
    st.markdown(
        """
        <div style="text-align: center; padding: 3.25rem 2rem 2.5rem;">
            <div class="alphy-wrap" style="justify-content: center; margin-bottom: 0.75rem;">
                <div class="alphy-avatar">
                    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="14" y="18" width="36" height="28" rx="8" fill="#FFFFFF" stroke="#93C5FD"/>
                        <circle cx="26" cy="32" r="4" fill="#2563EB"/>
                        <circle cx="38" cy="32" r="4" fill="#2563EB"/>
                        <rect x="28" y="10" width="8" height="6" rx="2" fill="#3B82F6"/>
                    </svg>
                </div>
            </div>
            <h2 style="font-weight: 700; color: #1F2937; margin-bottom: 0.5rem; font-size: 1.6rem; letter-spacing: -0.01em;">Olá, eu sou o Alphy!</h2>
            <div class="name-chip alphy" style="margin: 0 auto 0.25rem;">O bot de consulta de planilhas da Alpha Insights</div>
            <p style="font-size: 0.9rem; color: #6B7280; line-height: 1.6; max-width: 520px; margin: 0.25rem auto 0;"></p>
            <p style="font-size: 0.8rem; color: #9CA3AF; margin-top: 0.75rem;">Use os comandos rápidos da sidebar ou digite sua pergunta abaixo.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown('</div>', unsafe_allow_html=True)

# Input do usuário (com key para controlar via session_state)
if st.session_state.get('prefill_command'):
    # Se houve prefill numa iteração anterior, já colocamos em chat_input e limpamos a flag
    st.session_state.prefill_command = None

prompt = st.chat_input("Digite sua mensagem...", key='chat_input')

if prompt:
    # Adiciona mensagem do usuário ao histórico
    st.session_state.history.append({"role": "user", "content": prompt})

    # Exibe mensagem do usuário com novo estilo
    st.markdown(f'''
        <div class="user-bubble">
            <div class="name-chip user">Você</div>
            <div style="display: block;">{prompt}</div>
        </div>
    ''', unsafe_allow_html=True)
    
    # Verifica se é um comando especial
    is_special, special_response = process_special_commands(prompt)
    
    if is_special:
        # Resposta direta do comando especial
        st.session_state.history.append({"role": "assistant", "content": special_response})
        st.markdown(f'''
            <div class="assistant-bubble">
                <div class="name-chip alphy">Alphy</div>
                <div style="display: block;">{special_response}</div>
            </div>
        ''', unsafe_allow_html=True)
        st.rerun()
    else:
        # Prepara contexto com dados das planilhas
        sheets_context = get_google_sheets_context()
        
        system_message = {
            "role": "system",
            "content": f"""Você é Alphy, o assistente de análise de dados da Alpha Insights. Identifique-se como Alphy nas respostas quando fizer sentido.

{sheets_context}

Você tem acesso às planilhas acima e pode ajudar o usuário a:
- Analisar dados
- Responder perguntas sobre as planilhas
- Gerar insights e relatórios
- Processar informações de planilhas

Seja objetivo, profissional e forneça respostas em português brasileiro."""
        }
        
        # Monta histórico de mensagens
        messages = [system_message]
        for h in st.session_state.history[-10:]:  # Últimas 10 mensagens
            messages.append({"role": h["role"], "content": h["content"]})
        
        # Chama a API com streaming
        with st.spinner("Pensando..."):
            response_placeholder = st.empty()
            full_response = ""
            
            try:
                for chunk in call_abacus_streaming(messages):
                    full_response += chunk
                    response_placeholder.markdown(f'''
                        <div class="assistant-bubble">
                            <div class="name-chip alphy">Alphy</div>
                            <div style="display: block;">{full_response}</div>
                        </div>
                    ''', unsafe_allow_html=True)
                
                # Adiciona resposta ao histórico
                st.session_state.history.append({"role": "assistant", "content": full_response})
            
            except Exception as e:
                error_msg = f"Erro ao processar sua mensagem: {str(e)}"
                st.error(error_msg)
                st.session_state.history.append({"role": "assistant", "content": error_msg})

# Rodapé discreto
st.markdown("""
    <div style="text-align: center; padding: 2rem 0 1rem; margin-top: 2rem; border-top: 1px solid #E5E7EB;">
        <div style="font-size: 0.7rem; color: #9CA3AF;">
            Alpha Insights © 2025
        </div>
    </div>
""", unsafe_allow_html=True)


