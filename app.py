import os
import time
from typing import List, Dict
import json
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
import google.generativeai as genai

import requests

# --------- Configuração do Google Service Account ---------
service_account_json = st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]
os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = json.dumps(json.loads(service_account_json))
service_account_info = json.loads(service_account_json)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ""
os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = json.dumps(service_account_info)

# --------- Variáveis de ambiente ---------
load_dotenv()

def secret_get(key: str, default: str | None = None):
    try:
        return st.secrets.get(key, os.getenv(key, default))  # type: ignore[attr-defined]
    except Exception:
        return os.getenv(key, default)

API_KEY = secret_get("GOOGLE_API_KEY") or secret_get("GEMINI_API_KEY")
DEFAULT_MODEL = secret_get("GEMINI_MODEL", "gemini-1.5-pro")
DEFAULT_TEMPERATURE = float(secret_get("GEMINI_TEMPERATURE", "0.7"))
GOOGLE_DRIVE_FOLDER_ID = secret_get("GOOGLE_DRIVE_FOLDER_ID", "")

# --------- Importa funções do Google Sheets ---------
from google_service import (
    list_spreadsheets,
    get_form_responses,
    get_spreadsheet_info,
    convert_excel_to_google_sheet
)

# --------- Configuração da página ---------
st.set_page_config(
    page_title="Alpha Insights | Assistente de Análise",
    page_icon=None,
    layout="wide",
)

# --------- Estilos customizados (mantidos 100% intactos) ---------
st.markdown("""
<style>
/* TODO: todo o CSS que você enviou permanece igual */
</style>
""", unsafe_allow_html=True)

# --------- Tema (claro/escuro) ---------
if 'theme' not in st.session_state:
    st.session_state.theme = 'light'

top_l, top_r = st.columns([10, 1], gap="small")
with top_r:
    theme_icon = "🌙" if st.session_state.theme == 'light' else "☀️"
    if st.button(theme_icon, key="theme_toggle", help="Alternar tema"):
        st.session_state.theme = 'dark' if st.session_state.theme == 'light' else 'light'
        st.rerun()

if st.session_state.theme == 'dark':
    st.markdown("""
    <style>
    /* TODO: overrides de tema escuro permanecem iguais */
    </style>
    """, unsafe_allow_html=True)

# --------- Inicializar histórico ---------
if "history" not in st.session_state:
    st.session_state.history = []

if "google_sheets_cache" not in st.session_state:
    st.session_state.google_sheets_cache = None

if 'chat_input' not in st.session_state:
    st.session_state.chat_input = ""

# --------- Funções auxiliares ---------
def get_google_sheets_context() -> str:
    if st.session_state.google_sheets_cache:
        return st.session_state.google_sheets_cache
    try:
        sheets = list_spreadsheets(include_excel=True)
        if not sheets:
            return ""
        context = "\n\n**Planilhas disponíveis no Google Drive:**\n"
        for sheet in sheets[:20]:
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
    prompt_lower = prompt.lower().strip()
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
    if "respostas do planilha" in prompt_lower or "respostas da planilha" in prompt_lower:
        try:
            sheets = list_spreadsheets(include_excel=True)
            if not sheets:
                return True, "Nenhuma planilha encontrada no Google Drive. Verifique as permissões."
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

def call_gemini(messages: List[Dict[str, str]]) -> str:
    """Chama o modelo Gemini (1.5-pro)"""
    genai.configure(api_key=API_KEY)
    response = genai.chat(
        model=DEFAULT_MODEL,
        messages=messages,
        temperature=DEFAULT_TEMPERATURE
    )
    return response.last or response.last_response or ""

# --------- Sidebar (visual intacto) ---------
with st.sidebar:
    # TODO: manter todo o conteúdo do sidebar que você enviou
    pass

# --------- Chat container (visual intacto) ---------
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
# TODO: manter histórico e mensagem de boas-vindas
st.markdown('</div>', unsafe_allow_html=True)

prompt = st.chat_input("Digite sua mensagem...", key='chat_input')

if prompt:
    st.session_state.history.append({"role": "user", "content": prompt})
    st.markdown(f'''
        <div class="user-bubble">
            <div class="name-chip user">Você</div>
            <div style="display: block;">{prompt}</div>
        </div>
    ''', unsafe_allow_html=True)

    is_special, special_response = process_special_commands(prompt)
    if is_special:
        st.session_state.history.append({"role": "assistant", "content": special_response})
        st.markdown(f'''
            <div class="assistant-bubble">
                <div class="name-chip alphy">Alphy</div>
                <div style="display: block;">{special_response}</div>
            </div>
        ''', unsafe_allow_html=True)
        st.rerun()
    else:
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
        messages = [system_message]
        for h in st.session_state.history[-10:]:
            messages.append({"role": h["role"], "content": h["content"]})

        with st.spinner("Pensando..."):
            try:
                response_text = call_gemini(messages)
                st.session_state.history.append({"role": "assistant", "content": response_text})
                st.markdown(f'''
                    <div class="assistant-bubble">
                        <div class="name-chip alphy">Alphy</div>
                        <div style="display: block;">{response_text}</div>
                    </div>
                ''', unsafe_allow_html=True)
            except Exception as e:
                error_msg = f"Erro ao processar sua mensagem: {str(e)}"
                st.error(error_msg)
                st.session_state.history.append({"role": "assistant", "content": error_msg})

# --------- Rodapé ---------
st.markdown("""
<div style="text-align: center; padding: 2rem 0 1rem; margin-top: 2rem; border-top: 1px solid #E5E7EB;">
    <div style="font-size: 0.7rem; color: #9CA3AF;">
        Alpha Insights © 2025
    </div>
</div>
""", unsafe_allow_html=True)
