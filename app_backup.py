import os
import time
from typing import List, Dict, Any
import json
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
import google.generativeai as genai
import requests

# Importa serviço do Google Sheets
from google_service import (
    list_spreadsheets,
    get_form_responses,
    get_spreadsheet_info
)

# --------- Carregar variáveis de ambiente ---------
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
DEFAULT_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
ABACUS_API_KEY = os.getenv("ABACUS_API_KEY")
ABACUS_MODEL = os.getenv("ABACUS_MODEL", "gemini-2.0-flash-exp")
ABACUS_URL = "https://routellm.abacus.ai/v1/chat/completions"

# --------- Configuração da página ---------
st.set_page_config(
    page_title="Alpha Insights | Assistente de Análise",
    page_icon="📊",
    layout="wide",
)

# --------- Estilos customizados ---------
st.markdown(
    """
    <style>
    /* Layout base */
    .main .block-container { 
        padding-top: 1rem; 
        padding-bottom: 2rem; 
        max-width: 1200px;
    }

    /* Cabeçalho */
    .app-title { 
        font-size: 2rem; 
        font-weight: 700; 
        color: #1E3A8A;
        margin-bottom: 0.5rem;
    }
    .app-subtitle { 
        color: #6b7280; 
        margin-top: 0.2rem; 
        font-size: 1rem;
    }

    /* Balões do chat */
    .assistant-bubble { 
        background: linear-gradient(135deg, #3B82F6 0%, #1E3A8A 100%);
        color: white; 
        padding: 1rem 1.2rem; 
        border-radius: 16px;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(30, 58, 138, 0.2);
    }
    .user-bubble { 
        background: #F3F4F6; 
        color: #111827; 
        padding: 1rem 1.2rem; 
        border-radius: 16px;
        margin-bottom: 1rem;
        border: 1px solid #E5E7EB;
    }

    /* Botões */
    .stButton > button {
        background: #3B82F6;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        background: #1E3A8A;
        box-shadow: 0 4px 12px rgba(30, 58, 138, 0.3);
    }

    /* Input */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 2px solid #E5E7EB;
        padding: 0.75rem;
    }
    .stTextInput > div > div > input:focus {
        border-color: #3B82F6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }

    /* Sidebar */
    .css-1d391kg, [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #F9FAFB 0%, #F3F4F6 100%);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------- Inicializar histórico ---------
if "history" not in st.session_state:
    st.session_state.history = []

if "google_sheets_cache" not in st.session_state:
    st.session_state.google_sheets_cache = None

# --------- Funções auxiliares ---------

def get_google_sheets_context() -> str:
    """Carrega contexto das planilhas do Google Drive"""
    if st.session_state.google_sheets_cache:
        return st.session_state.google_sheets_cache
    
    try:
        sheets = list_spreadsheets()
        if not sheets:
            return ""
        
        context = "\n\n📊 **PLANILHAS DISPONÍVEIS:**\n"
        for sheet in sheets[:10]:  # Limita a 10 para não sobrecarregar
            context += f"- {sheet['name']} (ID: {sheet['id']})\n"
        
        st.session_state.google_sheets_cache = context
        return context
    except Exception as e:
        st.error(f"❌ Erro ao carregar planilhas: {e}")
        return ""

def process_special_commands(prompt: str) -> tuple[bool, str]:
    """
    Processa comandos especiais do usuário.
    Retorna (comando_processado, resposta)
    """
    prompt_lower = prompt.lower().strip()
    
    # Comando: listar planilhas/planilhas
    if any(word in prompt_lower for word in ["liste as planilhas", "listar planilhas", "mostrar planilhas", "planilhas disponíveis"]):
        try:
            sheets = list_spreadsheets()
            if not sheets:
                return True, "❌ Nenhuma planilha encontrada no Google Drive."
            
            response = f"📊 **Encontrei {len(sheets)} planilha(s):**\n\n"
            for i, sheet in enumerate(sheets, 1):
                response += f"{i}. **{sheet['name']}**\n"
                response += f"   - ID: `{sheet['id']}`\n"
                response += f"   - Modificado: {sheet.get('modifiedTime', 'N/A')}\n\n"
            
            st.info(f"✅ Google Sheets carregado com sucesso - {len(sheets)} planilha(s) encontrada(s)")
            return True, response
        except Exception as e:
            return True, f"❌ Erro ao listar planilhas: {str(e)}"
    
    # Comando: mostrar respostas de um planilha
    if "respostas do planilha" in prompt_lower or "respostas da planilha" in prompt_lower:
        try:
            # Tenta extrair ID da planilha do prompt
            sheets = list_spreadsheets()
            if not sheets:
                return True, "❌ Nenhuma planilha encontrada. Compartilhe as planilhas com a service account primeiro."
            
            # Pega a primeira planilha como exemplo
            sheet_id = sheets[0]['id']
            sheet_name = sheets[0]['name']
            
            responses = get_form_responses(sheet_id)
            
            if not responses:
                return True, f"❌ Nenhuma resposta encontrada na planilha '{sheet_name}'."
            
            response = f"📋 **Respostas do planilha '{sheet_name}':**\n\n"
            response += f"Total de respostas: **{len(responses)}**\n\n"
            
            # Mostra as primeiras 3 respostas
            for i, resp in enumerate(responses[:3], 1):
                response += f"**Resposta {i}:**\n"
                for key, value in resp.items():
                    response += f"- {key}: {value}\n"
                response += "\n"
            
            if len(responses) > 3:
                response += f"_... e mais {len(responses) - 3} resposta(s)._"
            
            st.success(f"📊 {len(responses)} resposta(s) retornada(s) com sucesso")
            return True, response
        except Exception as e:
            return True, f"❌ Erro ao buscar respostas: {str(e)}"
    
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
        yield f"\n\n❌ **Erro na API:** {str(e)}"

# --------- Interface ---------

# Sidebar com configurações
with st.sidebar:
    st.markdown('<p class="app-title">⚙️ Configurações</p>', unsafe_allow_html=True)
    st.markdown("---")
    
    # Botão para recarregar planilhas
    if st.button("🔄 Recarregar Planilhas", use_container_width=True):
        st.session_state.google_sheets_cache = None
        get_google_sheets_context()
        st.success("✅ Cache de planilhas atualizado!")
    
    st.markdown("---")
    
    # Informações
    st.markdown("### 📊 Recursos")
    st.markdown("""
    - Análise de dados em tempo real
    - Integração com Google Sheets
    - Respostas contextualizadas
    - Comandos especiais disponíveis
    """)
    
    st.markdown("---")
    st.markdown("### 💡 Comandos Especiais")
    st.markdown("""
    - `Liste os planilhas disponíveis`
    - `Mostre as respostas da planilha`
    - `Quantas respostas teve no mês de agosto?`
    """)
    
    st.markdown("---")
    if st.button("🗑️ Limpar Histórico", use_container_width=True):
        st.session_state.history = []
        st.rerun()

# Cabeçalho principal
st.markdown('<p class="app-title">📊 Alpha Insights</p>', unsafe_allow_html=True)
st.markdown('<p class="app-subtitle">Assistente Inteligente de Análise de Dados</p>', unsafe_allow_html=True)
st.markdown("---")

# Exibir histórico do chat
for msg in st.session_state.history:
    role = msg["role"]
    content = msg["content"]
    
    if role == "assistant":
        st.markdown(f'<div class="assistant-bubble">🤖 {content}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="user-bubble">👤 {content}</div>', unsafe_allow_html=True)

# Input do usuário
prompt = st.chat_input("Digite sua mensagem...")

if prompt:
    # Adiciona mensagem do usuário ao histórico
    st.session_state.history.append({"role": "user", "content": prompt})
    
    # Exibe mensagem do usuário
    st.markdown(f'<div class="user-bubble">👤 {prompt}</div>', unsafe_allow_html=True)
    
    # Verifica se é um comando especial
    is_special, special_response = process_special_commands(prompt)
    
    if is_special:
        # Resposta direta do comando especial
        st.session_state.history.append({"role": "assistant", "content": special_response})
        st.markdown(f'<div class="assistant-bubble">🤖 {special_response}</div>', unsafe_allow_html=True)
        st.rerun()
    else:
        # Prepara contexto com dados das planilhas
        sheets_context = get_google_sheets_context()
        
        system_message = {
            "role": "system",
            "content": f"""Você é o assistente de análise de dados da Alpha Insights.

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
        with st.spinner("🤔 Pensando..."):
            response_placeholder = st.empty()
            full_response = ""
            
            try:
                for chunk in call_abacus_streaming(messages):
                    full_response += chunk
                    response_placeholder.markdown(f'<div class="assistant-bubble">🤖 {full_response}</div>', unsafe_allow_html=True)
                
                # Adiciona resposta ao histórico
                st.session_state.history.append({"role": "assistant", "content": full_response})
            
            except Exception as e:
                error_msg = f"❌ Erro ao processar sua mensagem: {str(e)}"
                st.error(error_msg)
                st.session_state.history.append({"role": "assistant", "content": error_msg})

# Rodapé
st.markdown("---")
st.markdown(
    '<p style="text-align: center; color: #6b7280; font-size: 0.9rem;">Powered by Alpha Insights © 2025</p>',
    unsafe_allow_html=True,
)
